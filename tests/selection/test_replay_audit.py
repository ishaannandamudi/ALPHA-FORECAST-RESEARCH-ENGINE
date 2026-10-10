"""Exact replay, hash seeds, concurrent source/candidate additions and bounded audits."""

import os
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from afre.schema import ContractError
from afre.selection import SelectionBounds, SelectionEngine, SelectionRepository
from afre.selection.lineage import SelectionAudit
from afre.selection.results import CandidateValidationResult, SelectionResult
from afre.serialization import canonical_json
from afre.statistical_models.artifacts import FittedModelArtifact
from afre.target_engine.market_data import TargetBar
from tests.selection.conftest import SelectionCase


def test_idempotence_restart_exact_semantic_bytes(case: SelectionCase) -> None:
    old = canonical_json(case.result), canonical_json(case.registry)
    result, registry = SelectionEngine(case.repository).select(case.space, 100, 100)
    assert (canonical_json(result), canonical_json(registry)) == old
    with SelectionRepository(case.path) as restarted:
        assert canonical_json(restarted.resolve(SelectionResult, result.fingerprint)) == old[0]
        assert restarted.resolve(type(registry), registry.fingerprint) == registry
        assert result.selected_model_id is not None
        assert (
            restarted.get(FittedModelArtifact, result.selected_model_id).fingerprint
            == result.selected_model_id
        )


@pytest.mark.parametrize("endpoint", (20, 45, 80))
def test_concurrent_source_and_candidate_addition_does_not_enter_open_selection(
    case: SelectionCase,
    endpoint: int,
) -> None:
    with SelectionRepository(case.path) as writer:
        old = case.result

        def correct() -> None:
            row = writer._connection.execute(
                "SELECT fingerprint FROM target_bars WHERE end_ns=? LIMIT 1", (endpoint,)
            ).fetchone()
            bar = writer.get(TargetBar, row[0])
            assert bar.close is not None
            corrected = replace(bar, close=bar.close + 10, predecessor_id=bar.fingerprint)
            new_space = replace(case.space, search_key="later-independent-candidate-roster")
            with writer.transaction():
                writer.put(corrected)
                writer.put(new_space)

        selected, _ = SelectionEngine(case.repository).select(
            case.space, 100, 100, snapshot_hook=correct
        )
    assert selected == old
    assert case.repository.resolve(SelectionResult, old.fingerprint) == old


def test_test_truth_payload_perturbation_is_never_decoded(case: SelectionCase) -> None:
    # A corrupt sealed payload is an especially strict read detector: a TEST
    # response load would fail hash validation. Selection must be independent.
    from afre.research_datasets.samples import ResearchSample

    sample = case.repository.get(ResearchSample, case.fixture.test_sample_ids[0])
    trigger = case.repository._connection.execute(
        "SELECT sql FROM sqlite_master WHERE name='immutable_target_artifacts_update'"
    ).fetchone()[0]
    case.repository._connection.execute("DROP TRIGGER immutable_target_artifacts_update")
    case.repository._connection.execute(
        "UPDATE target_artifacts SET payload='corrupt TEST payload' WHERE fingerprint=?",
        (sample.target_id,),
    )
    case.repository._connection.execute(trigger)
    selected, _ = SelectionEngine(case.repository).select(case.space, 100, 100)
    assert selected == case.result


def test_earlier_cutoff_exclusions_create_new_result(case: SelectionCase) -> None:
    from afre.selection.schema import SelectionStatus

    result, _ = SelectionEngine(case.repository).select(case.space, 40, 40)
    assert result.status is SelectionStatus.NO_VALID_CANDIDATE
    assert result.fingerprint != case.result.fingerprint
    assert result.request_id != case.result.request_id
    assert set(result.validation_ids).isdisjoint(case.result.validation_ids)
    new_trials = {
        case.repository.get(CandidateValidationResult, i).trial_id
        for i in result.validation_ids
    }
    assert new_trials.isdisjoint(e.trial_id for e in case.registry.entries)


def test_audit_restart_and_byte_node_depth_bounds(case: SelectionCase) -> None:
    engine = SelectionEngine(case.repository)
    audit = engine.audit(case.result.fingerprint)
    assert isinstance(audit, SelectionAudit)
    assert set(case.result.candidate_ids) <= set(audit.node_ids)
    assert case.space.target_id in audit.node_ids and case.space.horizon_id in audit.node_ids
    assert case.registry.entries[0].trial_id in audit.node_ids
    assert case.repository.resolve(SelectionAudit, audit.fingerprint) == audit
    for field in ("lineage_nodes", "lineage_depth", "payload_bytes"):
        with (
            SelectionRepository(case.path, replace(SelectionBounds(), **{field: 1})) as bounded,
            pytest.raises(ContractError, match="bound"),
        ):
            SelectionEngine(bounded).audit(case.result.fingerprint)


def test_snapshot_and_publication_bounds_rollback(case: SelectionCase) -> None:
    for field in ("snapshot_bytes", "publication_rows"):
        with (
            SelectionRepository(case.path, replace(SelectionBounds(), **{field: 1})) as bounded,
            pytest.raises(ContractError, match="bound"),
        ):
            SelectionEngine(bounded).select(
                replace(case.space, search_key="new-bounded-search"), 100, 100
            )


def test_hash_seeds_and_reversed_requests(case: SelectionCase, tmp_path: Path) -> None:
    source = tmp_path / "seed-source.sqlite"
    shutil.copyfile(case.path, source)
    script = """
import sys
from dataclasses import replace
from afre.selection import SelectionRepository, SelectionEngine, SearchSpace
from afre.serialization import canonical_json
from afre.hashing import bytes_digest
with SelectionRepository(sys.argv[1]) as repo:
    space=repo.get(SearchSpace,sys.argv[2])
    dimensions=tuple(replace(d,values=tuple(reversed(d.values)))
                     for d in reversed(space.dimensions))
    space=replace(space,recipes=tuple(reversed(space.recipes)),dimensions=dimensions,
                  validation_sample_ids=tuple(reversed(space.validation_sample_ids)))
    result,registry=SelectionEngine(repo).select(space,100,100)
    print(bytes_digest((canonical_json(result)+canonical_json(registry)).encode()))
"""
    outputs = []
    for seed in ("0", "1", "42", "random"):
        env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": "src:."}
        outputs.append(
            subprocess.run(
                [
                    str(Path(".venv311/bin/python").resolve()),
                    "-c",
                    script,
                    str(source),
                    case.space.fingerprint,
                ],
                env=env,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        )
    assert len(set(outputs)) == 1


def test_upstream_source_and_request_insertion_reversal(
    case: SelectionCase, tmp_path: Path
) -> None:
    from examples.selection_fixture import small_fixture

    with SelectionRepository(tmp_path / "reverse-native.sqlite") as repo:
        fixture = small_fixture(repo, reverse=True)
        assert fixture.space == case.space
        result, registry = SelectionEngine(repo).select(fixture.space, 100, 100)
        assert canonical_json(result) == canonical_json(case.result)
        assert canonical_json(registry) == canonical_json(case.registry)

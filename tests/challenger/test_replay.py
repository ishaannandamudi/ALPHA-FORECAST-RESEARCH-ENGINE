"""Append-only source/truth revisions, concurrent writers, hash seeds and native provenance."""

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from afre.challenger import (
    ChallengeEngine,
    ChallengeRepository,
    CommonMatchedEvidence,
    EvaluationEvidence,
    ShadowForecast,
    ShadowMode,
)
from afre.health.context import context_records
from afre.serialization import canonical_json
from afre.statistical_models.artifacts import PointForecast
from examples.challenge_context import health_context_for
from examples.challenge_corrections import source_correction, truth_correction
from examples.challenge_selection import selected_participants
from examples.challenger_fixture import ChallengeFixture, evidence_for, program_for
from examples.fusion_fixture import build_fixture
from tests.challenger.conftest import ChallengeCase


def test_source_and_truth_corrections_preserve_old_run(challenge_case: ChallengeCase) -> None:
    c = challenge_case
    program, rules = program_for(c.fixture)
    program = replace(
        program, health_participant_ids=(program.champion_id, *program.challenger_ids)
    )
    c.engine.declare(program, rules)
    evidence = c.engine.evidence(
        replace(
            evidence_for(c.repo, c.fixture, program),
            health_bindings=health_context_for(c.repo, c.fixture, program),
        )
    )
    original = c.engine.evaluate(evidence.fingerprint)
    before = canonical_json(original)
    row = next(
        c.repo.get(ShadowForecast, i)
        for i in evidence.shadow_ids
        if c.repo.get(ShadowForecast, i).participant_id == c.fixture.participants[1].fingerprint
    )
    corrected_source = source_correction(c.repo, row)
    changed_shadow = c.engine.shadow(
        program.fingerprint, row.participant_id, corrected_source, row.origin_ns
    )
    revised = c.engine.evidence(
        replace(
            evidence,
            shadow_ids=tuple(
                changed_shadow.fingerprint if i == row.fingerprint else i
                for i in evidence.shadow_ids
            ),
        )
    )
    updated = c.engine.evaluate(revised.fingerprint)
    assert updated.fingerprint != original.fingerprint
    new_truth = truth_correction(c.repo, evidence.truth_assignments[0][1])
    later = replace(
        program,
        window=replace(program.window, cutoff_ns=122),
        shadow_mode=ShadowMode.RECONSTRUCTED_NATIVE,
    )
    c.engine.declare(later, rules)
    newer = evidence_for(c.repo, c.fixture, later, available_ns=122)
    newer = c.engine.evidence(
        replace(
            newer,
            truth_assignments=tuple(
                (s, new_truth if s == evidence.truth_assignments[0][0] else t)
                for s, t in newer.truth_assignments
            ),
        )
    )
    newest = c.engine.evaluate(newer.fingerprint)
    assert newest.fingerprint not in (original.fingerprint, updated.fingerprint)
    assert canonical_json(c.repo.resolve(type(original), original.fingerprint)) == before
    assert new_truth in {
        t for _, t in c.repo.resolve(CommonMatchedEvidence, newest.common_id).assignments
    }


@pytest.mark.parametrize("operation", ("evaluation", "shadow", "audit"))
def test_frozen_snapshot_parallel_writer(challenge_case: ChallengeCase, operation: str) -> None:
    c = challenge_case
    program, rules = program_for(c.fixture)
    program = replace(
        program, health_participant_ids=(program.champion_id, *program.challenger_ids)
    )
    c.engine.declare(program, rules)
    evidence = c.engine.evidence(
        replace(
            evidence_for(c.repo, c.fixture, program),
            health_bindings=health_context_for(c.repo, c.fixture, program),
        )
    )
    expected = c.engine.evaluate(evidence.fingerprint)
    shadow = c.repo.get(ShadowForecast, evidence.shadow_ids[0])
    audit = c.engine.audit(expected.fingerprint) if operation == "audit" else None
    written: tuple[str, ...] = ()

    def writer() -> tuple[str, ...]:
        with ChallengeRepository(c.path) as repo:
            changed = source_correction(repo, shadow)
            truth = truth_correction(repo, evidence.truth_assignments[0][1])
            rule = replace(rules[0], name="concurrent-criterion", required_improvement=1.0)
            added = replace(
                program, name="concurrent-program", promotion_criterion_ids=(rule.fingerprint,)
            )
            ChallengeEngine(repo).declare(added, (rule,))
            health = health_context_for(repo, c.fixture, program, warning_threshold=0.0)
            return changed, truth, added.fingerprint, *(i for _, i in health)

    def hook() -> None:
        nonlocal written
        with ThreadPoolExecutor(max_workers=1) as pool:
            written = pool.submit(writer).result(timeout=60)

    if operation == "evaluation":
        assert c.engine.evaluate(evidence.fingerprint, snapshot_hook=hook) == expected
    elif operation == "shadow":
        assert (
            c.engine.shadow(
                program.fingerprint,
                shadow.participant_id,
                shadow.source_id,
                shadow.computed_ns,
                snapshot_hook=hook,
            )
            == shadow
        )
    else:
        assert c.engine.audit(expected.fingerprint, snapshot_hook=hook) == audit
    assert (
        len(written) == 6 and c.repo.resolve(type(expected), expected.fingerprint) == expected
    )


@pytest.mark.parametrize("seed", ("0", "1", "42", "random"))
def test_hash_seeds_and_reverse_orders(
    tmp_path: Path, challenge_template: tuple[Path, ChallengeFixture], seed: str
) -> None:
    path, _ = challenge_template
    values = []
    for reverse in ("0", "1"):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "examples.challenge_replay",
                str(path),
                str(tmp_path / (seed + reverse + ".sqlite")),
                reverse,
            ],
            check=True,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "PYTHONHASHSEED": seed,
                "PYTHONPATH": str(Path.cwd() / "src") + os.pathsep + str(Path.cwd()),
            },
        )
        values.append(result.stdout)
    assert values[0] == values[1]
    expected = tmp_path.parent / "challenge-canonical-wire.txt"
    if expected.exists():
        assert expected.read_text() == values[0]
    else:
        expected.write_text(values[0])


def test_completed_selection_and_research_context(tmp_path: Path) -> None:
    path = tmp_path / "selected.sqlite"
    champion, challenger, a, b, records = selected_participants(path)
    with ChallengeRepository(path) as repo:
        fixture = ChallengeFixture(
            build_fixture(repo),
            (champion, challenger),
            ((champion.fingerprint, a), (challenger.fingerprint, b)),
        )
        program, rules = program_for(fixture)
        program = replace(
            program,
            declared_ns=100,
            predeclared=False,
            shadow_mode=ShadowMode.RECONSTRUCTED_NATIVE,
            context_records=records,
        )
        engine = ChallengeEngine(repo)
        engine.declare(program, rules)
        shadows = tuple(
            engine.shadow(program.fingerprint, p.fingerprint, i, 120).fingerprint
            for p, outputs in ((champion, a), (challenger, b))
            for i in outputs
        )
        sample_ids = tuple(repo.get(PointForecast, i).input.sample_id for i in a)
        from afre.research_datasets.samples import ResearchSample

        evidence = EvaluationEvidence(
            program.fingerprint,
            shadows,
            tuple(
                (s.fingerprint, s.target_id)
                for s in (repo.get(ResearchSample, i) for i in sample_ids if i is not None)
                if s.target_id is not None
            ),
            120,
        )
        engine.evidence(evidence)
        from unittest.mock import patch

        from afre.selection import SelectionEngine

        with patch.object(
            SelectionEngine, "select", side_effect=AssertionError("challenge reran selection")
        ):
            run = engine.evaluate(evidence.fingerprint)
        assert challenger.selection_result_id is not None
        assert any(kind == "ResearchTrial" for _, kind, _, _ in records)
        assert any(kind == "HypothesisFamily" for _, kind, _, _ in records)
        from afre.multiple_testing import TestReuseDiagnostic, TestReuseStatus

        reuse_id = next(i for i, kind, _, _ in records if kind == "TestReuseDiagnostic")
        reuse = repo.resolve(TestReuseDiagnostic, reuse_id)
        assert reuse.use_count == 3 and reuse.status is TestReuseStatus.HEAVILY_REUSED
        assert engine.evaluate(evidence.fingerprint) == run
        assert repo.resolve(TestReuseDiagnostic, reuse_id) == reuse
        assert context_records(repo, tuple(i for i, _, _, _ in records)) == records
        assert run.action == "MANUAL_ONLY"

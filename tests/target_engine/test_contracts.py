from dataclasses import replace
from pathlib import Path

import pytest

from afre.datasets import AdjustmentBasis, AdjustmentPolicy
from afre.features import MissingState
from afre.ids import InstrumentId
from afre.persistence import ArtifactStore
from afre.schema import ContractError
from afre.serialization import canonical_json, deserialize
from afre.target_engine import (
    SuppliedBenchmarkReturn,
    TargetActionKind,
    TargetActionStream,
    TargetCorporateAction,
    TargetEndpointRules,
    TargetEngine,
    TargetPathPolicy,
    TargetRepository,
    TargetSetManifest,
)
from afre.target_engine.schema import (
    TargetAggregation,
    TargetEndpointPolicy,
    TargetOriginPolicy,
)
from afre.targets import TargetType
from afre.time import TimeRange
from examples.feature_store_demo import INPUT_ID, SECURITY, SOURCE, clocks
from examples.foundation_demo import build_demo
from examples.target_demo import BENCHMARK, bar, definition
from tests.target_engine.test_builders import append, build


def test_definition_identity_and_strict_policies() -> None:
    target = definition()
    alternatives = (
        replace(target, horizon=replace(target.horizon, duration_ns=5)),
        replace(
            target,
            endpoints=TargetEndpointRules(
                endpoint=TargetEndpointPolicy.FIRST_AT_OR_AFTER, endpoint_tolerance_ns=1
            ),
        ),
        replace(
            target,
            endpoints=TargetEndpointRules(
                origin=TargetOriginPolicy.FIRST_AFTER, origin_tolerance_ns=1
            ),
        ),
        replace(
            target, adjustment=AdjustmentPolicy(AdjustmentBasis.SPLIT_ADJUSTED, 0, INPUT_ID)
        ),
        replace(target, implementation_version="future-v2"),
    )
    assert len({target.fingerprint, *(t.fingerprint for t in alternatives)}) == 6
    assert deserialize(canonical_json(target)) == target
    with pytest.raises(ContractError):
        replace(target, aggregation=TargetAggregation.LOG)
    with pytest.raises(ContractError):
        replace(target, benchmark=BENCHMARK)
    with pytest.raises(ContractError):
        TargetEndpointRules(origin=TargetOriginPolicy.FIRST_AFTER)
    with pytest.raises(ContractError):
        TargetEndpointRules(origin_tolerance_ns=-1)
    with pytest.raises(ContractError):
        TargetPathPolicy(1, annualization_factor=0.0)
    with pytest.raises(ContractError):
        replace(
            definition(TargetType.MAX_ADVERSE_EXCURSION),
            path=TargetPathPolicy(1, annualization_factor=252.0),
        )
    with pytest.raises(ContractError):
        TargetSetManifest((target, alternatives[0]))


def test_source_revision_entity_and_window_compatibility(engine: TargetEngine) -> None:
    first = bar(5, 105.0)
    append(engine, first)
    for correction in (
        replace(
            first,
            instrument=InstrumentId("security", "other"),
            predecessor_id=first.fingerprint,
        ),
        replace(bar(6, 106.0), predecessor_id=first.fingerprint),
    ):
        with pytest.raises(ContractError, match="predecessor"):
            append(engine, correction)
    action = TargetCorporateAction(
        SECURITY,
        "split",
        3,
        TargetActionKind.SPLIT,
        2.0,
        INPUT_ID,
        clocks(7),
        SOURCE.provenance,
    )
    benchmark = SuppliedBenchmarkReturn(
        BENCHMARK, TimeRange(1, 5), 1, 5, 0.02, clocks(7), SOURCE.provenance
    )
    append(engine, action, benchmark)
    for source_correction in (
        replace(action, amount=3.0, clocks=clocks(8), predecessor_id=action.fingerprint),
        replace(benchmark, value=0.03, clocks=clocks(8), predecessor_id=benchmark.fingerprint),
    ):
        append(engine, source_correction)
    with pytest.raises(ContractError, match="predecessor"):
        append(engine, replace(action, event_id="different", predecessor_id=action.fingerprint))
    with pytest.raises(ContractError, match="predecessor"):
        append(
            engine,
            replace(benchmark, window=TimeRange(2, 5), predecessor_id=benchmark.fingerprint),
        )
    stream = TargetActionStream(
        INPUT_ID, "late-action", (action.fingerprint,), 0, 8, clocks(8), SOURCE.provenance
    )
    with pytest.raises(ContractError, match="future"):
        append(engine, replace(stream, clocks=clocks(6), complete_through_ns=6))


def test_correction_precedence_and_lineage_cycles(
    engine: TargetEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    append(engine, bar(1, 100.0))
    first = bar(5, 105.0, 7)
    second = replace(first, close=110.0, predecessor_id=first.fingerprint)
    third = replace(first, close=120.0, predecessor_id=second.fingerprint)
    append(engine, first, second, third)
    row = build(engine)
    assert row.value == pytest.approx(0.2)
    assert first in engine.repository.lineage(row.fingerprint)
    cycle = replace(third, predecessor_id=first.fingerprint)
    monkeypatch.setattr(engine.repository, "get_any", lambda identity: cycle)
    with pytest.raises(ContractError, match="cycle"):
        engine.repository.lineage(first.fingerprint)


def test_target_completion_and_invalid_state_checks(engine: TargetEngine) -> None:
    append(engine, bar(1, 100.0), bar(5, 105.0))
    row = build(engine)
    with pytest.raises(ContractError, match="completion"):
        replace(row, completion_ns=4)
    with pytest.raises(ContractError, match="value/absence"):
        replace(row, state=MissingState.MISSING)
    with pytest.raises(ContractError, match="builder"):
        replace(row, builder_version="wrong")
    with pytest.raises(ContractError, match="target origin/window"):
        replace(row, window=TimeRange(2, 5))


def test_direct_foundation_migration_preserves_payload(tmp_path: Path) -> None:
    path = tmp_path / "foundation.sqlite"
    legacy = replace(build_demo().row.dataset, engine_version="0.1.0")
    payload = canonical_json(legacy)
    with ArtifactStore(path) as repository, repository.transaction():
        repository.put(legacy)
    with TargetRepository(path) as upgraded:
        assert canonical_json(upgraded.get(type(legacy), legacy.fingerprint)) == payload
        assert upgraded.audit() == 1

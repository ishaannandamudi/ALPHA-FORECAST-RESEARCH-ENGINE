import math
from dataclasses import replace
from typing import Any

import pytest

from afre.datasets import AdjustmentBasis, AdjustmentPolicy
from afre.feature_store.providers import BarTimestampConvention
from afre.features import DataQuality, MissingState
from afre.schema import Artifact, ContractError
from afre.target_engine import (
    SuppliedBenchmarkReturn,
    TargetActionKind,
    TargetActionStream,
    TargetCalendar,
    TargetCorporateAction,
    TargetEndpointRules,
    TargetEngine,
    TargetPathPolicy,
    TargetSetManifest,
    TargetVintage,
    target_known_by_cutoff,
)
from afre.target_engine.schema import (
    TargetEndpointPolicy,
    TargetObservationState,
    TargetOriginPolicy,
    TargetPathRule,
    TargetQualityFlag,
)
from afre.targets import TargetType
from afre.time import DAY_NS, SECOND_NS, TimeRange
from examples.feature_store_demo import INPUT_ID, SECURITY, SOURCE, UNIVERSE, clocks, origin
from examples.target_demo import BENCHMARK, CALENDAR_TARGET, SOURCE_MARKET, bar, definition


def append(engine: TargetEngine, *values: Artifact) -> None:
    with engine.repository.transaction():
        for value in values:
            engine.repository.put(value)


def calendar(engine: TargetEngine) -> TargetCalendar:
    return replace(
        CALENDAR_TARGET,
        sessions=(replace(CALENDAR_TARGET.sessions[0], period=TimeRange(0, DAY_NS)),),
    )


def build(
    engine: TargetEngine,
    target: Any = None,
    at: int = 1,
    cutoff: int = 7,
    action_stream: TargetActionStream | None = None,
    benchmark_ids: tuple[str, ...] = (),
) -> TargetVintage:
    target = definition() if target is None else target
    source = engine.freeze_source(
        SOURCE_MARKET, calendar(engine), cutoff, action_stream, benchmark_ids
    )
    manifest = engine.build_dataset(
        "test-targets",
        (origin(at),),
        TargetSetManifest((target,)),
        source.fingerprint,
        UNIVERSE,
        clocks(cutoff),
    )
    return engine.rows(manifest)[0]


@pytest.mark.parametrize(
    "kind,expected",
    [
        (TargetType.SIMPLE_RETURN, 0.05),
        (TargetType.LOG_RETURN, math.log(1.05)),
        (TargetType.ABSOLUTE_RETURN, 0.05),
        (TargetType.DOWNSIDE_RETURN, 0.0),
        (TargetType.MAX_ADVERSE_EXCURSION, -0.02),
        (TargetType.MAX_FAVORABLE_EXCURSION, 0.05),
    ],
)
def test_deterministic_target_types(
    engine: TargetEngine, kind: TargetType, expected: float
) -> None:
    append(
        engine,
        *(
            bar(at, price)
            for at, price in ((1, 100.0), (2, 102.0), (3, 98.0), (4, 104.0), (5, 105.0))
        ),
    )
    value = build(engine, definition(kind))
    assert value.value == pytest.approx(expected)
    assert value.window == TimeRange(1, 5)
    assert not target_known_by_cutoff(value, 1)
    assert not target_known_by_cutoff(value, 6)
    assert target_known_by_cutoff(value, 7)
    audit = engine.audit_target(value.fingerprint)
    assert value.definition.fingerprint in audit.lineage_ids
    engine.audit()


def test_realized_volatility_sampling_annualization_and_no_gap_bridge(
    engine: TargetEngine,
) -> None:
    append(engine, bar(1, 100.0), bar(2, 110.0), bar(3, 121.0), bar(4, 121.0), bar(5, 121.0))
    target = definition(TargetType.REALIZED_VOLATILITY)
    value = build(engine, target)
    expected = math.sqrt(2 * math.log(1.1) ** 2)
    assert value.value == pytest.approx(expected)
    assert target.path is not None
    annualized = replace(
        target, name="target.annualized", path=replace(target.path, annualization_factor=4.0)
    )
    assert build(engine, annualized).value == pytest.approx(expected * 2)
    # Missing interval breaks the chain; an explicit partial policy does not span that gap.
    missing = replace(
        bar(3, 121.0), close=None, state=TargetObservationState.MISSING, clocks=clocks(8)
    )
    append(engine, missing)
    partial = replace(
        target,
        name="target.partial_vol",
        path=TargetPathPolicy(1, 1, TargetPathRule.MINIMUM_COVERAGE, 0.5),
    )
    assert build(engine, target, cutoff=8).state is MissingState.MISSING
    result = build(engine, partial, cutoff=8)
    assert result.value == pytest.approx(abs(math.log(1.1)))
    assert TargetQualityFlag.PARTIAL_PATH in result.quality.flags
    assert not target_known_by_cutoff(result, 8)


def test_endpoint_delivery_latency_and_exact_same_time_training(engine: TargetEngine) -> None:
    ten = 10 * 3600 * SECOND_NS
    eleven = ten + 3600 * SECOND_NS
    append(engine, bar(ten, 100.0, ten), bar(eleven, 105.0, eleven + 2 * SECOND_NS))
    target = definition(horizon_ns=3600 * SECOND_NS)
    at_origin = build(engine, target, ten, ten)
    assert at_origin.state is MissingState.NOT_AVAILABLE_YET
    before_delivery = build(engine, target, ten, eleven + SECOND_NS)
    assert before_delivery.value is None
    available = build(engine, target, ten, eleven + 2 * SECOND_NS)
    assert available.completion_ns == eleven + 2 * SECOND_NS
    assert not target_known_by_cutoff(available, eleven + SECOND_NS)
    assert target_known_by_cutoff(available, eleven + 2 * SECOND_NS)
    assert available.clocks.afre_received_ns == eleven + 2 * SECOND_NS


@pytest.mark.parametrize(
    "policy,end,tolerance,expected",
    [
        (TargetEndpointPolicy.EXACT, 4, 0, None),
        (TargetEndpointPolicy.LAST_AT_OR_BEFORE, 4, 1, 0.04),
        (TargetEndpointPolicy.FIRST_AT_OR_AFTER, 6, 1, 0.06),
        (TargetEndpointPolicy.FIRST_AT_OR_AFTER, 7, 1, None),
    ],
)
def test_explicit_endpoint_tolerance(
    engine: TargetEngine,
    policy: TargetEndpointPolicy,
    end: int,
    tolerance: int,
    expected: float | None,
) -> None:
    append(engine, bar(1, 100.0), bar(end, 100.0 + end))
    target = replace(
        definition(),
        endpoints=TargetEndpointRules(endpoint=policy, endpoint_tolerance_ns=tolerance),
    )
    value = build(engine, target, cutoff=8)
    if expected is None:
        assert value.state is MissingState.MISSING
    else:
        assert value.value == pytest.approx(expected)
        assert TargetQualityFlag.TOLERATED_ENDPOINT in value.quality.flags
        assert value.completion_ns == max(5, end)


@pytest.mark.parametrize(
    "policy,start,tolerance",
    [
        (TargetOriginPolicy.LAST_AT_OR_BEFORE, 1, 1),
        (TargetOriginPolicy.FIRST_AFTER, 3, 1),
    ],
)
def test_origin_selection_is_separate_from_future_window(
    engine: TargetEngine, policy: TargetOriginPolicy, start: int, tolerance: int
) -> None:
    append(engine, bar(start, 100.0), bar(6, 105.0))
    target = replace(
        definition(),
        endpoints=TargetEndpointRules(origin=policy, origin_tolerance_ns=tolerance),
    )
    result = build(engine, target, at=2, cutoff=7)
    assert result.window == TimeRange(2, 6)
    assert result.value == pytest.approx(0.05)
    assert TargetQualityFlag.TOLERATED_ORIGIN in result.quality.flags


def test_supplied_benchmark_alignment_and_later_availability(engine: TargetEngine) -> None:
    append(engine, bar(1, 100.0), bar(5, 105.0))
    supplied = SuppliedBenchmarkReturn(
        BENCHMARK, TimeRange(1, 5), 1, 5, 0.02, clocks(9), SOURCE.provenance
    )
    append(engine, supplied)
    missing = build(engine, definition(TargetType.RESIDUAL_RETURN), cutoff=7)
    assert missing.state is MissingState.MISSING
    result = build(
        engine,
        definition(TargetType.RESIDUAL_RETURN),
        cutoff=9,
        benchmark_ids=(supplied.fingerprint,),
    )
    assert result.value == pytest.approx(0.03)
    assert result.completion_ns == 9
    assert not target_known_by_cutoff(result, 8)
    assert target_known_by_cutoff(result, 9)
    wrong = replace(supplied, origin_price_ns=0)
    append(engine, wrong)
    assert (
        build(
            engine,
            definition(TargetType.RESIDUAL_RETURN),
            cutoff=9,
            benchmark_ids=(wrong.fingerprint,),
        ).state
        is MissingState.MISSING
    )
    with pytest.raises(ContractError):
        build(
            engine,
            definition(TargetType.RESIDUAL_RETURN),
            cutoff=8,
            benchmark_ids=(supplied.fingerprint,),
        )


def test_split_and_explicit_action_streams_pin_knowledge(engine: TargetEngine) -> None:
    append(engine, bar(1, 100.0), bar(5, 50.0))
    split = TargetCorporateAction(
        SECURITY,
        "split-v1",
        3,
        TargetActionKind.SPLIT,
        2.0,
        INPUT_ID,
        clocks(8),
        SOURCE.provenance,
    )
    stream = TargetActionStream(
        INPUT_ID, "actions-v1", (split.fingerprint,), 0, 5, clocks(8), SOURCE.provenance
    )
    append(engine, split, stream)
    raw = build(engine, cutoff=8)
    adjusted = replace(
        definition(adjustment=AdjustmentPolicy(AdjustmentBasis.SPLIT_ADJUSTED, 8, INPUT_ID)),
        name="target.split",
    )
    result = build(engine, adjusted, cutoff=8, action_stream=stream)
    assert result.completion_ns == 8
    assert raw.value == -0.5 and result.value == 0.0
    assert raw.fingerprint != result.fingerprint and result.action_ids == (split.fingerprint,)
    assert not target_known_by_cutoff(result, 7)
    assert build(engine, adjusted, cutoff=8).state is MissingState.MISSING
    partial = replace(stream, complete_through_ns=4)
    append(engine, partial)
    assert (
        build(engine, adjusted, cutoff=8, action_stream=partial).state
        is MissingState.NOT_AVAILABLE_YET
    )
    factor = replace(split, event_id="factor-v1", kind=TargetActionKind.PRICE_FACTOR)
    explicit_stream = replace(stream, action_ids=(factor.fingerprint,))
    append(engine, factor, explicit_stream)
    explicit = replace(
        adjusted,
        name="target.explicit",
        adjustment=replace(
            adjusted.adjustment, basis=AdjustmentBasis.EXPLICIT_ADJUSTMENT_STREAM
        ),
    )
    assert build(engine, explicit, cutoff=8, action_stream=explicit_stream).value == 0.0
    with pytest.raises(ContractError):
        build(engine, adjusted, cutoff=8, action_stream=explicit_stream)
    with pytest.raises(ContractError):
        build(engine, explicit, cutoff=8, action_stream=stream)
    with pytest.raises(ContractError, match="contract-only"):
        build(
            engine,
            replace(
                adjusted,
                name="target.total_return",
                adjustment=replace(adjusted.adjustment, basis=AdjustmentBasis.TOTAL_RETURN),
            ),
            cutoff=8,
            action_stream=stream,
        )
    engine.audit()


@pytest.mark.parametrize(
    "state",
    [
        TargetObservationState.MISSING,
        TargetObservationState.HALTED,
        TargetObservationState.DELISTED,
        TargetObservationState.NONPOSITIVE_PRICE,
    ],
)
def test_missing_delisting_halt_and_zero_are_not_dropped(
    engine: TargetEngine, state: TargetObservationState
) -> None:
    endpoint = replace(
        bar(5, 100.0),
        close=0.0 if state is TargetObservationState.NONPOSITIVE_PRICE else None,
        state=state,
        quality=DataQuality.INVALID,
    )
    append(engine, bar(1, 100.0), endpoint)
    value = build(engine)
    assert value.value is None
    assert value.state is (
        MissingState.INVALID
        if state is TargetObservationState.NONPOSITIVE_PRICE
        else MissingState.MISSING
    )
    assert not target_known_by_cutoff(value, 100)


def test_bar_conventions_revisions_conflicts_and_old_source_build(engine: TargetEngine) -> None:
    first = bar(1, 100.0)
    endpoint = bar(5, 105.0)
    append(engine, first, endpoint)
    old = build(engine)
    conflicting = replace(endpoint, close=106.0)
    append(engine, conflicting)
    with pytest.raises(ContractError, match="precedence"):
        build(engine)
    corrected = replace(conflicting, predecessor_id=endpoint.fingerprint, clocks=clocks(8))
    append(engine, corrected)
    assert build(engine, cutoff=8).value == pytest.approx(0.06)
    assert engine.repository.get(TargetVintage, old.fingerprint) == old
    for convention in BarTimestampConvention:
        time = (
            endpoint.period.start_ns
            if convention is BarTimestampConvention.OPEN
            else endpoint.period.end_ns
        )
        assert (
            replace(endpoint, timestamp_convention=convention, timestamp_ns=time).period.end_ns
            == 5
        )
    with pytest.raises(ContractError):
        replace(endpoint, close=0.0)
    with pytest.raises(ContractError):
        replace(endpoint, clocks=clocks(4))


@pytest.mark.parametrize(
    "changes",
    [
        {"name": "market.return"},
        {"implementation_version": "untrusted"},
        {"parameters": ()},
    ],
)
def test_definition_identity_and_builder_version(
    engine: TargetEngine, changes: dict[str, Any]
) -> None:
    if changes == {"parameters": ()}:
        from afre.lineage import Parameter

        changes = {"parameters": (Parameter("secret_parameter", 1),)}
    with pytest.raises(ContractError):
        build(engine, replace(definition(), **changes))

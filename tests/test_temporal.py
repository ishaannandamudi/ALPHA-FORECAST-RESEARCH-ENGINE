from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, cast

import pytest

from afre.datasets import ForecastFeatureRow, SymbolMapping, UniversePolicy, resolve_symbol
from afre.features import (
    AvailabilityRule,
    DataQuality,
    FeatureScope,
    MissingPolicy,
    MissingState,
    ValueType,
)
from afre.horizons import ForecastHorizon, HorizonBasis
from afre.ids import InstrumentId
from afre.lineage import FeatureDependency, FeatureLineage, ReconstructionProof
from afre.schema import ContractError
from afre.targets import TargetSpec, TargetType
from afre.time import DAY_NS, TimeRange, datetime_to_ns, ns_to_datetime, validate_timestamp
from afre.validation import validate_training_pair
from examples.foundation_demo import Demo


@pytest.mark.parametrize("timestamp", [-1, 2**63, True, 1.0, "1"])
def test_invalid_timestamps(timestamp: Any) -> None:
    with pytest.raises(ContractError):
        validate_timestamp(timestamp)


def test_exact_time_conversion() -> None:
    value = datetime(2026, 1, 5, 9, 30, 1, 123456, tzinfo=timezone(timedelta(hours=-5)))
    assert ns_to_datetime(datetime_to_ns(value)) == value.astimezone(UTC)
    assert datetime_to_ns(datetime(1970, 1, 1, tzinfo=UTC)) == 0
    for bad in (datetime(2026, 1, 1), datetime(1969, 1, 1, tzinfo=UTC)):
        with pytest.raises(ContractError):
            datetime_to_ns(bad)
    with pytest.raises(ContractError, match="lose nanoseconds"):
        ns_to_datetime(1)


@pytest.mark.parametrize("start,end", [(5, 5), (5, 4), (-1, 4), (0, 2**63)])
def test_invalid_ranges(start: int, end: int) -> None:
    with pytest.raises(ContractError):
        TimeRange(start, end)


def test_half_open_range() -> None:
    interval = TimeRange(4, 9)
    assert interval.contains(4)
    assert interval.contains(8)
    assert not interval.contains(9)
    assert not interval.contains(3)


@pytest.mark.parametrize(
    "changes",
    [
        {"duration_ns": 0},
        {"duration_ns": None},
        {"duration_ns": -1},
        {"count": 1},
        {"calendar_id": "x"},
        {"bar_definition": "x"},
        {"basis": "elapsed_time"},
    ],
)
def test_invalid_elapsed_horizon(demo: Demo, changes: dict[str, Any]) -> None:
    with pytest.raises(ContractError):
        replace(demo.target.target.horizon, **changes)


@pytest.mark.parametrize("basis", [HorizonBasis.TRADING_SESSIONS, HorizonBasis.BARS])
def test_session_bar_contracts(basis: HorizonBasis) -> None:
    kwargs: dict[str, Any] = {"calendar_id": "exchange-calendar-v1", "count": 5}
    if basis is HorizonBasis.BARS:
        kwargs["bar_definition"] = "5m-price-bars-v1"
    horizon = ForecastHorizon(basis, **kwargs)
    for invalid in ({"count": 0}, {"count": None}, {"duration_ns": 1}, {"calendar_id": None}):
        with pytest.raises(ContractError):
            replace(horizon, **invalid)
    with pytest.raises(ContractError):
        replace(horizon, bar_definition=None if basis is HorizonBasis.BARS else "ambiguous")


def test_availability_equality_and_rejection(demo: Demo) -> None:
    assert demo.features[0].available_ns == demo.origin.timestamp_ns
    assert ForecastFeatureRow(demo.origin, demo.row.dataset, demo.features) == demo.row
    for change in (
        {"available_ns": demo.origin.timestamp_ns + 1},
        {"instrument": InstrumentId("synthetic-security", "other")},
    ):
        future = replace(demo.features[0], **change)
        with pytest.raises(ContractError):
            replace(demo.row, features=(future, demo.features[1]))
    with pytest.raises(ContractError):
        replace(demo.origin, availability_cutoff_ns=demo.origin.timestamp_ns + 1)
    earlier_cutoff = replace(demo.origin, availability_cutoff_ns=demo.origin.timestamp_ns - 1)
    with pytest.raises(ContractError):
        replace(demo.row, origin=earlier_cutoff)
    # Scheduled facts may have a future effective time while being known at T.
    scheduled = replace(demo.features[0], effective_ns=demo.origin.timestamp_ns + DAY_NS)
    replace(demo.row, features=(scheduled, demo.features[1]))


def test_derived_availability_and_reconstruction(demo: Demo) -> None:
    source = demo.features[0]
    dependency = FeatureDependency(
        source.definition.fingerprint, source.fingerprint, source.available_ns
    )
    definition = replace(
        source.definition,
        name="derived",
        availability_rule=AvailabilityRule.COMPUTED,
        dependency_ids=(dependency.definition_id,),
        transformation_version="derived-v1",
    )
    computation = source.available_ns + 10
    lineage = FeatureLineage((), (dependency,), "derived-v1", (), "build", "code", computation)
    derived = replace(source, definition=definition, lineage=lineage, available_ns=computation)
    assert derived.lineage.availability_floor_ns == computation
    for available in (source.available_ns - 1, computation - 1):
        with pytest.raises(ContractError, match="backdated"):
            replace(derived, available_ns=available)
    with pytest.raises(ContractError):
        replace(lineage, computation_available_ns=None)
    with pytest.raises(ContractError):
        replace(definition, dependency_ids=())
    with pytest.raises(ContractError):
        replace(source.definition, dependency_ids=(dependency.definition_id,))
    with pytest.raises(ContractError):
        replace(definition, dependency_ids=(dependency.definition_id,) * 2)
    proof = ReconstructionProof(source.lineage.upstream[0], computation, computation + DAY_NS)
    reconstructed = replace(
        lineage, computation_available_ns=proof.reconstructed_ns, reconstruction=proof
    )
    assert replace(derived, lineage=reconstructed).available_ns == computation
    with pytest.raises(ContractError):
        replace(proof, historical_computation_available_ns=proof.reconstructed_ns + 1)
    with pytest.raises(ContractError):
        replace(reconstructed, computation_available_ns=proof.reconstructed_ns - 1)
    with pytest.raises(ContractError):
        replace(source.lineage, upstream=())


@pytest.mark.parametrize(
    "changes",
    [
        {"observed_ns": 11 * DAY_NS},
        {"value": None},
        {"value": float("nan")},
        {"value": float("inf")},
        {"value": True},
        {"quality": DataQuality.INVALID},
        {"source": ""},
        {"source_version": "\n"},
    ],
)
def test_invalid_feature_value(demo: Demo, changes: dict[str, Any]) -> None:
    with pytest.raises(ContractError):
        replace(demo.features[0], **changes)


@pytest.mark.parametrize(
    "state", [state for state in MissingState if state is not MissingState.PRESENT]
)
def test_missing_states_are_not_zero(demo: Demo, state: MissingState) -> None:
    missing = replace(demo.features[0], value=None, missing_state=state)
    assert missing.value is None
    assert missing.fingerprint != replace(
        missing, missing_state=MissingState.UNKNOWN
    ).fingerprint or (state is MissingState.UNKNOWN)
    with pytest.raises(ContractError):
        replace(missing, value=0)
    with pytest.raises(ContractError):
        replace(
            missing, definition=replace(missing.definition, missing_policy=MissingPolicy.REJECT)
        )


@pytest.mark.parametrize(
    "value_type,value",
    [
        (ValueType.INTEGER, 2),
        (ValueType.BOOLEAN, True),
        (ValueType.TEXT, "scheduled"),
        (ValueType.NUMBER, 0),
    ],
)
def test_typed_values(demo: Demo, value_type: ValueType, value: Any) -> None:
    definition = replace(
        demo.features[0].definition, value_type=value_type, scope=FeatureScope.ENTITY
    )
    assert replace(demo.features[0], definition=definition, value=value).value == value


def test_feature_target_namespaces(demo: Demo) -> None:
    with pytest.raises(ContractError, match="wrong contract type"):
        replace(demo.features[0], value=cast(Any, demo.target))
    with pytest.raises(ContractError, match="namespace"):
        FeatureDependency(demo.target.target.fingerprint, demo.target.fingerprint, 0)
    with pytest.raises(ContractError):
        replace(demo.features[0].definition, dependency_ids=(demo.target.fingerprint,))
    with pytest.raises(ContractError):
        replace(demo.row, features=cast(Any, (demo.target, demo.features[1])))


def test_target_completion_and_training(demo: Demo) -> None:
    assert not demo.target.eligible_at(demo.target.window.end_ns - 1)
    assert not demo.target.eligible_at(demo.target.window.end_ns)
    assert demo.target.eligible_at(demo.target.available_ns)
    validate_training_pair(demo.row, demo.target, demo.target.available_ns)
    with pytest.raises(ContractError, match="excluded"):
        validate_training_pair(demo.row, demo.target, demo.target.window.end_ns)
    assert not replace(demo.target, quality=DataQuality.UNVERIFIED).eligible_at(20 * DAY_NS)
    invalid = replace(demo.target, value=None, quality=DataQuality.INVALID)
    assert not invalid.eligible_at(20 * DAY_NS)
    with pytest.raises(ContractError):
        replace(demo.target, available_ns=demo.target.window.end_ns - 1)
    with pytest.raises(ContractError):
        replace(demo.target, window=TimeRange(10 * DAY_NS, 12 * DAY_NS))
    with pytest.raises(ContractError):
        replace(demo.target, window=TimeRange(9 * DAY_NS, 11 * DAY_NS))
    with pytest.raises(ContractError):
        replace(demo.target, value=None)
    with pytest.raises(ContractError):
        validate_training_pair(
            demo.row,
            replace(demo.target, origin=replace(demo.origin, build_context="other")),
            20 * DAY_NS,
        )
    with pytest.raises(ContractError):
        validate_training_pair(
            demo.row,
            replace(
                demo.target, target=replace(demo.target.target, implementation_version="other")
            ),
            20 * DAY_NS,
        )
    with pytest.raises(ContractError):
        validate_training_pair(
            demo.row,
            replace(demo.target, market_dataset_id=demo.instrument.fingerprint),
            20 * DAY_NS,
        )


def test_session_target_requires_endpoint_evidence(demo: Demo) -> None:
    horizon = ForecastHorizon(HorizonBasis.TRADING_SESSIONS, count=1, calendar_id="calendar-v1")
    target = replace(demo.target.target, horizon=horizon)
    with pytest.raises(ContractError):
        replace(demo.target, target=target)
    session_row = replace(demo.target, target=target, endpoint_evidence_id=horizon.fingerprint)
    assert session_row.target == target
    with pytest.raises(ContractError):
        replace(session_row, endpoint_evidence_id="bad")


def test_target_benchmark_semantics(demo: Demo) -> None:
    for kind in TargetType:
        target = TargetSpec(
            kind,
            demo.target.target.horizon,
            "ratio",
            "v1",
            demo.instrument if kind is TargetType.RESIDUAL_RETURN else None,
        )
        assert target.target_type is kind
    with pytest.raises(ContractError):
        replace(demo.target.target, benchmark=demo.instrument)
    with pytest.raises(ContractError):
        replace(demo.target.target, target_type=TargetType.RESIDUAL_RETURN)


def test_historical_membership_and_survivorship(demo: Demo) -> None:
    universe = demo.row.dataset.universe
    member = universe.memberships[0]
    for changed in (
        replace(member, known_ns=demo.origin.timestamp_ns + 1),
        replace(member, validity=TimeRange(0, demo.origin.timestamp_ns)),
        replace(member, instrument=InstrumentId("security", "other")),
    ):
        future_universe = replace(universe, memberships=(changed,))
        origin = replace(demo.origin, universe_id=future_universe.fingerprint)
        dataset = replace(demo.row.dataset, universe=future_universe)
        with pytest.raises(ContractError, match="historical universe"):
            replace(demo.row, origin=origin, dataset=dataset)
    with pytest.raises(ContractError):
        replace(universe, policy=UniversePolicy.CURRENT_CONSTITUENTS)
    assert (
        replace(universe, policy=UniversePolicy.FIXED_COHORT).policy
        is UniversePolicy.FIXED_COHORT
    )
    with pytest.raises(ContractError):
        universe.eligible(
            replace(demo.origin, universe_id=replace(universe, name="x").fingerprint)
        )
    with pytest.raises(ContractError):
        replace(universe, memberships=())


def test_ticker_reuse_does_not_merge(demo: Demo) -> None:
    new_security = InstrumentId("synthetic-security", "0002")
    mappings = (
        SymbolMapping("ABC", "X", demo.instrument, TimeRange(0, 10), 0),
        SymbolMapping("ABC", "X", new_security, TimeRange(10, 20), 10),
    )
    assert resolve_symbol(mappings, "ABC", "X", 9, 9) == demo.instrument
    assert resolve_symbol(mappings, "ABC", "X", 10, 10) == new_security
    for valid, known in ((10, 9), (20, 30)):
        with pytest.raises(ContractError):
            resolve_symbol(mappings, "ABC", "X", valid, known)
    with pytest.raises(ContractError):
        resolve_symbol(
            mappings + (replace(mappings[1], instrument=demo.instrument),), "ABC", "X", 10, 10
        )
    assert demo.instrument.fingerprint != new_security.fingerprint


def test_row_completeness_and_immutability(demo: Demo) -> None:
    for features in (
        (),
        (demo.features[0],),
        (demo.features[0],) * 2,
        (
            replace(
                demo.features[0], definition=replace(demo.features[0].definition, name="x")
            ),
            demo.features[1],
        ),
    ):
        with pytest.raises(ContractError):
            replace(demo.row, features=features)
    with pytest.raises(ContractError):
        replace(demo.row, origin=replace(demo.origin, timestamp_ns=50 * DAY_NS))
    with pytest.raises(FrozenInstanceError):
        demo.features[0].value = 0  # type: ignore[misc]
    with pytest.raises(ContractError):
        replace(demo.row, features=cast(Any, list(demo.features)))
    with pytest.raises(ContractError):
        replace(
            demo.features[0],
            lineage=replace(demo.features[0].lineage, transformation_version="other"),
        )


def test_target_provenance_is_rejected(demo: Demo) -> None:
    for identity in (demo.target.fingerprint, demo.target.target.fingerprint):
        provenance = replace(demo.features[0].lineage.upstream[0], artifact_id=identity)
        with pytest.raises(ContractError, match="target artifacts"):
            replace(demo.features[0].lineage, upstream=(provenance,))

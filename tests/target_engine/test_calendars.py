from dataclasses import replace

import pytest

from afre.datasets import SymbolMapping, UniverseMembership, resolve_symbol
from afre.features import MissingState
from afre.horizons import ForecastHorizon, HorizonBasis
from afre.ids import InstrumentId
from afre.schema import ContractError
from afre.target_engine import TargetEngine, TargetPathPolicy, TargetSession, TargetSetManifest
from afre.target_engine.schema import TargetEndpointPolicy, TargetSessionPolicy
from afre.targets import TargetType
from afre.time import DAY_NS, TimeRange
from examples.feature_store_demo import SECURITY, UNIVERSE, clocks, origin
from examples.target_demo import CALENDAR_TARGET, SOURCE_MARKET, bar, definition
from tests.target_engine.test_builders import append, build


def test_weekend_holiday_short_session_and_explicit_extended(engine: TargetEngine) -> None:
    # Friday, Monday holiday, Tuesday short session, Wednesday regular/extended.
    friday = TargetSession("friday", TimeRange(10, 20))
    tuesday = TargetSession("tuesday-half-day", TimeRange(4 * DAY_NS + 10, 4 * DAY_NS + 15))
    wednesday = TargetSession("wednesday", TimeRange(5 * DAY_NS + 10, 5 * DAY_NS + 20))
    extended = TargetSession("postmarket", TimeRange(5 * DAY_NS + 20, 5 * DAY_NS + 25), True)
    calendar = replace(CALENDAR_TARGET, sessions=(friday, tuesday, wednesday, extended))
    universe = replace(
        UNIVERSE,
        memberships=(replace(UNIVERSE.memberships[0], validity=TimeRange(0, 6 * DAY_NS)),),
    )
    at = replace(origin(20), market_session_id="friday", universe_id=universe.fingerprint)
    append(
        engine,
        calendar,
        *(
            replace(bar(t, p), session_id=s)
            for t, p, s in (
                (20, 100.0, "friday"),
                (4 * DAY_NS + 15, 105.0, "tuesday-half-day"),
                (5 * DAY_NS + 20, 110.0, "wednesday"),
                (5 * DAY_NS + 25, 112.0, "postmarket"),
            )
        ),
    )
    cutoff = 6 * DAY_NS
    source = engine.freeze_source(SOURCE_MARKET, calendar, cutoff)

    session = replace(
        definition(),
        horizon=ForecastHorizon(
            HorizonBasis.TRADING_SESSIONS, count=1, calendar_id=calendar.calendar_id
        ),
    )
    manifest = engine.build_dataset(
        "sessions",
        (at,),
        TargetSetManifest((session,)),
        source.fingerprint,
        universe,
        clocks(cutoff),
    )
    row = engine.rows(manifest)[0]
    assert row.window == TimeRange(20, 4 * DAY_NS + 15)
    assert row.value == pytest.approx(0.05)
    # Elapsed Saturday endpoint never substitutes Friday unless explicitly allowed.
    elapsed = replace(definition(horizon_ns=DAY_NS), name="target.weekend")
    manifest = engine.build_dataset(
        "weekend",
        (at,),
        TargetSetManifest((elapsed,)),
        source.fingerprint,
        universe,
        clocks(cutoff),
    )
    assert engine.rows(manifest)[0].state is MissingState.MISSING
    tolerant = replace(
        elapsed,
        name="target.weekend_tolerant",
        endpoints=replace(
            elapsed.endpoints,
            endpoint=TargetEndpointPolicy.LAST_AT_OR_BEFORE,
            endpoint_tolerance_ns=DAY_NS,
        ),
    )
    manifest = engine.build_dataset(
        "weekend-tolerant",
        (at,),
        TargetSetManifest((tolerant,)),
        source.fingerprint,
        universe,
        clocks(cutoff),
    )
    assert engine.rows(manifest)[0].value is None
    assert "no positive outcome interval" in engine.rows(manifest)[0].reason
    # Explicit regular vs extended session counting reaches different closes.
    next_origin = replace(
        at,
        timestamp_ns=5 * DAY_NS + 20,
        availability_cutoff_ns=5 * DAY_NS + 20,
        market_session_id="wednesday",
    )
    regular = replace(session, name="target.regular")
    inclusive = replace(
        session, name="target.extended", session_policy=TargetSessionPolicy.INCLUDE_EXTENDED
    )
    manifest = engine.build_dataset(
        "extended",
        (next_origin,),
        TargetSetManifest((regular, inclusive)),
        source.fingerprint,
        universe,
        clocks(cutoff),
    )
    rows = {r.definition.name: r for r in engine.rows(manifest)}
    assert rows[regular.name].state is MissingState.NOT_AVAILABLE_YET
    assert rows[inclusive.name].window == TimeRange(
        next_origin.timestamp_ns, extended.period.end_ns
    )
    assert rows[inclusive.name].value == pytest.approx(112 / 110 - 1)
    assert calendar.expected_closes(
        wednesday.period.start_ns, extended.period.end_ns, 5, False, 10
    ) == (5 * DAY_NS + 15, 5 * DAY_NS + 20)
    bad_origin = replace(at, market_session_id="missing-session")
    with pytest.raises(ContractError, match="declared target session"):
        engine.build_dataset(
            "bad",
            (bad_origin,),
            TargetSetManifest((session,)),
            source.fingerprint,
            universe,
            clocks(cutoff),
        )


def test_bar_horizon_counts_declared_completed_observations(engine: TargetEngine) -> None:
    append(engine, bar(1, 100.0), bar(3, 102.0), bar(9, 105.0))
    target = replace(
        definition(),
        horizon=ForecastHorizon(
            HorizonBasis.BARS,
            count=2,
            calendar_id=SOURCE_MARKET.calendar_id,
            bar_definition=SOURCE_MARKET.bar_definition,
        ),
    )
    row = build(engine, target, cutoff=10)
    assert row.window == TimeRange(1, 9)
    assert row.value == pytest.approx(0.05)
    assert build(engine, target, cutoff=5).state is MissingState.NOT_AVAILABLE_YET


def test_path_sampling_phase_and_closed_periods(engine: TargetEngine) -> None:
    append(engine, *(bar(n, 100.0 + n) for n in range(1, 7)))
    target = replace(definition(TargetType.REALIZED_VOLATILITY), path=TargetPathPolicy(2))
    with pytest.raises(ContractError, match="sampling grid"):
        build(engine, target)
    result = build(engine, target, at=2, cutoff=7)
    assert result.value is not None and len(result.path_ids) == 2
    calendar = replace(
        CALENDAR_TARGET,
        sessions=(TargetSession("a", TimeRange(0, 3)), TargetSession("b", TimeRange(10, 14))),
    )
    assert calendar.expected_closes(2, 14, 1, False, 10) == (3, 11, 12, 13, 14)
    with pytest.raises(ContractError, match="overlapping"):
        replace(
            calendar,
            sessions=(TargetSession("a", TimeRange(0, 3)), TargetSession("b", TimeRange(2, 4))),
        )


def test_reused_symbol_never_joins_distinct_security_ids(engine: TargetEngine) -> None:
    other = InstrumentId("synthetic-security", "second-listing")
    mappings = (
        SymbolMapping("REUSED", "X", SECURITY, TimeRange(0, 4), 0),
        SymbolMapping("REUSED", "X", other, TimeRange(4, 10), 0),
    )
    assert resolve_symbol(mappings, "REUSED", "X", 1, 1) == SECURITY
    assert resolve_symbol(mappings, "REUSED", "X", 5, 5) == other
    universe = replace(
        UNIVERSE,
        memberships=(
            *UNIVERSE.memberships,
            UniverseMembership(other, TimeRange(0, 10), 0, "synthetic"),
        ),
    )
    append(
        engine,
        bar(1, 100.0),
        bar(5, 105.0),
        replace(bar(1, 50.0), instrument=other),
        replace(bar(5, 40.0), instrument=other),
    )
    source = engine.freeze_source(SOURCE_MARKET, CALENDAR_TARGET, 7)
    origins = tuple(
        replace(origin(1, security), universe_id=universe.fingerprint)
        for security in (SECURITY, other)
    )
    manifest = engine.build_dataset(
        "reuse",
        origins,
        TargetSetManifest((definition(),)),
        source.fingerprint,
        universe,
        clocks(7),
    )
    rows = {r.origin.instrument: r for r in engine.rows(manifest)}
    assert rows[SECURITY].value == pytest.approx(0.05)
    assert rows[other].value == pytest.approx(-0.2)
    assert engine.targets_known_by(7, manifest.targets, instruments=(other,)) == (rows[other],)

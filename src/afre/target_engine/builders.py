"""Deterministic target construction from a pinned source build only."""

import math

from afre.datasets import AdjustmentBasis
from afre.feature_store.models import AvailabilityEvidence
from afre.feature_store.schema import AvailabilityMode
from afre.features import DataQuality, MissingState
from afre.forecast import ForecastOrigin
from afre.horizons import HorizonBasis
from afre.schema import ContractError, require
from afre.target_engine.corporate_actions import TargetCorporateAction, adjusted_price
from afre.target_engine.definitions import TargetDefinition
from afre.target_engine.market_data import TargetBar, TargetSourceBuild
from afre.target_engine.models import TargetVintage
from afre.target_engine.quality import TargetQuality
from afre.target_engine.repository import TargetRepository
from afre.target_engine.residuals import SuppliedBenchmarkReturn
from afre.target_engine.schema import (
    BUILDER_VERSION,
    TargetAggregation,
    TargetEndpointPolicy,
    TargetObservationState,
    TargetOriginPolicy,
    TargetPathRule,
    TargetQualityFlag,
    TargetSessionPolicy,
)
from afre.time import MAX_TIMESTAMP_NS, TimeRange


class TargetSourceConflict(ContractError):
    """Incompatible equal-precedence source records require an explicit revision."""


def latest_sources(
    repository: TargetRepository, values: tuple[TargetBar, ...]
) -> tuple[TargetBar, ...]:
    groups: dict[int, list[TargetBar]] = {}
    for value in values:
        groups.setdefault(value.period.end_ns, []).append(value)
    selected: list[TargetBar] = []
    for end_ns in sorted(groups):
        group = groups[end_ns]
        latest = max(item.clocks.final_available_ns for item in group)
        candidates = {
            item.fingerprint: item for item in group if item.clocks.final_available_ns == latest
        }
        superseded: set[str] = set()
        for candidate in candidates.values():
            current = candidate.predecessor_id
            seen: set[str] = set()
            while current is not None:
                require(current not in seen, "target source revision cycle")
                require(
                    len(seen) < repository.target_bounds.lineage_depth,
                    "target revision depth bound",
                )
                seen.add(current)
                if current in candidates:
                    superseded.add(current)
                current = repository.resolve(TargetBar, current).predecessor_id
        winners = [item for key, item in candidates.items() if key not in superseded]
        if len(winners) != 1:
            raise TargetSourceConflict("equal-time target bars require predecessor precedence")
        selected.append(winners[0])
    return tuple(selected)


def eligible_bars(
    repository: TargetRepository,
    definition: TargetDefinition,
    origin: ForecastOrigin,
    build: TargetSourceBuild,
    start_ns: int,
    end_ns: int,
) -> tuple[TargetBar, ...]:
    sessions = {session.session_id: session for session in build.calendar.sessions}
    bars = repository.bars(
        build, origin.instrument.fingerprint, max(0, start_ns), min(MAX_TIMESTAMP_NS, end_ns)
    )
    return latest_sources(
        repository,
        tuple(
            bar
            for bar in bars
            if definition.session_policy is TargetSessionPolicy.INCLUDE_EXTENDED
            or not sessions[bar.session_id].extended
        ),
    )


def resolve_window(
    repository: TargetRepository,
    definition: TargetDefinition,
    origin: ForecastOrigin,
    build: TargetSourceBuild,
) -> TimeRange | None:
    horizon = definition.horizon
    if horizon.basis is HorizonBasis.ELAPSED_TIME:
        return TimeRange(origin.timestamp_ns, origin.timestamp_ns + (horizon.duration_ns or 0))
    if horizon.basis is HorizonBasis.TRADING_SESSIONS:
        sessions = tuple(
            session
            for session in build.calendar.sessions
            if definition.session_policy is TargetSessionPolicy.INCLUDE_EXTENDED
            or not session.extended
        )
        origin_session = next(
            (session for session in sessions if session.session_id == origin.market_session_id),
            None,
        )
        require(
            origin_session is not None
            and origin_session.period.start_ns
            <= origin.timestamp_ns
            <= origin_session.period.end_ns,
            "origin is outside its declared target session",
        )
        closes = tuple(
            session.period.end_ns
            for session in sessions
            if session.period.end_ns > origin.timestamp_ns
        )
        count = horizon.count or 0
        return (
            TimeRange(origin.timestamp_ns, closes[count - 1]) if len(closes) >= count else None
        )
    bars = eligible_bars(
        repository, definition, origin, build, origin.timestamp_ns + 1, build.known_as_of_ns
    )
    count = horizon.count or 0
    return (
        TimeRange(origin.timestamp_ns, bars[count - 1].period.end_ns)
        if len(bars) >= count
        else None
    )


def select_price(
    repository: TargetRepository,
    definition: TargetDefinition,
    origin: ForecastOrigin,
    build: TargetSourceBuild,
    at_ns: int,
    initial: bool,
) -> TargetBar | None:
    rules = definition.endpoints
    if initial:
        if rules.origin is TargetOriginPolicy.FIRST_AFTER:
            values = eligible_bars(
                repository,
                definition,
                origin,
                build,
                at_ns + 1,
                at_ns + rules.origin_tolerance_ns,
            )
            return values[0] if values else None
        values = eligible_bars(
            repository, definition, origin, build, at_ns - rules.origin_tolerance_ns, at_ns
        )
        return values[-1] if values else None
    if rules.endpoint is TargetEndpointPolicy.FIRST_AT_OR_AFTER:
        values = eligible_bars(
            repository, definition, origin, build, at_ns, at_ns + rules.endpoint_tolerance_ns
        )
        return values[0] if values else None
    values = eligible_bars(
        repository, definition, origin, build, at_ns - rules.endpoint_tolerance_ns, at_ns
    )
    return values[-1] if values else None


def build_vintage(
    repository: TargetRepository,
    definition: TargetDefinition,
    origin: ForecastOrigin,
    build: TargetSourceBuild,
    clocks: AvailabilityEvidence,
    universe_eligible: bool = True,
) -> TargetVintage:
    require(
        definition.implementation_version == BUILDER_VERSION, "unknown trusted target builder"
    )
    require(
        definition.calendar_id == build.source.calendar_id
        and definition.bar_definition == build.source.bar_definition
        and build.source.upstream.dataset_id in definition.source_dataset_ids,
        "target/source dataset, calendar or bar stream mismatch",
    )
    require(
        clocks.afre_computed_ns >= build.known_as_of_ns,
        "target computation before source cutoff",
    )
    require(
        clocks.final_available_ns >= build.calendar.clocks.final_available_ns
        and clocks.final_available_ns >= definition.adjustment.known_as_of_ns,
        "target computation before calendar/adjustment availability",
    )
    require(
        definition.adjustment.known_as_of_ns <= build.known_as_of_ns,
        "future target adjustment policy",
    )
    require(
        definition.adjustment.basis is not AdjustmentBasis.TOTAL_RETURN,
        "total-return/dividend reinvestment is contract-only in AFRE-2",
    )
    window = resolve_window(repository, definition, origin, build)
    start = None
    endpoint = None
    path: tuple[TargetBar, ...] = ()
    actions: tuple[TargetCorporateAction, ...] = ()
    benchmark = None
    flags: set[TargetQualityFlag] = set()
    expected = 0
    present = 0
    quality = DataQuality.VERIFIED
    completion = None

    def result(state: MissingState, reason: str, value: float | None = None) -> TargetVintage:
        used = tuple(item for item in (start, endpoint, *path) if item is not None)
        availability = [
            build.calendar.clocks.final_available_ns,
            definition.adjustment.known_as_of_ns,
        ]
        physical = [build.calendar.clocks.afre_computed_ns]
        for bar in used:
            availability.append(bar.clocks.final_available_ns)
            physical.append(bar.clocks.afre_computed_ns)
            if bar.predecessor_id is not None:
                flags.add(TargetQualityFlag.SOURCE_REVISION)
            if bar.clocks.mode is AvailabilityMode.RECONSTRUCTED:
                flags.add(TargetQualityFlag.RECONSTRUCTED_SOURCE)
            if bar.quality is not DataQuality.VERIFIED:
                flags.add(TargetQualityFlag.UNVERIFIED_SOURCE)
        if (
            definition.adjustment.basis is not AdjustmentBasis.RAW
            and build.action_stream is not None
        ):
            availability.append(build.action_stream.clocks.final_available_ns)
            physical.append(build.action_stream.clocks.afre_computed_ns)
        for action in actions:
            availability.append(action.clocks.final_available_ns)
            physical.append(action.clocks.afre_computed_ns)
            if action.predecessor_id is not None:
                flags.add(TargetQualityFlag.SOURCE_REVISION)
            if action.clocks.mode is AvailabilityMode.RECONSTRUCTED:
                flags.add(TargetQualityFlag.RECONSTRUCTED_SOURCE)
        if benchmark is not None:
            availability.append(benchmark.clocks.final_available_ns)
            physical.append(benchmark.clocks.afre_computed_ns)
        require(
            clocks.final_available_ns >= max(availability)
            and clocks.afre_computed_ns >= max(physical),
            "target backdated before input delivery/processing",
        )
        returned_quality = quality
        if state is not MissingState.PRESENT:
            returned_quality = DataQuality.INVALID
        elif (
            TargetQualityFlag.PARTIAL_PATH in flags
            or TargetQualityFlag.UNVERIFIED_SOURCE in flags
        ):
            returned_quality = DataQuality.UNVERIFIED
        return TargetVintage(
            definition,
            origin,
            repository.source_identity(build),
            window,
            start.fingerprint if start else None,
            endpoint.fingerprint if endpoint else None,
            tuple(bar.fingerprint for bar in path),
            tuple(action.fingerprint for action in actions),
            benchmark.fingerprint if benchmark else None,
            value,
            state,
            max(completion or 0, *availability, *physical)
            if state is MissingState.PRESENT
            else None,
            clocks,
            TargetQuality(returned_quality, tuple(flags), expected, present),
            reason,
        )

    if not universe_eligible:
        return result(
            MissingState.NOT_APPLICABLE, "historical universe excludes origin security"
        )
    if window is None or window.end_ns > build.known_as_of_ns:
        return result(
            MissingState.NOT_AVAILABLE_YET,
            "target window is unresolved or not complete at source cutoff",
        )
    start = select_price(repository, definition, origin, build, origin.timestamp_ns, True)
    endpoint = select_price(repository, definition, origin, build, window.end_ns, False)
    if start is None or endpoint is None:
        return result(
            MissingState.MISSING,
            "origin or endpoint price is missing within declared tolerance",
        )
    if start.period.end_ns >= endpoint.period.end_ns:
        return result(MissingState.INVALID, "price selection has no positive outcome interval")
    for bar in (start, endpoint):
        if bar.state is not TargetObservationState.VALID:
            flags.add(TargetQualityFlag(bar.state.value))
            state = (
                MissingState.INVALID
                if bar.state is TargetObservationState.NONPOSITIVE_PRICE
                else MissingState.MISSING
            )
            return result(
                state, "selected endpoint/origin has explicit invalid or absent print"
            )
    assert start.close is not None and endpoint.close is not None
    if start.period.end_ns != origin.timestamp_ns:
        flags.add(TargetQualityFlag.TOLERATED_ORIGIN)
    if endpoint.period.end_ns != window.end_ns:
        flags.add(TargetQualityFlag.TOLERATED_ENDPOINT)
    completion = max(window.end_ns, endpoint.period.end_ns)
    if definition.adjustment.basis is not AdjustmentBasis.RAW:
        stream = build.action_stream
        if stream is None:
            return result(MissingState.MISSING, "required corporate-action stream absent")
        require(
            stream.dataset_id == definition.adjustment.source_dataset_id,
            "incompatible target action dataset",
        )
        if (
            stream.coverage_start_ns > start.period.end_ns
            or stream.complete_through_ns < endpoint.period.end_ns
        ):
            return result(
                MissingState.NOT_AVAILABLE_YET, "corporate-action coverage is incomplete"
            )
        grouped: dict[str, list[TargetCorporateAction]] = {}
        for identity in stream.action_ids:
            action = repository.resolve(TargetCorporateAction, identity)
            if (
                action.instrument == origin.instrument
                and start.period.end_ns < action.effective_ns <= endpoint.period.end_ns
            ):
                grouped.setdefault(action.event_id, []).append(action)
        chosen = []
        for group in grouped.values():
            latest = max(item.clocks.final_available_ns for item in group)
            candidates = {
                item.fingerprint: item
                for item in group
                if item.clocks.final_available_ns == latest
            }
            superseded = {item.predecessor_id for item in candidates.values()}
            winners = [item for key, item in candidates.items() if key not in superseded]
            require(
                len(winners) == 1, "conflicting action vintages require explicit precedence"
            )
            chosen.append(winners[0])
        actions = tuple(sorted(chosen, key=lambda item: (item.effective_ns, item.event_id)))
    p0 = start.close
    p1 = adjusted_price(
        endpoint.close,
        endpoint.period.end_ns,
        start.period.end_ns,
        definition.adjustment.basis,
        actions,
    )
    require(p1 > 0 and math.isfinite(p1), "invalid adjusted endpoint price")
    simple = p1 / p0 - 1
    value = simple
    kind = definition.aggregation
    if kind is TargetAggregation.LOG:
        value = math.log(p1) - math.log(p0)
    elif kind is TargetAggregation.ABSOLUTE:
        value = abs(simple)
    elif kind is TargetAggregation.DOWNSIDE:
        value = min(simple, 0.0)
    elif kind is TargetAggregation.RESIDUAL:
        benchmark_candidates = tuple(
            repository.resolve(SuppliedBenchmarkReturn, identity)
            for identity in build.benchmark_ids
        )
        aligned = tuple(
            item
            for item in benchmark_candidates
            if item.benchmark == definition.benchmark
            and item.window == window
            and item.origin_price_ns == start.period.end_ns
            and item.endpoint_price_ns == endpoint.period.end_ns
        )
        if not aligned:
            return result(MissingState.MISSING, "exactly aligned supplied benchmark is absent")
        latest = max(item.clocks.final_available_ns for item in aligned)
        choices = {
            item.fingerprint: item
            for item in aligned
            if item.clocks.final_available_ns == latest
        }
        superseded = {item.predecessor_id for item in choices.values()}
        benchmark_winners = tuple(
            item for key, item in choices.items() if key not in superseded
        )
        require(len(benchmark_winners) == 1, "conflicting benchmark vintages")
        benchmark = benchmark_winners[0]
        value = simple - benchmark.value
    elif definition.path is not None:
        policy = definition.path
        require(
            policy.interval_ns % build.source.interval_ns == 0,
            "incompatible target sampling interval",
        )
        require(
            any(
                session.period.start_ns <= origin.timestamp_ns <= session.period.end_ns
                and (origin.timestamp_ns - session.period.start_ns) % policy.interval_ns == 0
                for session in build.calendar.sessions
                if definition.session_policy is TargetSessionPolicy.INCLUDE_EXTENDED
                or not session.extended
            ),
            "target origin is not aligned to declared path sampling grid",
        )
        expected_times = build.calendar.expected_closes(
            origin.timestamp_ns,
            window.end_ns,
            policy.interval_ns,
            definition.session_policy is TargetSessionPolicy.INCLUDE_EXTENDED,
            repository.target_bounds.path_observations,
        )
        expected = len(expected_times)
        path_map = {
            bar.period.end_ns: bar
            for bar in eligible_bars(
                repository, definition, origin, build, origin.timestamp_ns + 1, window.end_ns
            )
        }
        path = tuple(path_map[at] for at in expected_times if at in path_map)
        present = sum(bar.state is TargetObservationState.VALID for bar in path)
        complete = expected > 0 and present == expected and expected_times[-1] == window.end_ns
        if not complete:
            flags.add(TargetQualityFlag.PARTIAL_PATH)
        for bar in path:
            if bar.state is not TargetObservationState.VALID:
                flags.add(TargetQualityFlag(bar.state.value))
        if (
            expected == 0
            or present < policy.minimum_observations
            or present / expected < policy.minimum_coverage
            or (policy.rule is TargetPathRule.FAIL_MISSING and not complete)
        ):
            return result(MissingState.MISSING, "required target path coverage is incomplete")
        prices: list[float] = []
        log_returns: list[float] = []
        previous: float | None = p0
        for at in expected_times:
            sample = path_map.get(at)
            if sample is None or sample.state is not TargetObservationState.VALID:
                previous = None
                continue
            assert sample.close is not None
            price = adjusted_price(
                sample.close, at, start.period.end_ns, definition.adjustment.basis, actions
            )
            require(price > 0 and math.isfinite(price), "invalid adjusted path price")
            prices.append(price)
            if previous is not None:
                log_returns.append(math.log(price) - math.log(previous))
            previous = price
        if kind is TargetAggregation.VOLATILITY:
            if len(log_returns) < policy.minimum_observations:
                return result(MissingState.MISSING, "too few consecutive sampled returns")
            value = math.sqrt(
                math.fsum(change * change for change in log_returns)
                * (
                    policy.annualization_factor
                    if policy.annualization_factor is not None
                    else 1.0
                )
            )
        elif kind is TargetAggregation.ADVERSE:
            value = min(0.0, *(price / p0 - 1 for price in prices))
        else:
            value = max(0.0, *(price / p0 - 1 for price in prices))
    require(math.isfinite(value), "nonfinite computed target")
    return result(MissingState.PRESENT, "completed target with exact pinned evidence", value)

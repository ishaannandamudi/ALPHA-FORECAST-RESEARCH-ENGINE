"""Chronological folds with indexed interval purge and exact embargo grids."""

from bisect import bisect_left, bisect_right
from typing import TYPE_CHECKING

from afre.research_datasets.intervals import IntervalIndex, SampleInformationInterval
from afre.research_datasets.materialization import BLOCKED_STATES
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import (
    EmbargoBasis,
    EmbargoDirection,
    Partition,
    PurgeRule,
    PurgeScope,
    SplitStrategy,
)
from afre.research_datasets.splits import (
    FoldDefinition,
    FoldMembership,
    SplitDefinition,
)
from afre.schema import require
from afre.target_engine.models import TargetVintage
from afre.target_engine.validation import target_known_by_cutoff
from afre.time import TimeRange
from afre.universe.calendars import UniverseCalendar

if TYPE_CHECKING:
    from afre.research_datasets.repository import DatasetRepository


def folds_for(dataset_id: str, definition: SplitDefinition) -> tuple[FoldDefinition, ...]:
    folds = []
    for ordinal in range(definition.fold_count):
        step = ordinal * definition.step_ns
        rolling = definition.strategy is SplitStrategy.ROLLING_WINDOW
        folds.append(
            FoldDefinition(
                dataset_id,
                definition.fingerprint,
                ordinal,
                TimeRange(
                    definition.train.start_ns + (step if rolling else 0),
                    definition.train.end_ns + step,
                ),
                TimeRange(
                    definition.validation.start_ns + step, definition.validation.end_ns + step
                ),
                definition.test,
                definition.training_cutoff_ns + step,
            )
        )
    return tuple(folds)


def group_for(sample: ResearchSample, scope: PurgeScope) -> str:
    if scope is PurgeScope.GLOBAL:
        return "global"
    if scope is PurgeScope.SECURITY:
        return sample.security.instrument.fingerprint
    groups = dict(sample.group_keys)
    require(scope.value in groups, "missing typed purge group evidence")
    return groups[scope.value]


def interval_for(sample: ResearchSample, rule: PurgeRule) -> SampleInformationInterval | None:
    return (
        sample.full_information_interval
        if rule is PurgeRule.FULL_INFORMATION_INTERVAL_OVERLAP
        else sample.target_interval
    )


def embargo_intervals(
    repo: "DatasetRepository", definition: SplitDefinition, folds: tuple[FoldDefinition, ...]
) -> tuple[SampleInformationInterval, ...]:
    policy = definition.embargo
    if policy.count == 0:
        return ()
    periods: tuple[TimeRange, ...] = ()
    if policy.basis is EmbargoBasis.TRADING_SESSIONS:
        assert policy.calendar_id is not None
        calendar = repo.resolve(UniverseCalendar, policy.calendar_id)
        require(
            calendar.evidence.clocks.final_available_ns <= definition.training_cutoff_ns,
            "future embargo calendar",
        )
        periods = tuple(s.period for s in calendar.sessions if not s.extended)
    elif policy.basis is EmbargoBasis.BARS:
        assert policy.bar_grid is not None
        require(
            policy.bar_grid.known_ns <= definition.training_cutoff_ns, "future embargo bar grid"
        )
        periods = policy.bar_grid.periods
    require(
        policy.basis is EmbargoBasis.ELAPSED_TIME or bool(periods), "empty regular embargo grid"
    )
    starts = tuple(p.start_ns for p in periods)
    ends = tuple(p.end_ns for p in periods)
    ranges = {fold.validation for fold in folds}
    if definition.test is not None:
        ranges.add(definition.test)
    answer = []
    for protected in sorted(ranges, key=lambda p: p.start_ns):
        if policy.direction in (EmbargoDirection.BEFORE, EmbargoDirection.BOTH):
            begin = max(0, protected.start_ns - policy.count)
            if periods:
                index = bisect_right(ends, protected.start_ns)
                require(index >= policy.count, "insufficient prior embargo grid coverage")
                begin = periods[index - policy.count].start_ns
            if begin < protected.start_ns:
                answer.append(SampleInformationInterval(begin, protected.start_ns, True, False))
        if policy.direction in (EmbargoDirection.AFTER, EmbargoDirection.BOTH):
            end = protected.end_ns + policy.count
            if periods:
                index = bisect_left(starts, protected.end_ns)
                require(
                    index + policy.count <= len(periods),
                    "insufficient subsequent embargo grid coverage",
                )
                end = periods[index + policy.count - 1].end_ns
            answer.append(SampleInformationInterval(protected.end_ns, end, True, False))
    return tuple(answer)


def memberships_for(
    repo: "DatasetRepository",
    fold: FoldDefinition,
    definition: SplitDefinition,
    samples: tuple[ResearchSample, ...],
    folds: tuple[FoldDefinition, ...],
) -> tuple[FoldMembership, ...]:
    protected: dict[str, list[SampleInformationInterval]] = {}
    embargo = IntervalIndex(embargo_intervals(repo, definition, folds))
    purge = definition.purge
    if purge.rule is not PurgeRule.NONE:
        for sample in samples:
            if (
                (
                    fold.validation.contains(sample.timestamp_ns)
                    or (fold.test is not None and fold.test.contains(sample.timestamp_ns))
                )
                and sample.state not in BLOCKED_STATES
                and not sample.dropped
            ):
                interval = interval_for(sample, purge.rule)
                require(
                    interval is not None, "protected sample has unresolved information interval"
                )
                assert interval is not None
                protected.setdefault(group_for(sample, purge.scope), []).append(interval)
    indexes = {key: IntervalIndex(tuple(values)) for key, values in protected.items()}
    parent_ids: set[str] | None = None
    if definition.parent_fold_id is not None:
        parent_ids = {
            s.fingerprint
            for s in repo.partition_samples(definition.parent_fold_id, Partition.TRAIN)
        }
    memberships = []
    comparisons = 0
    for sample in samples:
        partition, reason = Partition.INELIGIBLE, "outside declared temporal windows"
        if sample.state in BLOCKED_STATES or sample.dropped:
            reason = "dropped sample" if sample.dropped else sample.state.value
        elif parent_ids is not None and repo.identity(sample) not in parent_ids:
            reason = "outside parent TRAIN boundary"
        elif fold.test is not None and fold.test.contains(sample.timestamp_ns):
            partition, reason = (
                Partition.TEST,
                "sealed holdout origin; truth queried separately",
            )
        elif fold.validation.contains(sample.timestamp_ns):
            partition, reason = (
                Partition.VALIDATION,
                "validation origin; truth queried separately",
            )
        elif fold.train.contains(sample.timestamp_ns):
            interval = interval_for(sample, purge.rule)
            index = (
                indexes.get(group_for(sample, purge.scope))
                if purge.rule is not PurgeRule.NONE
                else None
            )
            before = index.comparisons if index else 0
            overlap = index is not None and interval is not None and index.overlaps(interval)
            comparisons += (index.comparisons - before) if index else 0
            if overlap:
                partition, reason = Partition.PURGED, "protected information interval overlaps"
            else:
                point = SampleInformationInterval(
                    sample.timestamp_ns, sample.timestamp_ns, True, True
                )
                before = embargo.comparisons
                in_embargo = embargo.overlaps(point)
                comparisons += embargo.comparisons - before
                if in_embargo:
                    partition, reason = (
                        Partition.EMBARGOED,
                        "origin inside declared embargo fence",
                    )
                elif sample.target_id is None or not target_known_by_cutoff(
                    repo.resolve(TargetVintage, sample.target_id), fold.training_cutoff_ns
                ):
                    reason = "target not known by training cutoff"
                else:
                    partition, reason = (
                        Partition.TRAIN,
                        "causal inputs and label known by training cutoff",
                    )
        require(
            comparisons <= repo.dataset_bounds.interval_comparisons, "interval comparison bound"
        )
        memberships.append(
            FoldMembership(repo.identity(fold), repo.identity(sample), partition, reason)
        )
    repo.last_interval_comparisons = comparisons
    return tuple(memberships)

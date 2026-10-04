"""Endpoint, variable-horizon, scoped purge, embargo and label cutoff regressions."""

from dataclasses import replace
from itertools import product

import pytest

from afre.research_datasets import (
    EmbargoBarGrid,
    EmbargoBasis,
    EmbargoDirection,
    EmbargoPolicy,
    Partition,
    PurgePolicy,
    PurgeRule,
    PurgeScope,
    SampleInformationInterval,
    SampleState,
    SplitDefinition,
    SplitStrategy,
)
from afre.research_datasets.intervals import IntervalIndex
from afre.research_datasets.splitting import embargo_intervals, folds_for, memberships_for
from afre.schema import ContractError
from afre.time import TimeRange
from examples.feature_store_demo import CALENDAR, SOURCE
from examples.research_dataset_demo import split_definition
from examples.universe_demo import SECURITIES
from tests.research_datasets.conftest import Case


def holdout(case: Case, cutoff: int = 40, purge: PurgePolicy | None = None) -> SplitDefinition:
    return SplitDefinition(
        "split.holdout",
        "1",
        SplitStrategy.FIXED_HOLDOUT,
        TimeRange(10, 40),
        TimeRange(40, 50),
        cutoff,
        test=TimeRange(70, 90),
        purge=purge or PurgePolicy(),
    )


@pytest.mark.parametrize("left,right", product((False, True), repeat=2))
def test_endpoint_inclusion(left: bool, right: bool) -> None:
    first = SampleInformationInterval(1, 5, False, right)
    second = SampleInformationInterval(5, 10, left, True)
    assert first.overlaps(second) == (left and right)
    assert second.overlaps(first) == first.overlaps(second)
    assert not first.overlaps(SampleInformationInterval(6, 8))
    assert SampleInformationInterval(2, 4).overlaps(first)
    with pytest.raises(ContractError, match="empty"):
        SampleInformationInterval(5, 5)


def test_index_matches_exhaustive_endpoint_oracle() -> None:
    intervals = tuple(
        SampleInformationInterval(start, end, left, right)
        for start, end, left, right in product(
            range(1, 5), range(5, 8), (False, True), (False, True)
        )
    )
    for offset in range(0, len(intervals), 7):
        chosen = intervals[offset : offset + 7]
        index = IntervalIndex(chosen)
        for query in (*intervals, SampleInformationInterval(30, 30, True, True)):
            assert index.overlaps(query) == any(query.overlaps(other) for other in chosen)
    sparse = IntervalIndex(
        tuple(SampleInformationInterval(i * 4, i * 4 + 2) for i in range(10000))
    )
    assert sparse.overlaps(SampleInformationInterval(39997, 39998))
    assert sparse.comparisons <= 2


def test_purge_variable_horizon_and_target_cutoff(case: Case) -> None:
    definition = holdout(case)
    split = case.engine.build_split(case.dataset.fingerprint, definition)
    fold = case.engine.folds(split.fingerprint)[0]
    purged = case.engine.partition_samples(fold.fingerprint, Partition.PURGED)
    assert {s.timestamp_ns for s in purged} == {30}
    assert all(s.target_interval is not None and s.target_interval.end_ns == 45 for s in purged)
    train = case.engine.training_samples_for_fold(fold.fingerprint)
    assert {s.timestamp_ns for s in train} == {10, 20}
    assert len({s.fingerprint for s in train}) == len(train)
    assert not case.engine.validation_samples_for_fold(fold.fingerprint, 54)
    assert case.engine.validation_samples_for_fold(fold.fingerprint, 55)
    all_parts = tuple(case.engine.partition_samples(fold.fingerprint, p) for p in Partition)
    assert sum(map(len, all_parts)) == len(case.dataset.sample_ids)
    assert len({s.fingerprint for samples in all_parts for s in samples}) == len(
        case.dataset.sample_ids
    )
    case.engine.audit_fold(fold.fingerprint)


@pytest.mark.parametrize("cutoff,expected", [(34, False), (35, True)])
def test_cutoff_equality(case: Case, cutoff: int, expected: bool) -> None:
    definition = replace(
        holdout(case),
        train=TimeRange(10, 30),
        training_cutoff_ns=cutoff,
        purge=PurgePolicy(PurgeRule.NONE),
    )
    split = case.engine.build_split(case.dataset.fingerprint, definition)
    fold = case.engine.folds(split.fingerprint)[0]
    assert (
        any(
            s.timestamp_ns == 20
            for s in case.engine.training_samples_for_fold(fold.fingerprint)
        )
        == expected
    )


@pytest.mark.parametrize("scope", list(PurgeScope))
def test_purge_scope_cross_security(case: Case, scope: PurgeScope) -> None:
    definition = holdout(case, purge=PurgePolicy(PurgeRule.TARGET_INTERVAL_OVERLAP, scope))
    samples = tuple(
        s
        for s in case.engine.dataset_samples(case.dataset.fingerprint)
        if s.security in SECURITIES[:2] and s.timestamp_ns in (20, 40)
    )
    # Only the other security's validation interval overlaps this training interval.
    samples = tuple(
        replace(
            s,
            target_interval=SampleInformationInterval(20, 44)
            if s.timestamp_ns == 20
            else SampleInformationInterval(50, 55)
            if s.security == SECURITIES[0]
            else SampleInformationInterval(40, 45),
            group_keys=(("issuer", "common"), ("sector", "common"), ("market", "common")),
        )
        for s in samples
    )
    fold = folds_for(case.dataset.fingerprint, definition)[0]
    with case.repository.read_snapshot(), case.repository.validation_cache():
        memberships = memberships_for(case.repository, fold, definition, samples, (fold,))
    train_ids = {
        s.fingerprint for s in samples if s.timestamp_ns == 20 and s.security == SECURITIES[0]
    }
    decisions = {m.partition for m in memberships if m.sample_id in train_ids}
    assert decisions == {Partition.TRAIN if scope is PurgeScope.SECURITY else Partition.PURGED}


def test_full_information_purge_and_missing_group(case: Case) -> None:
    definition = holdout(case, purge=PurgePolicy(PurgeRule.FULL_INFORMATION_INTERVAL_OVERLAP))
    split = case.engine.build_split(case.dataset.fingerprint, definition)
    fold = case.engine.folds(split.fingerprint)[0]
    assert case.engine.partition_samples(fold.fingerprint, Partition.PURGED)
    with pytest.raises(ContractError, match="group"):
        case.engine.build_split(
            case.dataset.fingerprint,
            replace(definition, purge=PurgePolicy(scope=PurgeScope.SECTOR)),
        )


@pytest.mark.parametrize("direction", list(EmbargoDirection))
def test_elapsed_embargo_and_prior_fold_fences(case: Case, direction: EmbargoDirection) -> None:
    definition = replace(
        split_definition(case.fixture),
        embargo=EmbargoPolicy(count=10, direction=direction),
        purge=PurgePolicy(PurgeRule.NONE),
    )
    split = case.engine.build_split(case.dataset.fingerprint, definition)
    folds = case.engine.folds(split.fingerprint)
    first = case.engine.partition_samples(folds[0].fingerprint, Partition.EMBARGOED)
    last = case.engine.partition_samples(folds[2].fingerprint, Partition.EMBARGOED)
    assert bool(first) == (direction is not EmbargoDirection.AFTER)
    if direction is not EmbargoDirection.BEFORE:
        assert any(s.timestamp_ns == 50 for s in last)
    case.engine.audit_fold(folds[2].fingerprint)


@pytest.mark.parametrize("basis", [EmbargoBasis.TRADING_SESSIONS, EmbargoBasis.BARS])
def test_explicit_calendar_and_bar_embargo(case: Case, basis: EmbargoBasis) -> None:
    calendar_id = case.fixture.definition.compatibility.universe_calendar_ids[0]
    grid = EmbargoBarGrid(
        CALENDAR,
        "one-unit-bars-v1",
        "1",
        SOURCE.fingerprint,
        0,
        (
            TimeRange(20, 30),
            TimeRange(40, 50),
            TimeRange(60, 65),
            TimeRange(70, 80),
            TimeRange(90, 100),
        ),
    )
    embargo = EmbargoPolicy(
        basis,
        1,
        EmbargoDirection.BOTH,
        calendar_id if basis is EmbargoBasis.TRADING_SESSIONS else None,
        grid if basis is EmbargoBasis.BARS else None,
    )
    definition = replace(
        holdout(case), test=None, embargo=embargo, purge=PurgePolicy(PurgeRule.NONE)
    )
    folds = folds_for(case.dataset.fingerprint, definition)
    with case.repository.read_snapshot(), case.repository.validation_cache():
        fences = embargo_intervals(case.repository, definition, folds)
    assert fences == (
        SampleInformationInterval(20, 40, True, False),
        SampleInformationInterval(50, 65, True, False),
    )
    split = case.engine.build_split(case.dataset.fingerprint, definition)
    assert case.engine.partition_samples(split.fold_ids[0], Partition.EMBARGOED)


@pytest.mark.parametrize("strategy", list(SplitStrategy))
def test_strategies_deterministic(case: Case, strategy: SplitStrategy) -> None:
    definition = replace(
        split_definition(case.fixture),
        strategy=strategy,
        fold_count=1 if strategy is SplitStrategy.FIXED_HOLDOUT else 3,
        step_ns=0 if strategy is SplitStrategy.FIXED_HOLDOUT else 10,
    )
    split = case.engine.build_split(case.dataset.fingerprint, definition)
    assert case.engine.build_split(case.dataset.fingerprint, definition) == split
    folds = case.engine.folds(split.fingerprint)
    assert folds[-1].train.start_ns == (30 if strategy is SplitStrategy.ROLLING_WINDOW else 10)
    assert case.repository.last_interval_comparisons <= len(case.dataset.sample_ids) * 4


def test_test_seal_evaluation_reuse_and_nested_boundary(case: Case) -> None:
    split = case.engine.build_split(case.dataset.fingerprint, holdout(case))
    fold = case.engine.folds(split.fingerprint)[0]
    early, audit = case.engine.test_samples_for_fold(
        fold.fingerprint, "early", "holdout truth not known", 80
    )
    assert not early and not audit.sample_ids
    ready, record = case.engine.test_samples_for_fold(
        fold.fingerprint, "final", "explicit holdout evaluation", 100
    )
    assert ready and record.previous_evaluation_ids == (audit.fingerprint,)
    assert (
        case.engine.test_samples_for_fold(
            fold.fingerprint, "final", "explicit holdout evaluation", 100
        )[1]
        == record
    )
    with pytest.raises(ContractError, match="reuse"):
        case.engine.test_samples_for_fold(fold.fingerprint, "final", "changed purpose", 100)
    inner = replace(
        holdout(case),
        name="split.nested",
        train=TimeRange(10, 30),
        validation=TimeRange(30, 40),
        training_cutoff_ns=30,
        test=None,
        parent_fold_id=fold.fingerprint,
    )
    nested = case.engine.build_split(case.dataset.fingerprint, inner)
    assert not case.engine.validation_samples_for_fold(nested.fold_ids[0])
    assert all(
        s.timestamp_ns == 10 for s in case.engine.training_samples_for_fold(nested.fold_ids[0])
    )


@pytest.mark.parametrize(
    "state",
    [SampleState.TARGET_MISSING, SampleState.TARGET_NOT_AVAILABLE_YET, SampleState.INVALID],
)
def test_validation_membership_is_independent_of_later_truth_state(
    case: Case, state: SampleState
) -> None:
    definition = holdout(case, purge=PurgePolicy(PurgeRule.NONE))
    fold = folds_for(case.dataset.fingerprint, definition)[0]
    sample = next(
        s
        for s in case.engine.dataset_samples(case.dataset.fingerprint)
        if s.timestamp_ns == 40 and s.origin is not None
    )
    sample = replace(sample, state=state)
    with case.repository.read_snapshot(), case.repository.validation_cache():
        result = memberships_for(case.repository, fold, definition, (sample,), (fold,))
    assert result[0].partition is Partition.VALIDATION

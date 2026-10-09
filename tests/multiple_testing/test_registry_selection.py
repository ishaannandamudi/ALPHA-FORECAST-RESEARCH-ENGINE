"""Whole-registry history, TEST counts and caller-recorded selection opportunity sets."""

import statistics
from dataclasses import replace

import pytest

from afre.multiple_testing import (
    CorrectionMethod,
    EvidenceState,
    FamilyAnalysisSpec,
    ResearchTrial,
    SelectionEvent,
)
from afre.multiple_testing import (
    DescriptiveSelectionRule as Rule,
)
from afre.multiple_testing.raw_tests import raw_results_for
from afre.multiple_testing.schema import TestReuseStatus as Reuse
from afre.multiple_testing.test_reuse import TestReusePolicy as ReusePolicy
from afre.schema import ContractError
from afre.serialization import canonical_json
from tests.multiple_testing.conftest import TestingCase as MTCase
from tests.multiple_testing.helpers import analyses, completed_cutoff, trial


def selection(case: MTCase, rule: Rule, higher: bool, failed: bool = False) -> SelectionEvent:
    keys = ("phase-5", "phase-6", "phase-13", "phase-14") + (("failed",) if failed else ())
    candidates = tuple(trial(case, k) for k in keys)
    cutoff = max(t.completed_ns for t in candidates)
    with case.repo.read_snapshot(), case.repo.validation_cache():
        values = {
            t.fingerprint: raw_results_for(case.repo, t.fingerprint, cutoff)[1].estimate
            for t in candidates
        }
    order = tuple(
        sorted(
            values,
            key=lambda i: (
                values[i] is None,
                -(values[i] or 0.0) if higher and values[i] is not None else values[i] or 0.0,
                i,
            ),
        )
    )
    threshold = 0.0 if rule is Rule.DECLARED_THRESHOLD else None
    if threshold is not None:
        chosen = tuple(
            i
            for i in order
            if values[i] is not None
            and ((values[i] or 0) >= threshold if higher else (values[i] or 0) <= threshold)
        )
    else:
        chosen = order[: 2 if rule is Rule.TOP_K else 1]
    return SelectionEvent(
        tuple(values),
        chosen,
        rule,
        higher,
        2 if rule is Rule.TOP_K else 1,
        threshold,
        cutoff,
        cutoff,
        ordering=order,
    )


@pytest.mark.parametrize(
    "rule,higher",
    [
        (Rule.MAX_METRIC, True),
        (Rule.MIN_ERROR, False),
        (Rule.TOP_K, True),
        (Rule.TOP_K, False),
        (Rule.DECLARED_THRESHOLD, True),
        (Rule.DECLARED_THRESHOLD, False),
    ],
)
def test_selection_spread_oracles(completed_case: MTCase, rule: Rule, higher: bool) -> None:
    event = completed_case.engine.record_selection(selection(completed_case, rule, higher))
    at = completed_cutoff(completed_case)
    registry = completed_case.engine.registry(at, at)
    analysis = next(
        a
        for a in analyses(completed_case)
        if completed_case.repo.resolve(FamilyAnalysisSpec, a.spec_id).correction
        is CorrectionMethod.HOLM
    )
    d = completed_case.engine.selection_bias(
        event.fingerprint, analysis.fingerprint, registry.fingerprint, at
    )
    metrics = dict(d.metrics)
    winner = metrics[d.ordering[0]] if event.selected_trial_ids else None
    assert d.winner_metric == winner
    assert d.median_metric == statistics.median(v for v in metrics.values() if v is not None)
    if winner is not None:
        assert d.winner_minus_median == winner - (d.median_metric or 0)
        assert d.winner_minus_next == winner - (metrics[d.ordering[1]] or 0)
    assert (
        d.candidate_count == 4 and d.test_use_count == 0 and d.state is EvidenceState.AVAILABLE
    )


def test_failed_selection_candidate_retained(completed_case: MTCase) -> None:
    event = completed_case.engine.record_selection(
        selection(completed_case, Rule.TOP_K, True, True)
    )
    at = completed_cutoff(completed_case)
    registry = completed_case.engine.registry(at, at)
    d = completed_case.engine.selection_bias(
        event.fingerprint, analyses(completed_case)[0].fingerprint, registry.fingerprint, at
    )
    assert d.candidate_count == 5 and len(d.ordering) == 5
    assert any(v is None for _, v in d.metrics)
    assert d.median_metric is None and d.winner_minus_median is None
    assert d.state is EvidenceState.INCOMPATIBLE


@pytest.mark.parametrize("change", ["chosen", "ordering", "test", "cutoff", "mixed-samples"])
def test_selection_forgery_rejected(completed_case: MTCase, change: str) -> None:
    event = selection(completed_case, Rule.MAX_METRIC, True)
    if change == "chosen":
        event = replace(event, selected_trial_ids=(event.ordering[-1],))
    elif change == "ordering":
        event = replace(event, ordering=tuple(reversed(event.ordering)))
    elif change == "test":
        event = replace(event, test_involved=True)
    elif change == "cutoff":
        event = replace(event, selection_cutoff_ns=99)
    else:
        t = trial(completed_case, "test-0")
        event = replace(
            event,
            candidate_trial_ids=(*event.candidate_trial_ids, t.fingerprint),
            ordering=(*event.ordering, t.fingerprint),
            test_involved=True,
        )
    with pytest.raises(ContractError):
        completed_case.engine.record_selection(event)


def test_registry_whole_no_subset_and_historical_snapshot(mt_case: MTCase) -> None:
    p = mt_case.fixture.plan("phase-5")
    t = mt_case.engine.complete(p.fingerprint, mt_case.fixture.family.fingerprint, 100, 100)
    old = mt_case.engine.registry(100, 100)
    old_bytes = canonical_json(old)
    with pytest.raises(ContractError), mt_case.repo.transaction():
        mt_case.repo.put(replace(old, trial_ids=(), chronology=()))
    q = mt_case.fixture.plan("phase-6")
    second = mt_case.engine.complete(
        q.fingerprint, mt_case.fixture.family.fingerprint, 100, 100
    )
    latest = mt_case.engine.registry(100, 100)
    assert old.trial_ids == (t.fingerprint,)
    assert set(latest.trial_ids) == {t.fingerprint, second.fingerprint}
    assert canonical_json(mt_case.repo.get_any(old.fingerprint)) == old_bytes
    assert latest.fingerprint != old.fingerprint


def test_test_reuse_exact_seals_unknown_history_and_heavy(mt_case: MTCase) -> None:
    policy = mt_case.engine.reuse_policy(ReusePolicy(3, 40))
    histories = []
    for j in range(3):
        p = mt_case.fixture.plan(f"test-{j}")
        t = mt_case.engine.complete(
            p.fingerprint,
            mt_case.fixture.family.fingerprint,
            100,
            100,
            test_identity="repeated-native-seal",
        )
        registry = mt_case.engine.registry(100, 100)
        histories.append(
            mt_case.engine.test_reuse(
                registry.fingerprint, t.fingerprint, policy.fingerprint, 100
            )
        )
    assert [d.use_count for d in histories] == [1, 2, 3]
    assert [d.tracked_status for d in histories] == [
        Reuse.FIRST_USE,
        Reuse.REUSED,
        Reuse.HEAVILY_REUSED,
    ]
    assert all(sum(n for _, n in d.exact_seal_counts) == d.use_count for d in histories)
    assert histories[-1].exact_seal_counts[0][1] == 3
    if histories[-1].untracked_seal_ids:
        assert histories[-1].status is Reuse.UNTRACKED
    assert mt_case.repo.get_any(histories[0].fingerprint) == histories[0]


def test_validation_reuse_incompatible_and_overfitting(completed_case: MTCase) -> None:
    at = completed_cutoff(completed_case)
    registry = completed_case.engine.registry(at, at)
    policy = completed_case.engine.reuse_policy(ReusePolicy(3, 40))
    t = trial(completed_case, "phase-5")
    d = completed_case.engine.test_reuse(
        registry.fingerprint, t.fingerprint, policy.fingerprint, at
    )
    assert d.tracked_status is Reuse.INCOMPATIBLE
    counts = completed_case.engine.overfitting(registry.fingerprint, at)
    assert counts.planned_count == len(completed_case.fixture.plans)
    assert (
        counts.failed_count == 2
        and counts.completed_count == len(completed_case.fixture.plans) - 2
    )
    assert dict(counts.opportunity_counts)["environments"] == 2
    assert dict(counts.opportunity_counts)["cost_scenarios"] == 2
    unsupported = completed_case.engine.deflated(registry.fingerprint, at)
    assert unsupported.state is EvidenceState.UNSUPPORTED and unsupported.value is None
    with pytest.raises(ContractError):
        completed_case.engine.overfitting(registry.fingerprint, at - 1)


def test_registry_enumerates_uncompleted_planned_opportunities(mt_case: MTCase) -> None:
    registry = mt_case.engine.registry(40, 40)
    assert registry.trial_ids == () and len(registry.plan_ids) == len(mt_case.fixture.plans)
    d = mt_case.engine.overfitting(registry.fingerprint, 40)
    assert d.planned_count == len(mt_case.fixture.plans) and d.completed_count == 0
    with pytest.raises(ContractError):
        mt_case.repo.resolve(ResearchTrial, mt_case.fixture.plans[0].fingerprint)


def test_untracked_native_history_cannot_be_claimed_first_clean_use(mt_case: MTCase) -> None:
    from afre.statistical_models.evaluation import test_record

    p = mt_case.fixture.plan("test-0")
    with mt_case.repo.read_snapshot(), mt_case.repo.validation_cache():
        legacy = test_record(
            mt_case.repo,
            p.fold_id,
            "legacy-unregistered-assessment",
            "explicit-prior-native-assessment",
            99,
        )
    with mt_case.repo.transaction():
        mt_case.repo.put(legacy)
    t = mt_case.engine.complete(
        p.fingerprint,
        mt_case.fixture.family.fingerprint,
        100,
        100,
        test_identity="first-registered-opportunity",
    )
    policy = mt_case.engine.reuse_policy(ReusePolicy(3, 40))
    registry = mt_case.engine.registry(100, 100)
    diagnostic = mt_case.engine.test_reuse(
        registry.fingerprint, t.fingerprint, policy.fingerprint, 100
    )
    assert diagnostic.use_count == 1 and diagnostic.tracked_status is Reuse.FIRST_USE
    assert diagnostic.status is Reuse.UNTRACKED
    assert legacy.fingerprint in diagnostic.untracked_seal_ids


def test_selection_explicit_test_involvement_and_counts(completed_case: MTCase) -> None:
    candidates = tuple(trial(completed_case, f"test-{j}") for j in range(3))
    identities = tuple(sorted(t.fingerprint for t in candidates))
    event = completed_case.engine.record_selection(
        SelectionEvent(
            identities,
            (identities[0],),
            Rule.MAX_METRIC,
            True,
            1,
            None,
            100,
            100,
            ordering=identities,
            test_involved=True,
        )
    )
    at = completed_cutoff(completed_case)
    registry = completed_case.engine.registry(at, at)
    diagnostic = completed_case.engine.selection_bias(
        event.fingerprint, analyses(completed_case)[0].fingerprint, registry.fingerprint, at
    )
    assert event.test_involved and diagnostic.test_use_count == 3
    assert diagnostic.winner_minus_median == 0.0 and diagnostic.winner_minus_next == 0.0

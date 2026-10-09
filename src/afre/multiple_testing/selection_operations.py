"""Verify explicitly recorded selections and describe their observed opportunity sets."""

import statistics
from typing import TYPE_CHECKING

from afre.multiple_testing.effects import EffectSizeResult
from afre.multiple_testing.evaluations import AdjustedHypothesisResult, FamilyAnalysis
from afre.multiple_testing.hypotheses import HypothesisDefinition
from afre.multiple_testing.raw_tests import raw_results_for
from afre.multiple_testing.registry import TrialRegistrySnapshot
from afre.multiple_testing.schema import DescriptiveSelectionRule, EvidenceState
from afre.multiple_testing.selection_bias import SelectionBiasDiagnostic, SelectionEvent
from afre.multiple_testing.trials import ResearchTrial, TrialSpecification
from afre.schema import require

if TYPE_CHECKING:
    from afre.multiple_testing.repository import MultipleTestingRepository


def selection_values(
    repo: "MultipleTestingRepository", event: SelectionEvent
) -> tuple[tuple[str, float | None], ...]:
    effects: list[EffectSizeResult] = []
    protocols = set()
    observed_sets = set()
    tests = False
    for identity in event.candidate_trial_ids:
        trial = repo.resolve(ResearchTrial, identity)
        plan = repo.resolve(TrialSpecification, trial.plan_id)
        h = repo.resolve(HypothesisDefinition, trial.hypothesis_id)
        require(
            trial.completed_ns <= event.selection_cutoff_ns,
            "selection after candidate completion",
        )
        effects.append(raw_results_for(repo, identity, event.selection_cutoff_ns)[1])
        tests = tests or bool(trial.test_seal_ids)
        if trial.observations:
            observed_sets.add(tuple((o.sample_id, o.truth_id) for o in trial.observations))
        protocols.add(
            (
                plan.dataset_id,
                plan.fold_id,
                h.target_id,
                h.horizon_id,
                h.metric,
                h.null_value,
                effects[-1].unit,
                plan.sample_ids,
            )
        )
    require(
        len(protocols) == 1 and len(observed_sets) <= 1,
        "selection metrics require exact matched sample/truth/units/null/protocol",
    )
    values = tuple(zip(event.candidate_trial_ids, (e.estimate for e in effects), strict=True))
    ordered = sorted(
        ((i, v) for i, v in values if v is not None),
        key=lambda p: (-p[1] if event.higher_is_better else p[1], p[0]),
    )
    full_order = tuple(
        i
        for i, _ in sorted(
            values,
            key=lambda p: (
                p[1] is None,
                -p[1] if event.higher_is_better and p[1] is not None else p[1] or 0.0,
                p[0],
            ),
        )
    )
    require(
        event.ordering == full_order and event.test_involved == tests,
        "selection exact stable ordering/TEST involvement",
    )
    if event.rule is DescriptiveSelectionRule.DECLARED_THRESHOLD:
        assert event.threshold is not None
        expected = (
            {i for i, v in ordered if v >= event.threshold}
            if event.higher_is_better
            else {i for i, v in ordered if v <= event.threshold}
        )
    else:
        k = event.top_k if event.rule is DescriptiveSelectionRule.TOP_K else 1
        require(len(ordered) >= k, "insufficient observed candidate metrics")
        expected = {i for i, _ in ordered[:k]}
    require(
        set(event.selected_trial_ids) == expected,
        "recorded caller selection differs from declared rule/stable ties",
    )
    return values


def selection_diagnostic_for(
    repo: "MultipleTestingRepository",
    event_id: str,
    analysis_id: str,
    registry_id: str,
    available_ns: int,
) -> SelectionBiasDiagnostic:
    event = repo.resolve(SelectionEvent, event_id)
    analysis = repo.resolve(FamilyAnalysis, analysis_id)
    registry = repo.resolve(TrialRegistrySnapshot, registry_id)
    require(
        event_id in registry.selection_event_ids
        and set(event.candidate_trial_ids) <= set(registry.trial_ids)
        and max(event.available_ns, analysis.available_ns, registry.available_ns)
        <= available_ns,
        "selection exact registry/cutoff",
    )
    adjusted = tuple(repo.resolve(AdjustedHypothesisResult, i) for i in analysis.adjusted_ids)
    require(
        set(event.candidate_trial_ids) <= {r.trial_id for r in adjusted},
        "selection evidence from one exact correction family",
    )
    values = selection_values(repo, event)
    ordered = sorted(
        values,
        key=lambda p: (
            p[1] is None,
            -p[1] if event.higher_is_better and p[1] is not None else p[1] or 0.0,
            p[0],
        ),
    )
    valid = tuple(v for _, v in ordered if v is not None)
    complete = len(valid) == len(values)
    winner = ordered[0][1] if event.selected_trial_ids else None
    median = float(statistics.median(valid)) if complete else None
    next_value = ordered[1][1] if len(ordered) > 1 and complete else None
    return SelectionBiasDiagnostic(
        event_id,
        analysis_id,
        registry_id,
        tuple(i for i, _ in ordered),
        values,
        len(values),
        winner,
        median,
        winner - median if winner is not None and median is not None else None,
        winner - next_value if winner is not None and next_value is not None else None,
        tuple(r.fingerprint for r in adjusted if r.trial_id in event.selected_trial_ids),
        sum(
            bool(repo.resolve(ResearchTrial, i).test_seal_ids)
            for i in event.candidate_trial_ids
        ),
        EvidenceState.AVAILABLE if complete else EvidenceState.INCOMPATIBLE,
        available_ns,
    )

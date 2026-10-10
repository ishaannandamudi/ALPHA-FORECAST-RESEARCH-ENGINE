"""Full candidate pool in AFRE19, including explicitly anchored failed attempts."""

from typing import TYPE_CHECKING

from afre.multiple_testing.engine import MultipleTestingEngine
from afre.multiple_testing.families import HypothesisFamily
from afre.multiple_testing.hypotheses import HypothesisDefinition, TestAssumptions
from afre.multiple_testing.raw_tests import raw_results_for
from afre.multiple_testing.schema import (
    AdaptiveTrialStatus,
    CorrectionMethod,
    DependenceAssumption,
    DescriptiveSelectionRule,
    HypothesisDirection,
    RawTestMethod,
    ResearchMetric,
    TrialState,
)
from afre.multiple_testing.selection_bias import SelectionEvent
from afre.multiple_testing.trials import ResearchTrial, TrialSpecification
from afre.schema import require
from afre.selection.definitions import CandidateSpec, SearchSpace, SelectionRequest
from afre.selection.results import CandidateFitResult, CandidateValidationResult
from afre.selection.schema import CandidateStatus, SelectionCriterion

if TYPE_CHECKING:
    from afre.selection.repository import SelectionRepository


def register_pool(
    repo: "SelectionRepository",
    space: SearchSpace,
    candidates: tuple[CandidateSpec, ...],
    fits: tuple[CandidateFitResult, ...],
    request: SelectionRequest,
) -> tuple[HypothesisFamily, tuple[TrialSpecification, ...]]:
    engine = MultipleTestingEngine(repo)
    h = HypothesisDefinition(
        space.fingerprint[-64:],
        space.fingerprint[-64:],
        space.target_id,
        space.horizon_id,
        ResearchMetric.ABSOLUTE_ERROR
        if space.criterion is SelectionCriterion.MIN_MAE
        else ResearchMetric.SQUARED_ERROR,
        0.0,
        HypothesisDirection.TWO_SIDED,
        RawTestMethod.NORMAL_MEAN,
        space.minimum_support,
        TestAssumptions(
            False, False, False, False, "AFRE20-no-inferential-assumption", space.declared_ns
        ),
        space.declared_ns,
    )
    engine.hypothesis(h)
    by_id = {c.fingerprint: c for c in candidates}
    plans = []
    for fit in fits:
        candidate = by_id[fit.candidate_id]
        sources = (
            fit.forecast_ids
            if fit.status is CandidateStatus.VALID
            else space.failure_anchor_source_ids
        )
        require(
            bool(sources),
            "failed candidates require declared native VALIDATION protocol anchor",
        )
        phase = candidate.recipe.native_phase if fit.status is CandidateStatus.VALID else 5
        # Failed native plans reference the predeclared protocol anchor without
        # inventing a failed forecast. The AFRE20 spec records the attempted phase.
        plan = TrialSpecification(
            candidate.fingerprint[-64:],
            h.fingerprint,
            phase,
            sources[0],
            sources,
            space.validation_sample_ids,
            space.dataset_id,
            space.fold_id,
            fit.preprocessing_ids,
            (candidate.fingerprint,),
            (
                ("candidate", candidate.fingerprint),
                ("selection-request", request.fingerprint),
                ("native-phase", str(candidate.recipe.native_phase)),
                ("failed-protocol-anchor", str(fit.status is not CandidateStatus.VALID)),
            ),
            space.declared_ns,
            AdaptiveTrialStatus.PREDECLARED,
        )
        engine.plan(plan)
        plans.append(plan)
    family = HypothesisFamily(
        space.fingerprint[-64:],
        tuple(p.fingerprint for p in plans),
        CorrectionMethod.HOLM,
        0.05,
        DependenceAssumption.ARBITRARY,
        space.declared_ns,
        True,
    )
    engine.family(family)
    return family, tuple(plans)


def complete_pool(
    repo: "SelectionRepository",
    family: HypothesisFamily,
    plans: tuple[TrialSpecification, ...],
    fits: tuple[CandidateFitResult, ...],
    cutoff_ns: int,
    available_ns: int,
) -> tuple[ResearchTrial, ...]:
    engine = MultipleTestingEngine(repo)
    return tuple(
        engine.complete(
            p.fingerprint,
            family.fingerprint,
            cutoff_ns,
            available_ns,
            state=TrialState.COMPLETED
            if f.status is CandidateStatus.VALID
            else TrialState.FAILED,
            reason="AFRE20-native-VALIDATION"
            if f.status is CandidateStatus.VALID
            else f.reason,
        )
        for p, f in zip(plans, fits, strict=True)
    )


def exact_native_event(
    repo: "SelectionRepository",
    space: SearchSpace,
    results: tuple[CandidateValidationResult, ...],
    ordering: tuple[str, ...],
    winner: str | None,
    cutoff_ns: int,
    available_ns: int,
) -> SelectionEvent | None:
    if (
        winner is None
        or space.secondary_criterion is not None
        or space.criterion not in (SelectionCriterion.MIN_MSE, SelectionCriterion.MIN_MAE)
    ):
        return None
    by_candidate = {r.candidate_id: r for r in results}
    values = tuple(
        (r.trial_id, raw_results_for(repo, r.trial_id, cutoff_ns)[1].estimate) for r in results
    )
    if any(
        estimate != next(r.value for r in results if r.trial_id == i) for i, estimate in values
    ):
        return None
    native_order = tuple(
        i for i, v in sorted(values, key=lambda p: (p[1] is None, p[1] or 0.0, p[0]))
    )
    mapped = tuple(by_candidate[i].trial_id for i in ordering)
    if mapped != native_order:
        return None
    event = SelectionEvent(
        tuple(i for i, _ in values),
        (by_candidate[winner].trial_id,),
        DescriptiveSelectionRule.MIN_ERROR,
        False,
        1,
        None,
        available_ns,
        available_ns,
        mapped,
    )
    return event

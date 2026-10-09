"""Replay final/interim family evidence without searching, pruning or effect changes."""

from typing import TYPE_CHECKING

from afre.multiple_testing.corrections import adjust_pvalues
from afre.multiple_testing.effects import EffectSizeResult
from afre.multiple_testing.evaluations import AdjustedHypothesisResult, FamilyAnalysis
from afre.multiple_testing.families import FamilyAnalysisSpec, HypothesisFamily
from afre.multiple_testing.hypotheses import HypothesisDefinition
from afre.multiple_testing.pvalues import PValueResult
from afre.multiple_testing.schema import (
    AdaptiveTrialStatus,
    CorrectionMethod,
    DependenceAssumption,
    EvidenceState,
    FamilyCompleteness,
    TrialState,
)
from afre.multiple_testing.trials import ResearchTrial, TrialSpecification
from afre.research_datasets.splits import FoldDefinition
from afre.schema import require

if TYPE_CHECKING:
    from afre.multiple_testing.repository import MultipleTestingRepository


def adjustment_for(
    repo: "MultipleTestingRepository",
    spec: FamilyAnalysisSpec,
    pvalue_ids: tuple[str, ...],
    effect_ids: tuple[str, ...],
) -> tuple[tuple[AdjustedHypothesisResult, ...], FamilyAnalysis]:
    family = repo.resolve(HypothesisFamily, spec.family_id)
    require(
        spec.correction in (family.correction, *family.additional_corrections),
        "correction was not predeclared",
    )
    trials = tuple(repo.resolve(ResearchTrial, i) for i in spec.trial_ids)
    by_plan = {t.plan_id: t for t in trials}
    require(
        len(by_plan) == len(trials)
        and set(by_plan) <= set(family.plan_ids)
        and all(
            t.family_id == family.fingerprint and t.completed_ns <= spec.cutoff_ns
            for t in trials
        ),
        "family exact attempts/cutoff/no duplicate completion",
    )
    require(
        spec.completeness is not FamilyCompleteness.COMPLETE
        or set(by_plan) == set(family.plan_ids),
        "complete family cannot omit declared attempts",
    )
    raws = {
        v.trial_id: v
        for i in pvalue_ids
        if isinstance((v := repo.resolve(PValueResult, i)), PValueResult)
    }
    effects = {
        effect_result.trial_id: effect_result
        for i in effect_ids
        if isinstance((effect_result := repo.resolve(EffectSizeResult, i)), EffectSizeResult)
    }
    require(
        len(raws) == len(pvalue_ids) == len(trials)
        and len(effects) == len(effect_ids) == len(trials)
        and set(raws) == set(effects) == set(spec.trial_ids)
        and all(v.available_ns <= spec.cutoff_ns for v in raws.values())
        and all(v.available_ns <= spec.cutoff_ns for v in effects.values()),
        "exact one raw/effect pair per completed trial by cutoff",
    )
    plans = tuple(repo.resolve(TrialSpecification, i) for i in family.plan_ids)
    state, reason = (
        EvidenceState.AVAILABLE,
        "nominal-declared-family-control-valid-raw-null-evidence-required",
    )
    if spec.completeness in (FamilyCompleteness.OPEN, FamilyCompleteness.PARTIAL):
        state, reason = EvidenceState.INTERIM, "open-or-partial-family-no-final-rejections"
    elif spec.completeness is FamilyCompleteness.INVALID:
        state, reason = EvidenceState.INCOMPATIBLE, "declared-invalid-family"
    elif not family.caller_attested_predeclaration or any(
        p.adaptivity is not AdaptiveTrialStatus.PREDECLARED for p in plans
    ):
        state, reason = (
            EvidenceState.INTERIM,
            "adaptive-unknown-or-retrospective-generation-nominal-descriptive-only",
        )
    if spec.correction is CorrectionMethod.BENJAMINI_HOCHBERG and family.dependence not in (
        DependenceAssumption.INDEPENDENT,
        DependenceAssumption.PRDS,
    ):
        state, reason = EvidenceState.UNSUPPORTED, "BH-independence-or-PRDS-not-attested"
    for plan in plans:
        h = repo.resolve(HypothesisDefinition, plan.hypothesis_id)
        fold = repo.resolve(FoldDefinition, plan.fold_id)
        require(
            h.family_key == family.family_key
            and h.declared_ns <= plan.declared_ns <= family.declared_ns,
            "exact declared hypothesis/family chronology",
        )
        if family.caller_attested_predeclaration:
            require(
                family.declared_ns <= fold.training_cutoff_ns,
                "family/correction/alpha before held-out TRAIN boundary",
            )
    raw_values = tuple(
        (
            p.fingerprint,
            raws[by_plan[p.fingerprint].fingerprint].raw_p_value
            if p.fingerprint in by_plan
            else None,
        )
        for p in plans
    )
    adjusted = {
        i: (value, rank) for i, value, rank in adjust_pvalues(raw_values, spec.correction)
    }
    rows = []
    for plan in plans:
        trial = by_plan.get(plan.fingerprint)
        raw = raws[trial.fingerprint] if trial else None
        effect = effects[trial.fingerprint] if trial else None
        value, rank = adjusted[plan.fingerprint]
        row_state = (
            state
            if raw and raw.raw_p_value is not None
            else raw.state
            if raw
            else EvidenceState.INSUFFICIENT
        )
        rows.append(
            AdjustedHypothesisResult(
                spec.fingerprint,
                family.fingerprint,
                plan.fingerprint,
                plan.hypothesis_id,
                trial.fingerprint if trial else None,
                raw.fingerprint if raw else None,
                effect.fingerprint if effect else None,
                spec.correction,
                len(plans),
                raw.raw_p_value if raw else None,
                value if raw and raw.raw_p_value is not None else None,
                family.level,
                value <= family.level if row_state is EvidenceState.AVAILABLE else None,
                rank,
                row_state,
                reason
                if raw and raw.raw_p_value is not None
                else "missing-or-unsupported-declared-slot-counts-as-one-internally",
                spec.available_ns,
            )
        )
    result = FamilyAnalysis(
        spec.fingerprint,
        family.fingerprint,
        tuple(r.fingerprint for r in rows),
        len(plans),
        sum(t.state is TrialState.COMPLETED for t in trials),
        sum(t.state is not TrialState.COMPLETED for t in trials),
        len(plans) - len(trials),
        spec.completeness,
        state,
        reason,
        "FWER"
        if spec.correction in (CorrectionMethod.BONFERRONI, CorrectionMethod.HOLM)
        else "FDR",
        spec.available_ns,
    )
    return tuple(rows), result

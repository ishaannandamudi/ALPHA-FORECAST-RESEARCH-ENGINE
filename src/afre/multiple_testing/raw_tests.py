"""Exact sign evidence and independent descriptive effects, with explicit assumptions."""

import statistics
from typing import TYPE_CHECKING

from afre.invariance.artifacts import EnvironmentMembership
from afre.multiple_testing.effects import EffectSizeResult
from afre.multiple_testing.hypotheses import HypothesisDefinition
from afre.multiple_testing.pvalues import PValueResult, fair_sign_pvalue
from afre.multiple_testing.schema import EvidenceState, RawTestMethod, TrialState
from afre.multiple_testing.trials import ResearchTrial, TrialSpecification
from afre.research_datasets.samples import ResearchSample
from afre.schema import require

if TYPE_CHECKING:
    from afre.multiple_testing.repository import MultipleTestingRepository


def raw_results_for(
    repo: "MultipleTestingRepository", trial_id: str, available_ns: int
) -> tuple[PValueResult, EffectSizeResult]:
    trial = repo.resolve(ResearchTrial, trial_id)
    plan = repo.resolve(TrialSpecification, trial.plan_id)
    h = repo.resolve(HypothesisDefinition, trial.hypothesis_id)
    require(trial.completed_ns <= available_ns, "raw evidence actually available after trial")
    values = tuple(o.value - h.null_value for o in trial.observations)
    informative = tuple(v for v in values if v != 0)
    n = len(informative)
    state, reason = (
        EvidenceState.AVAILABLE,
        "exact-conditional-fair-signs-caller-attested-independence",
    )
    assumptions = h.assumptions
    if trial.state is not TrialState.COMPLETED:
        state, reason = EvidenceState.INSUFFICIENT, "registered-failed-or-unavailable-trial"
    elif h.method not in (RawTestMethod.EXACT_SIGN, RawTestMethod.EXACT_PAIRED_SIGN):
        state, reason = (
            EvidenceState.UNSUPPORTED,
            "normal-mean-correlation-inference-not-implemented",
        )
    elif not (
        assumptions.independent_nonzero_signs
        and assumptions.conditional_fair_sign_null
        and assumptions.nonoverlapping_labels
        and (not plan.right_source_ids or assumptions.exact_pairing)
    ):
        state, reason = (
            EvidenceState.UNSUPPORTED,
            "required-independent-sign-null-pairing-assumptions-not-attested",
        )
    elif any(
        repo.resolve(EnvironmentMembership, i).weight not in (0.0, 1.0)
        for i in plan.membership_ids
    ):
        state, reason = (
            EvidenceState.UNSUPPORTED,
            "weighted-soft-cohort-sign-test-not-supported",
        )
    elif n < h.minimum_support:
        state, reason = (
            EvidenceState.INSUFFICIENT,
            "nonzero-sign-support-below-declared-minimum",
        )
    else:
        per_security: dict[str, list[ResearchSample]] = {}
        for observation in trial.observations:
            sample = repo.resolve(ResearchSample, observation.sample_id)
            per_security.setdefault(sample.security.fingerprint, []).append(sample)
        for samples in per_security.values():
            intervals = sorted(
                (s.target_interval for s in samples if s.target_interval),
                key=lambda i: i.start_ns,
            )
            if len(intervals) != len(samples) or any(
                a.overlaps(b) for a, b in zip(intervals, intervals[1:], strict=False)
            ):
                state, reason = (
                    EvidenceState.UNSUPPORTED,
                    "overlapping-or-unavailable-native-label-intervals",
                )
    positive = sum(v > 0 for v in informative)
    p = fair_sign_pvalue(positive, n, h.direction) if state is EvidenceState.AVAILABLE else None
    raw = PValueResult(
        trial_id,
        h.fingerprint,
        h.method,
        state,
        reason,
        p,
        positive / n if p is not None else None,
        len(values),
        n,
        len(values) - n,
        available_ns,
    )
    effect = EffectSizeResult(
        trial_id,
        h.fingerprint,
        float(statistics.median(values)) if values else None,
        trial.observations[0].unit if values else h.unit,
        len(values),
        EvidenceState.AVAILABLE if values else EvidenceState.INSUFFICIENT,
        available_ns,
    )
    return raw, effect

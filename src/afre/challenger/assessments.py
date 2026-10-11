"""Independent challenger assessments and explicit earlier-baseline rollback advice."""

from typing import TYPE_CHECKING

from afre.challenger.artifacts import (
    ChallengerComparison,
    EvaluationEvidence,
    ParticipantMetricResult,
    PromotionAssessment,
    RollbackAssessment,
)
from afre.challenger.criteria import PromotionCriterion, RollbackCriterion
from afre.challenger.participants import ParticipantReference
from afre.challenger.programs import ChallengeProgram
from afre.challenger.schema import (
    ChallengeDirection as D,
)
from afre.challenger.schema import (
    ChallengeStatus as S,
)
from afre.challenger.schema import (
    CriteriaPolicy,
)
from afre.challenger.schema import (
    PromotionOutcome as P,
)
from afre.challenger.schema import (
    RollbackOutcome as R,
)
from afre.health.artifacts import ModelHealthSnapshot
from afre.health.definitions import HealthSpec, MonitoredArtifactReference
from afre.health.schema import HealthStatus
from afre.schema import require

if TYPE_CHECKING:
    from afre.challenger.repository import ChallengeRepository


def comparison_for(
    program: ChallengeProgram,
    champion: ParticipantMetricResult,
    challenger: ParticipantMetricResult,
) -> ChallengerComparison:
    require(
        champion.common_id == challenger.common_id
        and champion.sample_ids == challenger.sample_ids
        and champion.truth_ids == challenger.truth_ids
        and champion.request_id == challenger.request_id,
        "comparison exact global support",
    )
    status = (
        S.AVAILABLE
        if champion.status is challenger.status is S.AVAILABLE
        else (
            S.INCOMPARABLE
            if S.INCOMPARABLE in (champion.status, challenger.status)
            else S.INSUFFICIENT_DATA
            if S.INSUFFICIENT_DATA in (champion.status, challenger.status)
            else S.UNAVAILABLE
        )
    )
    delta = (
        None
        if champion.value is None or challenger.value is None
        else challenger.value - champion.value
    )
    improvement = (
        None
        if delta is None or champion.orientation == "descriptive-only"
        else (delta if champion.orientation == "higher-is-better" else -delta)
    )
    return ChallengerComparison(
        program.fingerprint,
        champion.participant_id,
        challenger.participant_id,
        champion.request_id,
        champion.fingerprint,
        challenger.fingerprint,
        champion.common_id,
        delta,
        improvement,
        status,
        champion.orientation,
        champion.available_ns,
    )


def health_status(
    repo: "ChallengeRepository",
    program: ChallengeProgram,
    evidence: EvaluationEvidence,
    participant_id: str,
) -> HealthStatus | None:
    identity = dict(evidence.health_bindings).get(participant_id)
    if identity is None:
        return None
    require(
        participant_id in program.health_participant_ids, "health usage explicitly predeclared"
    )
    snapshot = repo.resolve(ModelHealthSnapshot, identity)
    spec = repo.resolve(HealthSpec, snapshot.spec_id)
    ref = repo.resolve(MonitoredArtifactReference, snapshot.reference_id)
    participant = repo.resolve(ParticipantReference, participant_id)
    require(
        ref.producer_id == participant.reference.producer_id
        and (spec.target_id, spec.horizon_id) == (program.target_id, program.horizon_id)
        and snapshot.cutoff_ns == program.window.cutoff_ns
        and spec.current_window.start_ns == program.window.start_ns
        and spec.current_window.end_ns == program.window.end_ns
        and snapshot.available_ns <= evidence.available_ns,
        "health exact participant target window cutoff and availability",
    )
    return snapshot.status


def promotion_for(
    repo: "ChallengeRepository",
    program: ChallengeProgram,
    evidence: EvaluationEvidence,
    challenger_id: str,
    comparisons: tuple[ChallengerComparison, ...],
) -> PromotionAssessment:
    by_request = {c.request_id: c for c in comparisons}
    checks: list[tuple[str, bool | None, str]] = []
    insufficient = incomparable = False
    context = {
        i
        for i, _, at, _ in (*program.context_records, *evidence.context_records)
        if at <= evidence.available_ns
    }
    for identity in program.promotion_criterion_ids:
        rule = repo.resolve(PromotionCriterion, identity)
        c = by_request[rule.request_id]
        metric = repo.resolve(ParticipantMetricResult, c.challenger_metric_id)
        if c.status is S.INCOMPARABLE:
            checks.append((identity, None, "incompatible-declared-participant-semantics"))
            incomparable = True
            continue
        if metric.count < rule.minimum_count or c.status is S.INSUFFICIENT_DATA:
            checks.append((identity, None, "minimum-common-support"))
            insufficient = True
            continue
        if (
            c.delta is None
            or c.status is not S.AVAILABLE
            or not set(rule.required_context_ids) <= context
        ):
            checks.append((identity, None, "incomparable-or-required-context-missing"))
            incomparable = True
            continue
        passed = (
            c.delta if rule.direction is D.HIGHER else -c.delta
        ) >= rule.required_improvement
        reason = "inclusive-explicit-improvement-threshold"
        for participant, allowed in (
            (program.champion_id, rule.champion_health),
            (challenger_id, rule.challenger_health),
        ):
            if allowed:
                status = health_status(repo, program, evidence, participant)
                if status is None:
                    incomparable = True
                    passed = False
                    reason = "required-health-context-missing"
                elif status not in allowed:
                    passed = False
                    reason = "required-health-status-not-satisfied"
        if rule.requires_cost:
            from afre.challenger.artifacts import CommonMatchedEvidence
            from afre.challenger.costs import cost_score
            from afre.challenger.schema import ChallengeMetric

            _, state, why = cost_score(
                repo,
                program,
                repo.resolve(CommonMatchedEvidence, c.common_id),
                challenger_id,
                ChallengeMetric.NET_EDGE,
            )
            if state is not S.AVAILABLE:
                passed, incomparable, reason = False, True, why
        checks.append((identity, passed, reason))
    results = [v for _, v, _ in checks]
    passed = (
        all(v is True for v in results)
        if program.criteria_policy is CriteriaPolicy.ALL_REQUIRED
        else any(v is True for v in results)
    )
    outcome = (
        P.PROMOTION_ELIGIBLE
        if passed
        else P.INCOMPARABLE
        if incomparable
        else (P.INSUFFICIENT_DATA if insufficient else P.PROMOTION_NOT_ELIGIBLE)
    )
    return PromotionAssessment(
        program.fingerprint,
        challenger_id,
        evidence.fingerprint,
        tuple(c.fingerprint for c in comparisons),
        tuple(checks),
        outcome,
        evidence.available_ns,
    )


def rollback_for(
    repo: "ChallengeRepository",
    program: ChallengeProgram,
    evidence: EvaluationEvidence,
    current: ParticipantMetricResult,
    rule: RollbackCriterion,
) -> RollbackAssessment:
    baseline = repo.resolve(ParticipantMetricResult, rule.baseline_metric_id)
    prior = repo.resolve(ChallengeProgram, baseline.program_id)
    now_ref = repo.resolve(ParticipantReference, current.participant_id).reference
    old_ref = repo.resolve(ParticipantReference, baseline.participant_id).reference
    compatible = (
        now_ref.producer_id == old_ref.producer_id
        and (current.target_id, current.horizon_id, current.unit, current.request_id)
        == (baseline.target_id, baseline.horizon_id, baseline.unit, baseline.request_id)
        and prior.window.end_ns <= program.window.start_ns
        and prior.cost_plan_id == program.cost_plan_id
    )
    delta = (
        None
        if current.value is None or baseline.value is None
        else current.value - baseline.value
    )
    deterioration = None if delta is None else delta if rule.direction is D.HIGHER else -delta
    reason = "inclusive-explicit-earlier-baseline-deterioration"
    if not compatible or current.status is S.INCOMPARABLE or baseline.status is S.INCOMPARABLE:
        outcome, reason = R.INCOMPARABLE, "rollback-incompatible-explicit-baseline"
    elif min(current.count, baseline.count) < rule.minimum_count:
        outcome, reason = R.INSUFFICIENT_DATA, "rollback-minimum-common-support"
    elif deterioration is None:
        outcome, reason = R.INCOMPARABLE, "rollback-native-metric-unavailable"
    else:
        passed = deterioration >= rule.deterioration_threshold
        if rule.required_health:
            status = health_status(repo, program, evidence, program.champion_id)
            if status is None:
                outcome, reason = R.INCOMPARABLE, "rollback-required-health-missing"
                return RollbackAssessment(
                    program.fingerprint,
                    program.champion_id,
                    evidence.fingerprint,
                    rule.fingerprint,
                    current.fingerprint,
                    baseline.fingerprint,
                    deterioration,
                    outcome,
                    evidence.available_ns,
                    reason,
                )
            passed = passed and status in rule.required_health
        outcome = R.ROLLBACK_ELIGIBLE if passed else R.ROLLBACK_NOT_ELIGIBLE
    return RollbackAssessment(
        program.fingerprint,
        program.champion_id,
        evidence.fingerprint,
        rule.fingerprint,
        current.fingerprint,
        baseline.fingerprint,
        deterioration,
        outcome,
        evidence.available_ns,
        reason,
    )

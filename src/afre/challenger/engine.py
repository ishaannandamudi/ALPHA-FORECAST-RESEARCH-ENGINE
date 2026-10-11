"""Explicit frozen programs, target-free wrapping, matched evaluation and manual advice."""

from collections.abc import Callable

from afre.challenger.artifacts import (
    ChallengerComparison,
    ChallengeRun,
    CommonMatchedEvidence,
    EvaluationEvidence,
    ParticipantMetricResult,
    PromotionAssessment,
    RollbackAssessment,
    ShadowForecast,
)
from afre.challenger.assessments import comparison_for, promotion_for, rollback_for
from afre.challenger.criteria import PromotionCriterion, RollbackCriterion
from afre.challenger.lineage import ChallengeAudit, audit_for
from afre.challenger.matching import common_for
from afre.challenger.metrics import metric_for
from afre.challenger.participants import ParticipantReference, participant_for
from afre.challenger.programs import ChallengeProgram
from afre.challenger.repository import ChallengeRepository
from afre.challenger.schema import ParticipantRole
from afre.challenger.shadow import shadow_for
from afre.schema import Artifact, require


def run_for(
    program: ChallengeProgram,
    evidence: EvaluationEvidence,
    common: CommonMatchedEvidence,
    metrics: tuple[ParticipantMetricResult, ...],
    comparisons: tuple[ChallengerComparison, ...],
    promotions: tuple[PromotionAssessment, ...],
    rollbacks: tuple[RollbackAssessment, ...],
) -> ChallengeRun:
    require(
        evidence.program_id == common.program_id == program.fingerprint
        and common.evidence_id == evidence.fingerprint,
        "run exact inputs",
    )
    require(
        {(m.participant_id, m.request_id) for m in metrics}
        == {
            (p, r.fingerprint)
            for p in (program.champion_id, *program.challenger_ids)
            for r in program.requests
        }
        and len(metrics) == (1 + len(program.challenger_ids)) * len(program.requests),
        "run complete participant metric grid",
    )
    require(
        {(c.challenger_id, c.request_id) for c in comparisons}
        == {(p, r.fingerprint) for p in program.challenger_ids for r in program.requests}
        and len(comparisons) == len(program.challenger_ids) * len(program.requests),
        "run complete independent comparison grid",
    )
    require(
        {p.challenger_id for p in promotions} == set(program.challenger_ids)
        and len(promotions) == len(program.challenger_ids)
        and {r.criterion_id for r in rollbacks} == set(program.rollback_criterion_ids)
        and len(rollbacks) == len(program.rollback_criterion_ids),
        "run exact advisory grid",
    )
    require(
        all(m.common_id == common.fingerprint for m in metrics)
        and all(c.common_id == common.fingerprint for c in comparisons)
        and all(p.evidence_id == evidence.fingerprint for p in promotions)
        and all(r.evidence_id == evidence.fingerprint for r in rollbacks),
        "run same evidence everywhere",
    )
    return ChallengeRun(
        program.fingerprint,
        program.champion_id,
        program.challenger_ids,
        evidence.fingerprint,
        common.fingerprint,
        tuple(m.fingerprint for m in metrics),
        tuple(c.fingerprint for c in comparisons),
        tuple(p.fingerprint for p in promotions),
        tuple(r.fingerprint for r in rollbacks),
        common.cutoff_ns,
        evidence.available_ns,
    )


class ChallengeEngine:
    def __init__(self, repository: ChallengeRepository) -> None:
        self.repository = repository

    def publish(self, values: tuple[Artifact, ...]) -> None:
        with self.repository.transaction(), self.repository.validation_cache():
            for value in values:
                self.repository.put(value)

    def participant(
        self,
        name: str,
        role: ParticipantRole,
        source_id: str,
        anchor_id: str | None = None,
        selection_id: str | None = None,
    ) -> ParticipantReference:
        with self.repository.read_snapshot(), self.repository.validation_cache():
            result = participant_for(
                self.repository, name, role, source_id, anchor_id, selection_id
            )
        self.publish((result.reference, result))
        return result

    def declare(
        self,
        program: ChallengeProgram,
        promotion: tuple[PromotionCriterion, ...],
        rollback: tuple[RollbackCriterion, ...] = (),
    ) -> ChallengeProgram:
        require(
            {r.fingerprint for r in promotion} == set(program.promotion_criterion_ids)
            and {r.fingerprint for r in rollback} == set(program.rollback_criterion_ids),
            "exact supplied frozen criteria",
        )
        self.publish(
            (program.bounds, program.window, *program.requests, *promotion, *rollback, program)
        )
        return program

    def shadow(
        self,
        program_id: str,
        participant_id: str,
        source_id: str,
        computed_ns: int,
        snapshot_hook: Callable[[], None] | None = None,
    ) -> ShadowForecast:
        with self.repository.feature_only():
            with self.repository.read_snapshot(), self.repository.validation_cache():
                program = self.repository.resolve(ChallengeProgram, program_id)
                if snapshot_hook:
                    snapshot_hook()
                result = shadow_for(
                    self.repository, program, participant_id, source_id, computed_ns
                )
            self.publish((result,))
        return result

    def evidence(self, value: EvaluationEvidence) -> EvaluationEvidence:
        self.publish((value,))
        return value

    def evaluate(
        self, evidence_id: str, snapshot_hook: Callable[[], None] | None = None
    ) -> ChallengeRun:
        repo = self.repository
        with repo.read_snapshot(), repo.validation_cache(), repo.pending_results():
            evidence = repo.resolve(EvaluationEvidence, evidence_id)
            program = repo.resolve(ChallengeProgram, evidence.program_id)
            if snapshot_hook:
                snapshot_hook()
            common = common_for(repo, program, evidence)
            repo.stage_result(common)
            metrics = tuple(
                metric_for(repo, program, common, p, r)
                for p in (program.champion_id, *program.challenger_ids)
                for r in program.requests
            )
            for metric in metrics:
                repo.stage_result(metric)
            by_key = {(m.participant_id, m.request_id): m for m in metrics}
            comparisons = tuple(
                comparison_for(
                    program,
                    by_key[program.champion_id, r.fingerprint],
                    by_key[p, r.fingerprint],
                )
                for p in program.challenger_ids
                for r in program.requests
            )
            for comparison in comparisons:
                repo.stage_result(comparison)
            promotions = tuple(
                promotion_for(
                    repo,
                    program,
                    evidence,
                    p,
                    tuple(c for c in comparisons if c.challenger_id == p),
                )
                for p in program.challenger_ids
            )
            rollbacks = tuple(
                rollback_for(
                    repo,
                    program,
                    evidence,
                    by_key[
                        program.champion_id,
                        (rule := repo.resolve(RollbackCriterion, i)).request_id,
                    ],
                    rule,
                )
                for i in program.rollback_criterion_ids
            )
            result = run_for(
                program, evidence, common, metrics, comparisons, promotions, rollbacks
            )
        self.publish((common, *metrics, *comparisons, *promotions, *rollbacks, result))
        return result

    def history(self, program_id: str) -> tuple[ChallengeRun, ...]:
        with self.repository.read_snapshot(), self.repository.validation_cache():
            identities = tuple(
                r[0]
                for r in self.repository._connection.execute(
                    "SELECT fingerprint FROM ch_records WHERE kind='ChallengeRun' "
                    "AND program_id=? "
                    "ORDER BY cutoff_ns,available_ns,fingerprint",
                    (program_id,),
                )
            )
            require(
                len(identities) <= self.repository.challenge_bounds.artifacts,
                "challenge history bound",
            )
            return tuple(self.repository.resolve(ChallengeRun, i) for i in identities)

    def audit(
        self, root_id: str, snapshot_hook: Callable[[], None] | None = None
    ) -> ChallengeAudit:
        with self.repository.read_snapshot(), self.repository.validation_cache():
            if snapshot_hook:
                snapshot_hook()
            result = audit_for(self.repository, root_id)
        self.publish((result,))
        return result

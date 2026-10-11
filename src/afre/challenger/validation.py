"""Semantic replay before reuse, in addition to hashes, schemas, indexes and exact links."""

from typing import TYPE_CHECKING

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
from afre.challenger.assessments import (
    comparison_for,
    health_status,
    promotion_for,
    rollback_for,
)
from afre.challenger.costs import ChallengeCostPlan
from afre.challenger.criteria import PromotionCriterion, RollbackCriterion
from afre.challenger.lineage import ChallengeAudit, audit_for
from afre.challenger.matching import common_for
from afre.challenger.metrics import metric_for
from afre.challenger.participants import ParticipantReference, participant_for
from afre.challenger.programs import ChallengeMetricRequest, ChallengeProgram
from afre.challenger.schema import ParticipantRole
from afre.challenger.shadow import shadow_for
from afre.costs.definitions import CostScenario
from afre.health.context import verify_context
from afre.invariance.definitions import EnvironmentDefinition
from afre.research_datasets.splits import FoldDefinition
from afre.schema import Artifact, require
from afre.target_engine.definitions import TargetDefinition
from afre.uncertainty.artifacts import ForecastUncertaintyDecomposition

if TYPE_CHECKING:
    from afre.challenger.repository import ChallengeRepository


def validate_program(repo: "ChallengeRepository", program: ChallengeProgram) -> None:
    participants = tuple(
        repo.resolve(ParticipantReference, i)
        for i in (program.champion_id, *program.challenger_ids)
    )
    require(
        participants[0].role is ParticipantRole.CHAMPION
        and all(p.role is ParticipantRole.CHALLENGER for p in participants[1:]),
        "exact explicit roles",
    )
    require(
        len({p.reference.producer_id for p in participants}) == len(participants),
        "duplicate logical participant producer",
    )
    require(
        all(p.reference.available_ns <= program.declared_ns for p in participants)
        or not program.predeclared,
        "program participants known at declaration",
    )
    fold = repo.resolve(FoldDefinition, program.fold_id)
    require(fold.dataset_id == program.dataset_id, "challenge exact fold/dataset")
    repo.resolve(TargetDefinition, program.target_id)
    requests = {r.fingerprint for r in program.requests}
    for r in program.requests:
        require(
            repo.resolve(ChallengeMetricRequest, r.fingerprint) == r, "frozen persisted request"
        )
    for identity in program.promotion_criterion_ids:
        criterion = repo.resolve(PromotionCriterion, identity)
        require(
            criterion.request_id in requests and criterion.declared_ns <= program.declared_ns,
            "promotion request and predeclared threshold",
        )
        require(
            not criterion.champion_health
            or program.champion_id in program.health_participant_ids,
            "champion health requirement predeclared",
        )
        require(
            not criterion.challenger_health
            or set(program.challenger_ids) <= set(program.health_participant_ids),
            "challenger health requirement predeclared",
        )
    for identity in program.rollback_criterion_ids:
        rule = repo.resolve(RollbackCriterion, identity)
        require(
            rule.request_id in requests and rule.declared_ns <= program.declared_ns,
            "rollback request and threshold predeclared",
        )
        require(
            not rule.required_health or program.champion_id in program.health_participant_ids,
            "rollback health requirement predeclared",
        )
    require(
        repo.get_any(program.window.fingerprint) == program.window
        and repo.get_any(program.bounds.fingerprint) == program.bounds,
        "frozen persisted window/bounds",
    )
    if program.cost_plan_id:
        plan = repo.resolve(ChallengeCostPlan, program.cost_plan_id)
        require(plan.declared_ns <= program.declared_ns, "predeclared cost plan")
    if program.environment_id:
        environment = repo.resolve(EnvironmentDefinition, program.environment_id)
        require(
            environment.target.fingerprint == program.target_id
            and environment.declared_ns <= program.declared_ns,
            "predeclared exact environment",
        )
    verify_context(repo, program.context_records)
    require(
        all(at <= program.declared_ns for _, _, at, _ in program.context_records),
        "program research context known at declaration",
    )
    for identity in program.uncertainty_ids:
        decomposition = repo.resolve(ForecastUncertaintyDecomposition, identity)
        require(
            decomposition.target_id == program.target_id
            and decomposition.available_ns <= program.window.cutoff_ns,
            "exact uncertainty target and cutoff",
        )


def validate_challenge(repo: "ChallengeRepository", value: Artifact) -> None:
    if isinstance(value, ParticipantReference):
        require(
            value.reference == repo.resolve(type(value.reference), value.reference.fingerprint),
            "persisted exact participant reference",
        )
        require(
            value
            == participant_for(
                repo,
                value.name,
                value.role,
                value.reference.artifact_id,
                value.reference.anchor_output_id,
                value.selection_result_id,
            ),
            "participant native provenance replay",
        )
    elif isinstance(value, ChallengeProgram):
        validate_program(repo, value)
    elif isinstance(value, (PromotionCriterion, ChallengeMetricRequest)):
        if isinstance(value, PromotionCriterion):
            repo.resolve(ChallengeMetricRequest, value.request_id)
    elif isinstance(value, RollbackCriterion):
        # Shadow paths certify the pinned baseline's canonical metadata only.
        # Its numerical truth-dependent replay belongs to declaration/evaluation/audit.
        baseline = (
            repo.get(ParticipantMetricResult, value.baseline_metric_id)
            if repo._feature_only_depth
            else repo.resolve(ParticipantMetricResult, value.baseline_metric_id)
        )
        require(
            baseline.request_id == value.request_id
            and baseline.available_ns <= value.declared_ns,
            "rollback exact earlier frozen baseline",
        )
    elif isinstance(value, ChallengeCostPlan):
        scenario = repo.resolve(CostScenario, value.template_scenario_id)
        require(
            scenario.declared_ns <= value.declared_ns, "cost plan retains native declaration"
        )
    elif isinstance(value, ShadowForecast):
        with repo.feature_only():
            program = repo.resolve(ChallengeProgram, value.program_id)
            require(
                value
                == shadow_for(
                    repo, program, value.participant_id, value.source_id, value.computed_ns
                ),
                "shadow target-free semantic replay",
            )
    elif isinstance(value, EvaluationEvidence):
        program = repo.resolve(ChallengeProgram, value.program_id)
        require(
            len(value.shadow_ids) <= program.bounds.shadow_rows
            and len(value.truth_assignments) <= program.bounds.samples,
            "program evidence configured bounds",
        )
        verify_context(repo, value.context_records)
        require(
            all(at <= value.available_ns for _, _, at, _ in value.context_records),
            "research evidence actual availability",
        )
        require(
            set(dict(value.health_bindings)) <= set(program.health_participant_ids),
            "health bindings predeclared participants",
        )
        require(
            set(dict(value.cost_bindings)) <= {program.champion_id, *program.challenger_ids},
            "cost bindings declared participants",
        )
        require(
            set(dict(value.breakeven_bindings)) <= set(dict(value.cost_bindings)),
            "break-even binds supplied exact cost participants",
        )
        for participant, _ in value.health_bindings:
            health_status(repo, program, value, participant)
        for identity in value.shadow_ids:
            repo.resolve(ShadowForecast, identity)
    elif isinstance(value, CommonMatchedEvidence):
        program = repo.resolve(ChallengeProgram, value.program_id)
        evidence = repo.resolve(EvaluationEvidence, value.evidence_id)
        require(
            value == common_for(repo, program, evidence), "common intersection semantic replay"
        )
    elif isinstance(value, ParticipantMetricResult):
        program = repo.resolve(ChallengeProgram, value.program_id)
        common = repo.resolve(CommonMatchedEvidence, value.common_id)
        request = repo.resolve(ChallengeMetricRequest, value.request_id)
        require(
            value.participant_id in (program.champion_id, *program.challenger_ids)
            and request in program.requests
            and common.program_id == program.fingerprint,
            "metric exact program participant/request/common",
        )
        require(
            value == metric_for(repo, program, common, value.participant_id, request),
            "participant metric numerical replay",
        )
    elif isinstance(value, ChallengerComparison):
        program = repo.resolve(ChallengeProgram, value.program_id)
        champion = repo.resolve(ParticipantMetricResult, value.champion_metric_id)
        challenger = repo.resolve(ParticipantMetricResult, value.challenger_metric_id)
        require(
            champion.participant_id == program.champion_id
            and challenger.participant_id in program.challenger_ids,
            "comparison exact roles",
        )
        require(
            value == comparison_for(program, champion, challenger), "comparison semantic replay"
        )
    elif isinstance(value, PromotionAssessment):
        program = repo.resolve(ChallengeProgram, value.program_id)
        evidence = repo.resolve(EvaluationEvidence, value.evidence_id)
        comparisons = tuple(repo.resolve(ChallengerComparison, i) for i in value.comparison_ids)
        require(
            value.challenger_id in program.challenger_ids
            and {c.request_id for c in comparisons} == {r.fingerprint for r in program.requests}
            and all(
                c.challenger_id == value.challenger_id and c.program_id == program.fingerprint
                for c in comparisons
            ),
            "promotion exact independent comparisons",
        )
        require(
            value == promotion_for(repo, program, evidence, value.challenger_id, comparisons),
            "promotion frozen threshold replay",
        )
    elif isinstance(value, RollbackAssessment):
        program = repo.resolve(ChallengeProgram, value.program_id)
        evidence = repo.resolve(EvaluationEvidence, value.evidence_id)
        metric = repo.resolve(ParticipantMetricResult, value.current_metric_id)
        criterion = repo.resolve(RollbackCriterion, value.criterion_id)
        require(
            criterion.fingerprint in program.rollback_criterion_ids
            and metric.participant_id == program.champion_id
            and metric.program_id == program.fingerprint,
            "rollback exact champion/program/criterion",
        )
        require(
            value == rollback_for(repo, program, evidence, metric, criterion), "rollback replay"
        )
    elif isinstance(value, ChallengeRun):
        from afre.challenger.engine import run_for

        program = repo.resolve(ChallengeProgram, value.program_id)
        evidence = repo.resolve(EvaluationEvidence, value.evidence_id)
        common = repo.resolve(CommonMatchedEvidence, value.common_id)
        metrics = tuple(repo.resolve(ParticipantMetricResult, i) for i in value.metric_ids)
        comparisons = tuple(repo.resolve(ChallengerComparison, i) for i in value.comparison_ids)
        promotions = tuple(repo.resolve(PromotionAssessment, i) for i in value.promotion_ids)
        rollbacks = tuple(repo.resolve(RollbackAssessment, i) for i in value.rollback_ids)
        require(
            value
            == run_for(program, evidence, common, metrics, comparisons, promotions, rollbacks),
            "run complete immutable evidence replay",
        )
    elif isinstance(value, ChallengeAudit):
        require(value == audit_for(repo, value.root_id), "challenge audit semantic replay")

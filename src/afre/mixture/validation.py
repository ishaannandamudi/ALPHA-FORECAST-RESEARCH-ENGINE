"""Fail-closed semantic replay with truth-free forecast replay and explicit later scoring."""

from typing import TYPE_CHECKING

from afre.feature_store.models import QualifiedHistoricalDelivery, SourceReference
from afre.mixture.artifacts import (
    GateDriftDiagnostic,
    GateModelArtifact,
    GateTrainingRow,
    MixtureAudit,
    MixtureCalibrationAssessment,
    MixtureComponent,
    MixtureDiagnostics,
    MixtureDistribution,
    MixtureEvaluation,
    MixtureForecast,
    MixtureRankEvaluation,
    MixtureRanking,
    MixtureRequest,
)
from afre.mixture.availability import binding_for, gating_value_for, validate_expert
from afre.mixture.calibration import assessment_for
from afre.mixture.definitions import ExpertSet, FixedGateSpec, LearnedGateSpec
from afre.mixture.diagnostics import diagnostics_for, drift_for
from afre.mixture.evaluation import evaluation_for
from afre.mixture.experts import (
    ExpertForecastBinding,
    ExpertReference,
    ExternalExpertForecast,
    GatingFeatureReference,
)
from afre.mixture.fitting import fit_for, row_for
from afre.mixture.forecasts import forecast_for
from afre.research_datasets.splits import TestEvaluation
from afre.schema import Artifact, require

if TYPE_CHECKING:
    from afre.mixture.repository import MixtureRepository


def validate_mixture(repo: "MixtureRepository", value: Artifact) -> None:
    if isinstance(value, ExpertReference):
        validate_expert(repo, value)
    elif isinstance(value, ExternalExpertForecast):
        require(
            repo.resolve(ExpertReference, value.expert.fingerprint) == value.expert
            and repo.resolve(SourceReference, value.source.fingerprint) == value.source,
            "external expert source/producer evidence",
        )
        if value.clocks.historical_delivery:
            require(
                repo.resolve(
                    QualifiedHistoricalDelivery, value.clocks.historical_delivery.fingerprint
                )
                == value.clocks.historical_delivery,
                "external qualified evidence",
            )
    elif isinstance(value, ExpertForecastBinding):
        require(
            value
            == binding_for(
                repo, repo.resolve(ExpertReference, value.expert_id), value.forecast_id
            ),
            "expert forecast binding contamination",
        )
    elif isinstance(value, GatingFeatureReference):
        gating_value_for(repo, value)
    elif isinstance(value, ExpertSet):
        require(
            repo.get_any(value.target.fingerprint) == value.target
            and all(repo.resolve(ExpertReference, e.fingerprint) == e for e in value.experts),
            "expert set exact target/producers",
        )
    elif isinstance(value, (FixedGateSpec, LearnedGateSpec)):
        require(
            repo.resolve(ExpertSet, value.expert_set.fingerprint) == value.expert_set,
            "gate exact expert set",
        )
        if isinstance(value, LearnedGateSpec):
            require(
                repo.resolve_fold(value.fold_id).training_cutoff_ns == value.cutoff_ns,
                "gate exact fold cutoff",
            )
    elif isinstance(value, GateTrainingRow):
        require(
            value
            == row_for(
                repo,
                repo.resolve(LearnedGateSpec, value.spec_id),
                value.sample_id,
                value.binding_ids,
                value.feature_ids,
            ),
            "gate TRAIN row contamination",
        )
    elif isinstance(value, GateModelArtifact):
        require(
            value
            == fit_for(
                repo,
                repo.resolve(LearnedGateSpec, value.spec_id),
                value.rows,
                value.fit_started_ns,
                value.fit_completed_ns,
                value.available_ns,
            ),
            "gate model numerical/TRAIN contamination",
        )
    elif isinstance(value, MixtureComponent):
        b = repo.resolve(ExpertForecastBinding, value.binding_id)
        require(
            value.expert_id == b.expert_id and value.distribution == b.distribution,
            "mixture component exact original law",
        )
    elif isinstance(value, MixtureDistribution):
        require(
            all(repo.resolve(MixtureComponent, c.fingerprint) == c for c in value.components),
            "mixture distribution exact components",
        )
    elif isinstance(value, MixtureRequest):
        forecast_for(repo, value)
    elif isinstance(value, MixtureForecast):
        require(
            value == forecast_for(repo, value.request)
            and repo.resolve(MixtureRequest, value.request.fingerprint) == value.request,
            "mixture forecast contamination",
        )
        if value.distribution:
            require(
                repo.resolve(MixtureDistribution, value.distribution.fingerprint)
                == value.distribution,
                "mixture forecast distribution evidence",
            )
    elif isinstance(value, MixtureEvaluation):
        seal = (
            repo.resolve(TestEvaluation, value.test_evaluation_id)
            if value.test_evaluation_id
            else None
        )
        require(
            value
            == evaluation_for(
                repo,
                value.forecast_ids,
                value.cutoff_ns,
                value.available_ns,
                seal,
                value.thresholds,
            ),
            "mixture evaluation contamination",
        )
    elif isinstance(value, MixtureDiagnostics):
        require(
            value == diagnostics_for(repo, value.evaluation_id),
            "mixture diagnostics contamination",
        )
    elif isinstance(value, GateDriftDiagnostic):
        require(
            value
            == drift_for(
                repo,
                value.reference_diagnostics_id,
                value.current_diagnostics_id,
                value.cutoff_ns,
                value.minimum_count,
            ),
            "gate drift contamination",
        )
    elif isinstance(value, MixtureCalibrationAssessment):
        require(
            value
            == assessment_for(
                repo,
                value.forecast_id,
                value.observation_ids,
                value.cutoff_ns,
                value.minimum_count,
                value.proposed_component_state_id,
            ),
            "mixture calibration contamination",
        )
    elif isinstance(value, MixtureRanking):
        from afre.mixture.cross_sectional import ranking_for

        require(
            value == ranking_for(repo, value.ranking_id, value.forecast_ids),
            "mixture ranking contamination",
        )
    elif isinstance(value, MixtureRankEvaluation):
        from afre.cross_sectional.artifacts import CrossSectionEvaluation, CrossSectionTruth

        rank = repo.resolve(MixtureRanking, value.mixture_ranking_id)
        evaluation = repo.resolve(MixtureEvaluation, value.matched_evaluation_id)
        cs = repo.resolve(CrossSectionEvaluation, value.cross_section_evaluation_id)
        truth = repo.resolve(CrossSectionTruth, cs.truth_id)
        require(
            set(evaluation.forecast_ids) == set(rank.forecast_ids)
            and cs.ranking_id == rank.ranking_id
            and evaluation.cutoff_ns == cs.cutoff_ns
            and {p.target_id for p in evaluation.pairs}
            == {r.target_id for r in truth.rows if r.value is not None},
            "mixture rank exact matched truth/TEST evidence",
        )
    elif isinstance(value, MixtureAudit):
        from afre.mixture.lineage import lineage_for

        require(value == lineage_for(repo, value.root_id), "mixture lineage contamination")

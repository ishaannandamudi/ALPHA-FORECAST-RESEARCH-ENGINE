"""Fail-closed semantic replay; application replay deliberately does not refit TRAIN."""

from typing import TYPE_CHECKING

from afre.feature_store.models import QualifiedHistoricalDelivery, SourceReference
from afre.regime_conditioned.artifacts import (
    RegimeAudit,
    RegimeCalibrationAssessment,
    RegimeConditionedEvaluation,
    RegimeConditionedForecast,
    RegimeConditionedModel,
    RegimeConditionedSample,
    RegimeDriftDiagnostic,
    RegimeMatchSet,
    RegimeRankEvaluation,
    RegimeRanking,
    RegimeTransition,
)
from afre.regime_conditioned.calibration import assessment_for
from afre.regime_conditioned.cross_sectional import ranking_for
from afre.regime_conditioned.definitions import RegimeConditioningSpec
from afre.regime_conditioned.drift import drift_for
from afre.regime_conditioned.evaluation import evaluation_for
from afre.regime_conditioned.fitting import fit_for
from afre.regime_conditioned.forecasts import forecast_for
from afre.regime_conditioned.matching import base_context, matching_for, observation_for
from afre.regime_conditioned.regimes import (
    RegimeProviderReference,
    RegimeSnapshot,
    RegimeTaxonomy,
)
from afre.regime_conditioned.transitions import transition_for
from afre.research_datasets.splits import TestEvaluation
from afre.schema import Artifact, require

if TYPE_CHECKING:
    from afre.regime_conditioned.repository import RegimeRepository


def validate_regime(repo: "RegimeRepository", value: Artifact) -> None:
    if isinstance(value, RegimeProviderReference):
        require(
            repo.resolve(SourceReference, value.source.fingerprint) == value.source,
            "regime provider exact source",
        )
    elif isinstance(value, RegimeTaxonomy):
        require(
            repo.resolve(RegimeProviderReference, value.provider.fingerprint) == value.provider,
            "regime taxonomy provider evidence",
        )
    elif isinstance(value, RegimeSnapshot):
        require(
            repo.resolve(RegimeTaxonomy, value.taxonomy.fingerprint) == value.taxonomy
            and repo.resolve(SourceReference, value.source.fingerprint) == value.source,
            "regime snapshot taxonomy/source evidence",
        )
        if value.clocks.historical_delivery:
            proof = value.clocks.historical_delivery
            require(
                repo.resolve(QualifiedHistoricalDelivery, proof.fingerprint) == proof,
                "regime qualified historical evidence",
            )
    elif isinstance(value, RegimeConditioningSpec):
        base_context(repo, value)
    elif isinstance(value, RegimeMatchSet):
        require(
            value
            == matching_for(
                repo,
                repo.resolve(RegimeConditioningSpec, value.spec_id),
                value.sample_id,
                value.candidate_ids,
                value.mapping_ids,
            ),
            "regime matching contamination",
        )
    elif isinstance(value, RegimeConditionedSample):
        match = repo.resolve(RegimeMatchSet, value.matches_id)
        repo._validate_links(match)
        expected, transitions = observation_for(repo, match)
        require(
            value == expected
            and all(repo.resolve(RegimeTransition, t.fingerprint) == t for t in transitions),
            "regime sample/transition contamination",
        )
    elif isinstance(value, RegimeTransition):
        require(
            value
            == transition_for(
                repo.resolve(RegimeSnapshot, value.previous_id),
                repo.resolve(RegimeSnapshot, value.current_id),
            ),
            "regime transition contamination",
        )
    elif isinstance(value, RegimeConditionedModel):
        require(
            value
            == fit_for(
                repo,
                repo.resolve(RegimeConditioningSpec, value.spec_id),
                value.observation_ids,
                value.fit_started_ns,
                value.fit_completed_ns,
                value.available_ns,
            ),
            "regime TRAIN model contamination",
        )
    elif isinstance(value, RegimeConditionedForecast):
        require(
            value
            == forecast_for(
                repo,
                repo.resolve(RegimeConditionedModel, value.model_id),
                repo.resolve(RegimeConditionedSample, value.observation_id),
                value.base_forecast_id,
                value.base_probability_id,
                value.computed_ns,
            ),
            "regime forecast contamination",
        )
    elif isinstance(value, RegimeConditionedEvaluation):
        seal = (
            repo.resolve(TestEvaluation, value.test_evaluation_id)
            if value.test_evaluation_id
            else None
        )
        require(
            value
            == evaluation_for(
                repo, value.forecast_ids, value.cutoff_ns, value.available_ns, seal
            ),
            "regime matched evaluation contamination",
        )
    elif isinstance(value, RegimeCalibrationAssessment):
        require(
            value
            == assessment_for(
                repo,
                value.forecast_id,
                value.observation_forecast_ids,
                value.cutoff_ns,
                value.minimum_count,
                value.proposed_global_state_id,
            ),
            "regime calibration contamination",
        )
    elif isinstance(value, RegimeDriftDiagnostic):
        require(
            value
            == drift_for(
                repo,
                value.reference_evaluation_id,
                value.current_evaluation_id,
                value.cutoff_ns,
                value.minimum_count,
            ),
            "regime drift contamination",
        )
    elif isinstance(value, RegimeRanking):
        require(
            value == ranking_for(repo, value.ranking_id, value.forecast_ids),
            "regime ranking contamination",
        )
    elif isinstance(value, RegimeRankEvaluation):
        from afre.cross_sectional.artifacts import CrossSectionEvaluation, CrossSectionTruth

        rank = repo.resolve(RegimeRanking, value.regime_ranking_id)
        evaluation = repo.resolve(RegimeConditionedEvaluation, value.matched_evaluation_id)
        cs = repo.resolve(CrossSectionEvaluation, value.cross_section_evaluation_id)
        truth = repo.resolve(CrossSectionTruth, cs.truth_id)
        require(
            set(evaluation.forecast_ids) == set(rank.forecast_ids)
            and cs.ranking_id == rank.ranking_id
            and evaluation.cutoff_ns == cs.cutoff_ns
            and {p.target_id for p in evaluation.pairs}
            == {r.target_id for r in truth.rows if r.value is not None},
            "regime rank matched truth/TEST contamination",
        )
    elif isinstance(value, RegimeAudit):
        from afre.regime_conditioned.lineage import lineage_for

        require(value == lineage_for(repo, value.root_id), "regime lineage contamination")

"""Fail-closed replay of event semantics without truth reads during application."""

from typing import TYPE_CHECKING

from afre.event_conditioned.artifacts import (
    EventAudit,
    EventCalibrationAssessment,
    EventConditionedEvaluation,
    EventConditionedForecast,
    EventConditionedModel,
    EventConditionedObservation,
    EventMatchSet,
    EventRankEvaluation,
    EventRanking,
)
from afre.event_conditioned.calibration import assessment_for
from afre.event_conditioned.cross_sectional import ranking_for
from afre.event_conditioned.definitions import EventConditioningSpec, EventWindowSpec
from afre.event_conditioned.evaluation import evaluation_for
from afre.event_conditioned.events import EventReference, EventSurprise, EventValue
from afre.event_conditioned.fitting import fit_for
from afre.event_conditioned.forecasts import forecast_for
from afre.event_conditioned.matching import base_context, matching_for, observations_for
from afre.feature_store.models import QualifiedHistoricalDelivery, SourceReference
from afre.research_datasets.splits import TestEvaluation
from afre.schema import Artifact, require

if TYPE_CHECKING:
    from afre.event_conditioned.repository import EventRepository


def validate_event(repo: "EventRepository", value: Artifact) -> None:
    if isinstance(value, (EventValue, EventReference)):
        require(
            repo.resolve(SourceReference, value.source.fingerprint) == value.source,
            "event source evidence",
        )
        if value.clocks.historical_delivery:
            proof = value.clocks.historical_delivery
            require(
                proof.source_id == value.source.fingerprint
                and repo.resolve(QualifiedHistoricalDelivery, proof.fingerprint) == proof,
                "event historical delivery evidence",
            )
        if isinstance(value, EventReference):
            for attr in (value.materiality, value.novelty, value.surprise):
                if attr:
                    require(repo.get_any(attr.fingerprint) == attr, "event component identity")
    elif isinstance(value, EventSurprise):
        require(
            repo.resolve(EventValue, value.actual.fingerprint) == value.actual
            and repo.resolve(EventValue, value.expected.fingerprint) == value.expected,
            "surprise input evidence",
        )
    elif isinstance(value, EventConditioningSpec):
        base_context(repo, value)
        require(
            repo.resolve(EventWindowSpec, value.window.fingerprint) == value.window,
            "event window evidence",
        )
    elif isinstance(value, EventMatchSet):
        require(
            value
            == matching_for(
                repo,
                repo.resolve(EventConditioningSpec, value.spec_id),
                value.sample_id,
                value.event_ids,
                value.reaction_ids,
                value.mapping_ids,
            ),
            "event match/overlap contamination",
        )
    elif isinstance(value, EventConditionedObservation):
        require(
            value in observations_for(repo, repo.resolve(EventMatchSet, value.matches_id)),
            "event observation contamination",
        )
        repo._validate_links(repo.resolve(EventMatchSet, value.matches_id))
    elif isinstance(value, EventConditionedModel):
        require(
            value
            == fit_for(
                repo,
                repo.resolve(EventConditioningSpec, value.spec_id),
                value.observation_ids,
                value.fit_started_ns,
                value.fit_completed_ns,
                value.available_ns,
            ),
            "event TRAIN model contamination",
        )
    elif isinstance(value, EventConditionedForecast):
        require(
            value
            == forecast_for(
                repo,
                repo.resolve(EventConditionedModel, value.model_id),
                repo.resolve(EventConditionedObservation, value.observation_id),
                value.base_forecast_id,
                value.base_probability_id,
                value.computed_ns,
            ),
            "event forecast/reaction contamination",
        )
    elif isinstance(value, EventConditionedEvaluation):
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
            "event matched evaluation contamination",
        )
    elif isinstance(value, EventCalibrationAssessment):
        require(
            value
            == assessment_for(
                repo,
                value.forecast_id,
                value.observation_forecast_ids,
                value.cutoff_ns,
                value.minimum_count,
            ),
            "event calibration evidence contamination",
        )
    elif isinstance(value, EventRanking):
        require(
            value == ranking_for(repo, value.ranking_id, value.forecast_ids),
            "event ranking source contamination",
        )
    elif isinstance(value, EventRankEvaluation):
        from afre.cross_sectional.artifacts import CrossSectionEvaluation, CrossSectionTruth

        rank = repo.resolve(EventRanking, value.event_ranking_id)
        evaluation = repo.resolve(EventConditionedEvaluation, value.matched_evaluation_id)
        cs = repo.resolve(CrossSectionEvaluation, value.cross_section_evaluation_id)
        truth = repo.resolve(CrossSectionTruth, cs.truth_id)
        require(
            set(evaluation.forecast_ids) == set(rank.forecast_ids)
            and cs.ranking_id == rank.ranking_id
            and evaluation.cutoff_ns == cs.cutoff_ns
            and {p.target_id for p in evaluation.pairs}
            == {r.target_id for r in truth.rows if r.value is not None},
            "event rank matched truth/TEST contamination",
        )
    elif isinstance(value, EventAudit):
        from afre.event_conditioned.lineage import lineage_for

        require(value == lineage_for(repo, value.root_id), "event lineage contamination")

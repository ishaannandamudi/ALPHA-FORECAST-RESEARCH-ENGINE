"""Explicit assessment boundary; AFRE-7 states cannot silently calibrate new semantics."""

from typing import TYPE_CHECKING

from afre.event_conditioned.artifacts import (
    EventCalibrationAssessment,
    EventConditionedForecast,
    EventConditionedModel,
    EventConditionedObservation,
)
from afre.event_conditioned.schema import EventCalibrationStatus
from afre.schema import require
from afre.statistical_models.schema import PredictionScope
from afre.target_engine.models import TargetVintage
from afre.target_engine.validation import target_known_by_cutoff

if TYPE_CHECKING:
    from afre.event_conditioned.repository import EventRepository


def assessment_for(
    repo: "EventRepository",
    forecast_id: str,
    ids: tuple[str, ...],
    cutoff_ns: int,
    minimum_count: int,
) -> EventCalibrationAssessment:
    require(
        len(ids) <= repo.event_bounds.samples and len(set(ids)) == len(ids),
        "event calibration count bound",
    )
    reference = repo.resolve(EventConditionedForecast, forecast_id)
    require(reference.available_ns <= cutoff_ns, "event calibration reference unavailable")
    model = repo.resolve(EventConditionedModel, reference.model_id)
    training = {
        repo.resolve(EventConditionedObservation, i).sample_id for i in model.observation_ids
    }
    samples: set[str] = set()
    for identity in ids:
        f = repo.resolve(EventConditionedForecast, identity)
        o = repo.resolve(EventConditionedObservation, f.observation_id)
        require(
            f.model_id == reference.model_id
            and o.scope is PredictionScope.VALIDATION
            and o.sample_id not in training
            and f.available_ns <= cutoff_ns,
            "event calibration exact non-TRAIN/non-TEST evidence",
        )
        require(
            o.target_id is not None
            and target_known_by_cutoff(repo.resolve(TargetVintage, o.target_id), cutoff_ns),
            "event calibration truth unavailable",
        )
        require(o.sample_id not in samples, "duplicate event calibration sample")
        samples.add(o.sample_id)
    status = (
        EventCalibrationStatus.INSUFFICIENT_DATA
        if len(ids) < minimum_count
        else EventCalibrationStatus.UNAVAILABLE
    )
    return EventCalibrationAssessment(
        forecast_id,
        tuple(sorted(ids)),
        cutoff_ns,
        minimum_count,
        status,
        "insufficient-independent-observations"
        if len(ids) < minimum_count
        else "conditioned-calibration-fitting-not-implemented",
    )

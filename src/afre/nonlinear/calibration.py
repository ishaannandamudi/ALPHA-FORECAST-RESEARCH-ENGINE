"""Exact assessment only; upstream AFRE-7 states do not transfer to nonlinear laws."""

from typing import TYPE_CHECKING

from afre.calibration.artifacts import CalibrationState
from afre.nonlinear.artifacts import (
    NonlinearCalibrationAssessment,
    NonlinearForecast,
    NonlinearModelArtifact,
)
from afre.nonlinear.schema import NonlinearCalibrationStatus
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.schema import require
from afre.target_engine.models import TargetVintage
from afre.target_engine.validation import target_known_by_cutoff

if TYPE_CHECKING:
    from afre.nonlinear.repository import NonlinearRepository


def assessment_for(
    repo: "NonlinearRepository",
    forecast_id: str,
    ids: tuple[str, ...],
    cutoff_ns: int,
    minimum_count: int,
    proposed_state_id: str | None,
) -> NonlinearCalibrationAssessment:
    require(
        len(ids) <= repo.nonlinear_bounds.forecasts and len(set(ids)) == len(ids),
        "calibration evidence bound",
    )
    forecast = repo.resolve(NonlinearForecast, forecast_id)
    require(forecast.available_ns <= cutoff_ns, "calibration reference available")
    model = repo.resolve(NonlinearModelArtifact, forecast.model_id)
    samples: set[str] = set()
    for identity in sorted(ids):
        value = repo.resolve(NonlinearForecast, identity)
        sample = repo.resolve(ResearchSample, value.sample_id)
        require(
            value.model_id == forecast.model_id
            and value.partition is Partition.VALIDATION
            and value.sample_id not in model.train_sample_ids
            and value.sample_id not in samples
            and value.available_ns <= cutoff_ns,
            "independent nonlinear non-TRAIN/non-TEST calibration evidence",
        )
        require(
            sample.target_id is not None
            and target_known_by_cutoff(
                repo.resolve(TargetVintage, sample.target_id), cutoff_ns
            ),
            "calibration known truth",
        )
        samples.add(value.sample_id)
    if proposed_state_id:
        repo.resolve(CalibrationState, proposed_state_id)
    status = (
        NonlinearCalibrationStatus.INCOMPATIBLE
        if proposed_state_id
        else NonlinearCalibrationStatus.INSUFFICIENT_DATA
        if len(ids) < minimum_count
        else NonlinearCalibrationStatus.UNAVAILABLE
    )
    return NonlinearCalibrationAssessment(
        forecast_id, tuple(ids), proposed_state_id, minimum_count, cutoff_ns, status
    )

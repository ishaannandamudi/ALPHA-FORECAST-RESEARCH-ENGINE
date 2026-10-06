"""Dedicated assessment only; earlier AFRE-7 calibrators never silently transfer."""

from typing import TYPE_CHECKING

from afre.calibration.artifacts import CalibrationState
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.schema import require
from afre.sequence.artifacts import SequenceCalibrationAssessment, SequenceForecast
from afre.target_engine.models import TargetVintage
from afre.target_engine.validation import target_known_by_cutoff

if TYPE_CHECKING:
    from afre.sequence.repository import SequenceRepository


def assessment_for(
    repo: "SequenceRepository",
    forecast_id: str,
    ids: tuple[str, ...],
    cutoff_ns: int,
    minimum_count: int = 2,
    proposed_state_id: str | None = None,
) -> SequenceCalibrationAssessment:
    forecast = repo.resolve(SequenceForecast, forecast_id)
    require(
        len(ids) <= repo.sequence_bounds.forecasts and len(set(ids)) == len(ids),
        "sequence calibration observation bound/duplicates",
    )
    for identity in ids:
        obs = repo.resolve(SequenceForecast, identity)
        require(
            obs.model_id == forecast.model_id
            and obs.partition is Partition.VALIDATION
            and obs.available_ns <= cutoff_ns,
            "independent non-TRAIN/non-TEST sequence calibration",
        )
        sample = repo.resolve(ResearchSample, obs.sample_id)
        require(sample.target_id is not None, "calibration truth required")
        assert sample.target_id is not None
        target = repo.resolve(TargetVintage, sample.target_id)
        require(
            target_known_by_cutoff(target, cutoff_ns) and target.origin == obs.origin,
            "sequence calibration exact known truth",
        )
    if proposed_state_id:
        repo.resolve(CalibrationState, proposed_state_id)
        status = "incompatible"
    else:
        status = "insufficient" if len(ids) < minimum_count else "unavailable"
    return SequenceCalibrationAssessment(
        forecast_id, ids, cutoff_ns, minimum_count, proposed_state_id, status
    )

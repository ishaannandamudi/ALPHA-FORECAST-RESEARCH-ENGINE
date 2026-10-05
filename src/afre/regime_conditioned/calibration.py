"""Exact non-TEST evidence assessment; global calibration cannot silently transfer."""

from typing import TYPE_CHECKING

from afre.calibration.artifacts import CalibrationState
from afre.regime_conditioned.artifacts import (
    RegimeCalibrationAssessment,
    RegimeConditionedForecast,
    RegimeConditionedModel,
    RegimeConditionedSample,
)
from afre.regime_conditioned.schema import RegimeCalibrationStatus
from afre.schema import require
from afre.statistical_models.schema import PredictionScope
from afre.target_engine.models import TargetVintage
from afre.target_engine.validation import target_known_by_cutoff

if TYPE_CHECKING:
    from afre.regime_conditioned.repository import RegimeRepository


def assessment_for(
    repo: "RegimeRepository",
    forecast_id: str,
    ids: tuple[str, ...],
    cutoff_ns: int,
    minimum_count: int,
    global_state_id: str | None,
) -> RegimeCalibrationAssessment:
    require(
        len(ids) <= repo.regime_bounds.samples and len(set(ids)) == len(ids),
        "regime calibration input bound/duplicates",
    )
    reference = repo.resolve(RegimeConditionedForecast, forecast_id)
    require(reference.available_ns <= cutoff_ns, "regime calibration reference unavailable")
    model = repo.resolve(RegimeConditionedModel, reference.model_id)
    training = {
        repo.resolve(RegimeConditionedSample, i).sample_id for i in model.observation_ids
    }
    samples: set[str] = set()
    for identity in sorted(ids):
        f = repo.resolve(RegimeConditionedForecast, identity)
        o = repo.resolve(RegimeConditionedSample, f.observation_id)
        require(
            f.model_id == reference.model_id
            and f.membership == reference.membership
            and o.scope is PredictionScope.VALIDATION
            and o.sample_id not in training
            and f.available_ns <= cutoff_ns,
            "regime calibration exact non-TRAIN/non-TEST evidence",
        )
        require(
            o.target_id is not None
            and target_known_by_cutoff(repo.resolve(TargetVintage, o.target_id), cutoff_ns),
            "regime calibration truth unavailable",
        )
        require(o.sample_id not in samples, "duplicate regime calibration sample")
        samples.add(o.sample_id)
    if global_state_id:
        repo.resolve(CalibrationState, global_state_id)
    status = (
        RegimeCalibrationStatus.INCOMPATIBLE
        if global_state_id
        else RegimeCalibrationStatus.INSUFFICIENT_DATA
        if len(ids) < minimum_count
        else RegimeCalibrationStatus.UNAVAILABLE
    )
    return RegimeCalibrationAssessment(
        forecast_id,
        tuple(sorted(ids)),
        cutoff_ns,
        minimum_count,
        status,
        "global-calibration-has-different-conditioned-semantics"
        if global_state_id
        else "insufficient-independent-regime-observations"
        if len(ids) < minimum_count
        else "dedicated-regime-calibration-fitting-not-implemented",
        global_state_id,
    )

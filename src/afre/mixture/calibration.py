"""Dedicated mixture compatibility assessment; component calibration never transfers."""

from typing import TYPE_CHECKING

from afre.calibration.artifacts import CalibrationState
from afre.mixture.artifacts import (
    GateModelArtifact,
    MixtureCalibrationAssessment,
    MixtureForecast,
)
from afre.mixture.schema import MixtureCalibrationStatus
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.schema import require
from afre.target_engine.models import TargetVintage
from afre.target_engine.validation import target_known_by_cutoff

if TYPE_CHECKING:
    from afre.mixture.repository import MixtureRepository


def assessment_for(
    repo: "MixtureRepository",
    forecast_id: str,
    ids: tuple[str, ...],
    cutoff_ns: int,
    minimum_count: int,
    component_state_id: str | None,
) -> MixtureCalibrationAssessment:
    require(
        len(ids) <= repo.mixture_bounds.forecasts and len(set(ids)) == len(ids),
        "mixture calibration input bound/duplicates",
    )
    reference = repo.resolve(MixtureForecast, forecast_id)
    require(reference.available_ns <= cutoff_ns, "mixture calibration reference unavailable")
    training = (
        set(
            r.sample_id for r in repo.resolve(GateModelArtifact, reference.request.gate_id).rows
        )
        if reference.request.gate_id.startswith("afre.mix_gate_model:")
        else set()
    )
    samples: set[str] = set()
    for identity in sorted(ids):
        f = repo.resolve(MixtureForecast, identity)
        sample = repo.resolve(ResearchSample, f.request.sample_id)
        require(
            f.request.gate_id == reference.request.gate_id
            and f.request.expert_set_id == reference.request.expert_set_id
            and f.partition is Partition.VALIDATION
            and sample.fingerprint not in training
            and sample.fingerprint not in samples
            and f.available_ns <= cutoff_ns,
            "mixture calibration exact independent non-TRAIN/non-TEST evidence",
        )
        require(
            sample.target_id is not None
            and target_known_by_cutoff(
                repo.resolve(TargetVintage, sample.target_id), cutoff_ns
            ),
            "mixture calibration truth unavailable",
        )
        samples.add(sample.fingerprint)
    if component_state_id:
        repo.resolve(CalibrationState, component_state_id)
    status = (
        MixtureCalibrationStatus.INCOMPATIBLE
        if component_state_id
        else MixtureCalibrationStatus.INSUFFICIENT_DATA
        if len(samples) < minimum_count
        else MixtureCalibrationStatus.UNAVAILABLE
    )
    return MixtureCalibrationAssessment(
        forecast_id, tuple(sorted(ids)), cutoff_ns, minimum_count, status, component_state_id
    )

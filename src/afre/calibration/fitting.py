"""Frozen calibration sample and deterministic transformations, separate from raw fit."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from afre.calibration.application import outputs_for
from afre.calibration.artifacts import (
    CalibrationDiagnostics,
    CalibrationFitInputs,
    CalibrationFitRun,
    CalibrationObservationSet,
    CalibrationState,
    ConformalScoreSet,
    ProbabilityMapping,
    QuantileOffset,
)
from afre.calibration.conformal import scores_for
from afre.calibration.definitions import CalibrationRequest, CalibrationSpec
from afre.calibration.diagnostics import diagnostics_for
from afre.calibration.partitions import overlap_status, spec_context
from afre.calibration.probability import mapping_for
from afre.calibration.quantile import offset_for
from afre.calibration.samples import observations_for
from afre.calibration.schema import CalibrationMethod
from afre.schema import Artifact, require

if TYPE_CHECKING:
    from afre.calibration.repository import CalibrationRepository


@dataclass(frozen=True)
class FitBundle:
    observations: CalibrationObservationSet
    mappings: tuple[ProbabilityMapping, ...]
    offsets: tuple[QuantileOffset, ...]
    conformal: ConformalScoreSet | None
    diagnostics: CalibrationDiagnostics
    state: CalibrationState
    run: CalibrationFitRun

    @property
    def values(self) -> tuple[Artifact, ...]:
        return (
            self.observations,
            *self.mappings,
            *self.offsets,
            *((self.conformal,) if self.conformal else ()),
            self.diagnostics,
            self.state.inputs,
            self.state,
            self.run,
        )


def transformations(
    spec: CalibrationSpec, observations: CalibrationObservationSet
) -> tuple[
    tuple[ProbabilityMapping, ...],
    tuple[QuantileOffset, ...],
    ConformalScoreSet | None,
    CalibrationDiagnostics,
]:
    mappings = (
        tuple(mapping_for(spec, observations, event) for event in spec.events.requests)
        if spec.method
        in (CalibrationMethod.BINNED_PROBABILITY, CalibrationMethod.ISOTONIC_PROBABILITY)
        else ()
    )
    offsets = (
        tuple(offset_for(spec, observations, q) for q in spec.quantiles.levels)
        if spec.method is CalibrationMethod.QUANTILE_OFFSET
        else ()
    )
    conformal = (
        scores_for(spec, observations)
        if spec.method
        in (CalibrationMethod.CONFORMAL_ABSOLUTE_RESIDUAL, CalibrationMethod.ROLLING_CONFORMAL)
        else None
    )
    raw = tuple((r.truth, r.quantiles, r.probabilities, r.interval) for r in observations.rows)
    calibrated = tuple(
        (
            r.truth,
            *outputs_for(
                spec, r.quantiles, r.probabilities, r.median, mappings, offsets, conformal
            ),
        )
        for r in observations.rows
    )
    diagnostics = diagnostics_for(raw, calibrated, spec.bins, "fit-same-sample-retrospective")
    return mappings, offsets, conformal, diagnostics


def fit_for(
    repo: "CalibrationRepository",
    spec: CalibrationSpec,
    requests: tuple[CalibrationRequest, ...],
    started_ns: int,
    completed_ns: int,
    available_ns: int,
) -> FitBundle:
    observations = observations_for(repo, spec, requests)
    raw_inputs = spec_context(repo, spec)
    inputs = CalibrationFitInputs(
        spec.fingerprint,
        spec.raw_model_id,
        observations.fingerprint,
        tuple(r.sample_id for r in observations.rows),
        overlap_status(spec.partition.reserved_sample_ids, raw_inputs.train_sample_ids),
        spec.cutoff_ns,
        started_ns,
        completed_ns,
        available_ns,
    )
    require(
        available_ns
        >= max(max(r.truth_available_ns, r.raw_available_ns) for r in observations.rows),
        "calibration availability before evidence",
    )
    mappings, offsets, conformal, diagnostics = transformations(spec, observations)
    state = CalibrationState(
        inputs,
        spec.target.fingerprint,
        tuple(m.fingerprint for m in mappings),
        tuple(o.fingerprint for o in offsets),
        conformal.fingerprint if conformal else None,
        diagnostics.fingerprint,
    )
    run = CalibrationFitRun(inputs, state.fingerprint, diagnostics.fingerprint)
    for value in (
        observations,
        *mappings,
        *offsets,
        *((conformal,) if conformal else ()),
        diagnostics,
        state,
        run,
    ):
        repo.check_calibration_bounds(value)
    return FitBundle(observations, mappings, offsets, conformal, diagnostics, state, run)

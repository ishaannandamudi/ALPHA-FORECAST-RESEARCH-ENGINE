"""Semantic replay checks frozen calibration evidence, mappings, clocks and scores."""

from typing import TYPE_CHECKING

from afre.calibration.application import forecast_for
from afre.calibration.artifacts import (
    CalibratedForecast,
    CalibrationComparison,
    CalibrationDriftDiagnostics,
    CalibrationEvaluation,
    CalibrationFitInputs,
    CalibrationFitRun,
    CalibrationLineageAudit,
    CalibrationObservationSet,
    CalibrationState,
    ConformalScoreSet,
    ProbabilityMapping,
    QuantileOffset,
)
from afre.calibration.conformal import scores_for
from afre.calibration.definitions import CalibrationSpec
from afre.calibration.drift import drift_for
from afre.calibration.evaluation import comparison_for, evaluation_for
from afre.calibration.fitting import FitBundle, fit_for
from afre.calibration.partitions import eligible_forecasts
from afre.calibration.probability import mapping_for
from afre.calibration.quantile import offset_for
from afre.calibration.samples import observations_for
from afre.probabilistic.artifacts import ProbabilisticEvaluation, ProbabilisticForecast
from afre.schema import Artifact, require

if TYPE_CHECKING:
    from afre.calibration.repository import CalibrationRepository


def replay_fit(repo: "CalibrationRepository", inputs: CalibrationFitInputs) -> FitBundle:
    key = inputs.fingerprint
    if key not in repo._calibration_bundles:
        spec = repo.resolve(CalibrationSpec, inputs.spec_id)
        observations = repo.resolve(CalibrationObservationSet, inputs.observations_id)
        repo._validate_links(spec)
        repo._validate_links(observations)
        bundle = fit_for(
            repo,
            spec,
            observations.requests,
            inputs.fit_started_ns,
            inputs.fit_completed_ns,
            inputs.available_ns,
        )
        require(inputs == bundle.state.inputs, "calibration fit-input contamination/clocks")
        repo._calibration_bundles[key] = bundle
    return repo._calibration_bundles[key]


def validate_calibration_links(repo: "CalibrationRepository", value: Artifact) -> None:
    if isinstance(value, CalibrationSpec):
        eligible_forecasts(repo, value, ())
    elif isinstance(value, CalibrationObservationSet):
        spec = repo.resolve(CalibrationSpec, value.spec_id)
        for request in value.requests:
            repo._validate_links(repo.resolve(ProbabilisticForecast, request.raw_forecast_id))
        require(
            value == observations_for(repo, spec, value.requests),
            "calibration observation contamination",
        )
    elif isinstance(value, (ProbabilityMapping, QuantileOffset, ConformalScoreSet)):
        spec = repo.resolve(CalibrationSpec, value.spec_id)
        observations = repo.resolve(CalibrationObservationSet, value.observations_id)
        repo._validate_links(observations)
        if isinstance(value, ProbabilityMapping):
            require(
                value == mapping_for(spec, observations, value.event),
                "calibration map contamination",
            )
        elif isinstance(value, QuantileOffset):
            require(
                value == offset_for(spec, observations, value.level),
                "calibration offset contamination",
            )
        else:
            require(value == scores_for(spec, observations), "conformal score contamination")
    elif isinstance(value, CalibrationFitInputs):
        replay_fit(repo, value)
    elif isinstance(value, CalibrationState):
        require(
            value == replay_fit(repo, value.inputs).state, "calibration state contamination"
        )
        for identity in (
            *value.mapping_ids,
            *value.offset_ids,
            *((value.conformal_id,) if value.conformal_id else ()),
            value.diagnostics_id,
        ):
            require(
                repo.get_any(identity) in replay_fit(repo, value.inputs).values,
                "calibration state transformation evidence mismatch",
            )
    elif isinstance(value, CalibrationFitRun):
        require(
            value == replay_fit(repo, value.inputs).run
            and repo.resolve(CalibrationState, value.state_id)
            == replay_fit(repo, value.inputs).state,
            "calibration run/state mismatch",
        )
    elif isinstance(value, CalibratedForecast):
        state = repo.resolve(CalibrationState, value.state_id)
        raw = repo.resolve(ProbabilisticForecast, value.raw_forecast_id)
        require(
            value == forecast_for(repo, state, raw, value.computed_ns),
            "calibrated forecast mismatch",
        )
    elif isinstance(value, CalibrationEvaluation):
        raw_evaluation = repo.resolve(ProbabilisticEvaluation, value.raw_evaluation_id)
        repo._validate_links(raw_evaluation)
        require(
            value == evaluation_for(repo, value.forecast_ids, raw_evaluation),
            "calibration evaluation contamination",
        )
    elif isinstance(value, CalibrationComparison):
        require(
            value
            == comparison_for(repo, value.raw_evaluation_id, value.calibrated_evaluation_id),
            "calibration comparison contamination",
        )
    elif isinstance(value, CalibrationDriftDiagnostics):
        require(
            value == drift_for(repo, value.spec, value.evaluation_ids),
            "calibration drift contamination",
        )
    elif isinstance(value, CalibrationLineageAudit):
        from afre.calibration.lineage import lineage_audit

        require(value == lineage_audit(repo, value.root_id), "calibration audit mismatch")

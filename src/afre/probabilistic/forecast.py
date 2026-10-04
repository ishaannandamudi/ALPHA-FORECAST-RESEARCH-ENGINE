"""Completed uncertainty and feature-only point prediction; no target imports."""

from typing import TYPE_CHECKING

from afre.probabilistic.artifacts import (
    DistributionParameters,
    ProbabilisticFitRun,
    ProbabilisticForecast,
    ProbabilisticModelArtifact,
    QuantileValue,
    ThresholdProbability,
    TrainingDistribution,
)
from afre.probabilistic.definitions import ProbabilisticModelSpec
from afre.probabilistic.distributions import conditional_variance, expected_value, quantile
from afre.probabilistic.schema import DistributionFamily, DistributionState, ObservationPolicy
from afre.probabilistic.thresholds import threshold_probability
from afre.schema import require
from afre.statistical_models.artifacts import (
    FittedModelArtifact,
    PointForecast,
    PredictionInput,
)
from afre.statistical_models.linear_algebra import finite
from afre.statistical_models.prediction import forecast_for as point_forecast_for
from afre.statistical_models.schema import PredictionScope

if TYPE_CHECKING:
    from afre.probabilistic.repository import ProbabilisticRepository


def parameters_for(
    spec: ProbabilisticModelSpec,
    artifact: ProbabilisticModelArtifact,
    state: TrainingDistribution,
    point_value: float,
) -> DistributionParameters:
    location = (
        point_value
        if spec.observation_policy is ObservationPolicy.POINT_MODEL_RESIDUALS
        else 0.0
    )
    if spec.family is DistributionFamily.GAUSSIAN_LOCATION_SCALE:
        return DistributionParameters(
            spec.family, finite(location + artifact.location_offset), artifact.scale
        )
    if spec.family is DistributionFamily.EMPIRICAL_RESIDUAL:
        return DistributionParameters(
            spec.family,
            location,
            artifact.scale,
            state.values,
            state=DistributionState.DEGENERATE
            if state.values[0] == state.values[-1]
            else DistributionState.REGULAR,
        )
    empirical = DistributionParameters(
        DistributionFamily.EMPIRICAL_RESIDUAL,
        location,
        artifact.scale,
        state.values,
        state=DistributionState.DEGENERATE
        if state.values[0] == state.values[-1]
        else DistributionState.REGULAR,
    )
    values = tuple(QuantileValue(q, quantile(empirical, q)) for q in spec.quantiles.levels)
    return DistributionParameters(
        spec.family,
        location,
        artifact.scale,
        quantile_values=values,
        state=DistributionState.DEGENERATE
        if values[0].value == values[-1].value
        else DistributionState.REGULAR,
    )


def forecast_for(
    repo: "ProbabilisticRepository",
    artifact: ProbabilisticModelArtifact,
    request: PredictionInput,
    computed_ns: int,
) -> tuple[PointForecast, ProbabilisticForecast]:
    spec = repo.resolve(ProbabilisticModelSpec, artifact.spec_id)
    state = repo.resolve(TrainingDistribution, artifact.distribution_id)
    rows = repo._connection.execute(
        "SELECT fingerprint FROM p_fits WHERE artifact_id=?", (artifact.fingerprint,)
    ).fetchall()
    require(len(rows) == 1, "probability forecast requires one completed fit run")
    run = repo.resolve(ProbabilisticFitRun, rows[0][0])
    require(
        run.artifact_id == artifact.fingerprint
        and run.inputs.fingerprint == artifact.fit_inputs_id
        and run.distribution_id == state.fingerprint
        and run.diagnostics_id == artifact.diagnostics_id
        and state.spec_id == spec.fingerprint
        and state.available_ns == artifact.available_ns,
        "probability completed fit lineage mismatch",
    )
    historical = request.scope is not PredictionScope.IN_SAMPLE
    require(
        not historical or artifact.available_ns <= request.origin.availability_cutoff_ns,
        "probabilistic artifact unavailable at origin",
    )
    require(
        historical or computed_ns >= artifact.available_ns,
        "retrospective probability computation before fit",
    )
    model = repo.resolve(FittedModelArtifact, spec.point_model_id)
    require(
        artifact.available_ns >= model.available_ns, "uncertainty available before point model"
    )
    point = point_forecast_for(repo, model, request, computed_ns)
    distribution = parameters_for(spec, artifact, state, point.value)
    quantiles = tuple(
        QuantileValue(q, quantile(distribution, q)) for q in spec.quantiles.levels
    )
    probabilities = tuple(
        ThresholdProbability(r, threshold_probability(distribution, r))
        for r in spec.thresholds.requests
    )
    forecast = ProbabilisticForecast(
        artifact.fingerprint,
        point.fingerprint,
        spec.target.fingerprint,
        request,
        distribution,
        quantiles,
        probabilities,
        expected_value(distribution),
        quantile(distribution, 0.5),
        conditional_variance(distribution),
        artifact.available_ns,
        computed_ns,
        computed_ns,
        historical,
    )
    return point, forecast

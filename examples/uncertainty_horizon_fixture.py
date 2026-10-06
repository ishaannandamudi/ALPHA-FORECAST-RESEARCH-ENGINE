"""Actual independent 1h/1d forecast laws; no proportional time scaling assumption."""

from afre.probabilistic import (
    DistributionFamily,
    ObservationPolicy,
    ProbabilisticEngine,
    ProbabilisticModelSpec,
    QuantileDefinition,
    ResidualCentering,
    ScalePolicy,
    ScaleSpec,
    ThresholdDefinition,
)
from afre.probabilistic.artifacts import ProbabilisticForecast
from afre.regime_conditioned import RegimeConditioningSpec, RegimeEngine
from afre.uncertainty import (
    ForecastUncertaintyDecomposition,
    UncertaintyEngine,
    UncertaintyRepository,
    UncertaintyRequest,
    UncertaintySpec,
    UncertaintyType,
)
from examples.regime_horizon_fixture import real_horizons


def horizon_uncertainties(
    repo: UncertaintyRepository,
) -> tuple[tuple[ForecastUncertaintyDecomposition, ...], ...]:
    outputs = []
    for index, (model, forecasts) in enumerate(real_horizons(repo)):
        conditioning = repo.get(RegimeConditioningSpec, model.spec_id)
        from afre.statistical_models.artifacts import FittedModelArtifact
        from afre.statistical_models.definitions import BaselineModelSpec

        baseline = repo.get(FittedModelArtifact, conditioning.base_model_id)
        original = repo.get(BaselineModelSpec, baseline.spec_id)
        policy = ProbabilisticModelSpec(
            baseline.fingerprint,
            DistributionFamily.GAUSSIAN_LOCATION_SCALE,
            ObservationPolicy.POINT_MODEL_RESIDUALS,
            ResidualCentering.RAW,
            ScaleSpec(ScalePolicy.FIXED_SCALE, 0.01 if index == 0 else 0.025),
            QuantileDefinition((0.1, 0.5, 0.9)),
            ThresholdDefinition(()),
            original.fold_id,
            original.target,
            model.cutoff_ns,
            0,
        )
        probability = ProbabilisticEngine(repo)
        run = probability.fit_model(
            policy, model.available_ns, model.available_ns, model.available_ns
        )
        current = []
        for forecast in forecasts:
            from afre.statistical_models.artifacts import PointForecast

            point = repo.get(PointForecast, forecast.base_forecast_id)
            raw: ProbabilisticForecast = probability.predict(
                run.artifact_id, point.input, forecast.computed_ns
            )
            conditioned = RegimeEngine(repo).forecast(
                model.fingerprint,
                forecast.observation_id,
                point.fingerprint,
                forecast.computed_ns,
                raw.fingerprint,
            )
            spec = UncertaintySpec(
                original.target,
                conditioned.fingerprint,
                (
                    UncertaintyRequest(UncertaintyType.TOTAL_PREDICTIVE),
                    UncertaintyRequest(UncertaintyType.HORIZON),
                ),
                interval_levels=(0.1, 0.9),
            )
            current.append(UncertaintyEngine(repo).decompose(spec, forecast.computed_ns))
        outputs.append(tuple(current))
    assert outputs[0][0].horizon_id != outputs[1][0].horizon_id
    return tuple(outputs)

"""Native AFRE score definitions, explicit weighted support, no significance inference."""

from math import fsum, sqrt

from afre.invariance.definitions import StabilityAnalysisSpec
from afre.invariance.schema import StabilityMetricName
from afre.mixture.artifacts import MixtureDistribution
from afre.mixture.probabilistic import mixture_cdf, mixture_crps, mixture_nll
from afre.probabilistic.artifacts import DistributionParameters
from afre.probabilistic.distributions import cdf, quantile
from afre.probabilistic.schema import DistributionFamily
from afre.probabilistic.scoring import (
    empirical_crps,
    gaussian_crps,
    negative_log_likelihood,
    pinball_loss,
)
from afre.statistical_models.linear_algebra import finite
from afre.statistical_models.metrics import point_metrics
from afre.statistical_models.schema import MetricName
from afre.uncertainty.sources import ForecastSource

POINT_NAMES = {
    StabilityMetricName.MAE: MetricName.MAE,
    StabilityMetricName.MSE: MetricName.MSE,
    StabilityMetricName.RMSE: MetricName.RMSE,
    StabilityMetricName.R_SQUARED: MetricName.R_SQUARED,
    StabilityMetricName.PEARSON: MetricName.PEARSON_CORRELATION,
    StabilityMetricName.SPEARMAN: MetricName.SPEARMAN_CORRELATION,
    StabilityMetricName.SIGN_ACCURACY: MetricName.DIRECTIONAL_ACCURACY,
}


def weighted_mean(values: tuple[float, ...], weights: tuple[float, ...]) -> float:
    return finite(
        fsum(finite(v * w) for v, w in zip(values, weights, strict=True)) / fsum(weights)
    )


def point_score(
    name: StabilityMetricName,
    predictions: tuple[float, ...],
    truths: tuple[float, ...],
    weights: tuple[float, ...],
) -> tuple[float | None, str]:
    if len(set(weights)) <= 1:
        m = next(m for m in point_metrics(predictions, truths) if m.name is POINT_NAMES[name])
        return m.value, m.state.value
    if name in (StabilityMetricName.PEARSON, StabilityMetricName.SPEARMAN):
        return None, "weighted-correlation-not-supported"
    errors = tuple(finite(p - y) for p, y in zip(predictions, truths, strict=True))
    if name is StabilityMetricName.SIGN_ACCURACY:
        return weighted_mean(
            tuple(
                float((p > 0) - (p < 0) == (y > 0) - (y < 0))
                for p, y in zip(predictions, truths, strict=True)
            ),
            weights,
        ), "explicit-weighted-sign-v1"
    if name is StabilityMetricName.MAE:
        return weighted_mean(tuple(abs(e) for e in errors), weights), "explicit-weighted-MAE-v1"
    mse = weighted_mean(tuple(finite(e * e) for e in errors), weights)
    if name is StabilityMetricName.MSE:
        return mse, "explicit-weighted-MSE-v1"
    if name is StabilityMetricName.RMSE:
        return finite(sqrt(mse)), "explicit-weighted-RMSE-v1"
    center = weighted_mean(truths, weights)
    variance = weighted_mean(tuple(finite((y - center) ** 2) for y in truths), weights)
    return (
        (finite(1 - mse / variance), "explicit-weighted-R2-v1")
        if variance > 0
        else (None, "constant-target")
    )


def event_probability(source: ForecastSource, threshold: float) -> float | None:
    law = source.law
    if isinstance(law, MixtureDistribution):
        return 1 - mixture_cdf(law, threshold)
    if (
        isinstance(law, DistributionParameters)
        and law.family is not DistributionFamily.QUANTILE_SET
    ):
        return 1 - cdf(law, threshold)
    # Marginal calibrated probabilities are used only for their exact native threshold.
    from afre.calibration.artifacts import CalibratedForecast
    from afre.probabilistic.schema import ThresholdComparison

    if isinstance(source.artifact, CalibratedForecast):
        for p in source.artifact.probabilities:
            if p.request.comparison is ThresholdComparison.GT and p.request.value == threshold:
                return p.probability
    return None


def probabilistic_score(
    name: StabilityMetricName,
    source: ForecastSource,
    truth: float,
    spec: StabilityAnalysisSpec,
    work_cells: int,
) -> float | None:
    law = source.law
    if name is StabilityMetricName.BRIER:
        p = event_probability(source, spec.threshold)
        return None if p is None else finite((p - float(truth > spec.threshold)) ** 2)
    if name is StabilityMetricName.CRPS:
        if isinstance(law, MixtureDistribution):
            return mixture_crps(law, truth, work_cells)
        if isinstance(law, DistributionParameters):
            if law.family is DistributionFamily.GAUSSIAN_LOCATION_SCALE:
                return gaussian_crps(law, truth)
            if law.family is DistributionFamily.EMPIRICAL_RESIDUAL:
                return empirical_crps(law, truth)
        return None
    if name is StabilityMetricName.NLL:
        if isinstance(law, MixtureDistribution):
            return mixture_nll(law, truth)
        return (
            negative_log_likelihood(law, truth)
            if isinstance(law, DistributionParameters)
            and law.family is DistributionFamily.GAUSSIAN_LOCATION_SCALE
            else None
        )
    if name is StabilityMetricName.PINBALL:
        from afre.calibration.artifacts import CalibratedForecast

        if isinstance(source.artifact, CalibratedForecast):
            q = next(
                (q for q in source.artifact.quantiles if q.level == spec.pinball_level), None
            )
            return pinball_loss(spec.pinball_level, q.value, truth) if q else None
        return (
            pinball_loss(spec.pinball_level, quantile(law, spec.pinball_level), truth)
            if isinstance(law, DistributionParameters)
            else None
        )
    interval = source.interval
    if interval is not None:
        if (interval.lower_level, interval.upper_level) != spec.interval_levels:
            return None
        low, high = interval.lower, interval.upper
    elif isinstance(law, DistributionParameters):
        low, high = (
            quantile(law, spec.interval_levels[0]),
            quantile(law, spec.interval_levels[1]),
        )
    else:
        return None
    return (
        finite(high - low) if name is StabilityMetricName.WIDTH else float(low <= truth <= high)
    )


def reliability_for(
    sources: tuple[ForecastSource, ...],
    truths: tuple[float, ...],
    weights: tuple[float, ...],
    spec: StabilityAnalysisSpec,
) -> tuple[
    tuple[tuple[float, float, int, float | None, float | None], ...], float | None, float | None
]:
    probabilities = tuple(event_probability(s, spec.threshold) for s in sources)
    if any(p is None for p in probabilities):
        return (), None, None
    records, errors, masses = [], [], []
    edges = spec.reliability_edges
    for j in range(len(edges) - 1):
        low, high = edges[j], edges[j + 1]
        selected = tuple(
            i
            for i, p in enumerate(probabilities)
            if p is not None and low <= p and (p < high or j == len(edges) - 2 and p == high)
        )
        if selected:
            ws = tuple(weights[i] for i in selected)
            ps = tuple(p for i in selected if (p := probabilities[i]) is not None)
            mean = weighted_mean(ps, ws)
            frequency = weighted_mean(
                tuple(float(truths[i] > spec.threshold) for i in selected), ws
            )
            errors.append(abs(mean - frequency))
            masses.append(fsum(ws))
        else:
            mean, frequency = None, None
        records.append((low, high, len(selected), mean, frequency))
    return tuple(records), weighted_mean(tuple(errors), tuple(masses)), max(errors)

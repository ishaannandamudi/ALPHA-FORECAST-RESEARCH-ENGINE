"""Source-law/calibrated intervals only; no calibration fitting or mixture inversion."""

from afre.probabilistic.artifacts import DistributionParameters
from afre.probabilistic.distributions import quantile
from afre.probabilistic.schema import DistributionFamily
from afre.uncertainty.artifacts import UncertaintyInterval
from afre.uncertainty.definitions import UncertaintySpec
from afre.uncertainty.schema import IdentifiabilityStatus
from afre.uncertainty.sources import ForecastSource


def interval_for(
    spec: UncertaintySpec, source: ForecastSource, available_ns: int
) -> UncertaintyInterval:
    low = high = None
    status, semantics = IdentifiabilityStatus.UNAVAILABLE, "source-interval-unavailable"
    if source.interval is not None:
        interval = source.interval
        if spec.interval_levels == (interval.lower_level, interval.upper_level):
            low, high = interval.lower, interval.upper
            status, semantics = (
                IdentifiabilityStatus.IDENTIFIED,
                "AFRE-7-pinned-calibrated-interval-v1",
            )
        else:
            status, semantics = IdentifiabilityStatus.INCOMPATIBLE, "calibrated-level-mismatch"
    elif isinstance(source.law, DistributionParameters):
        law = source.law
        if law.family is not DistributionFamily.QUANTILE_SET or set(spec.interval_levels) <= {
            q.level for q in law.quantile_values
        }:
            low, high = (quantile(law, q) for q in spec.interval_levels)
            status = IdentifiabilityStatus.IDENTIFIED
            semantics = (
                "AFRE-6-Gaussian-quantile-approximation-v1"
                if law.family is DistributionFamily.GAUSSIAN_LOCATION_SCALE
                else "AFRE-6-Type7-empirical-quantiles-v1"
                if law.family is DistributionFamily.EMPIRICAL_RESIDUAL
                else "AFRE-6-explicit-sparse-quantiles-v1"
            )
        else:
            status, semantics = IdentifiabilityStatus.INCOMPATIBLE, "sparse-levels-not-stored"
    elif source.law is not None:
        semantics = "AFRE-12-mixture-quantiles-unsupported"
    return UncertaintyInterval(
        spec.fingerprint,
        spec.forecast_id,
        spec.interval_levels,
        low,
        high,
        high - low if low is not None and high is not None else None,
        status,
        semantics,
        available_ns,
    )

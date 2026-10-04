"""Explicit distribution queries; sparse quantiles imply no hidden CDF or tails."""

import math
from bisect import bisect_left, bisect_right

from afre.probabilistic.artifacts import DistributionParameters, ProbabilisticForecast
from afre.probabilistic.quantiles import interpolate_sorted, normal_quantile
from afre.probabilistic.scale import moments
from afre.probabilistic.schema import DistributionFamily
from afre.schema import require
from afre.statistical_models.linear_algebra import finite


def parameters(value: DistributionParameters | ProbabilisticForecast) -> DistributionParameters:
    return value.distribution if isinstance(value, ProbabilisticForecast) else value


def normal_cdf(z: float) -> float:
    require(not math.isnan(z), "NaN normal query")
    return 0.5 * math.erfc(-z / math.sqrt(2))


def quantile(distribution: DistributionParameters | ProbabilisticForecast, q: float) -> float:
    distribution = parameters(distribution)
    finite(q)
    require(0 < q < 1, "quantile query domain")
    if distribution.family is DistributionFamily.GAUSSIAN_LOCATION_SCALE:
        return finite(distribution.location + finite(distribution.scale * normal_quantile(q)))
    if distribution.family is DistributionFamily.EMPIRICAL_RESIDUAL:
        return finite(distribution.location + interpolate_sorted(distribution.samples, q))
    values = {value.level: value.value for value in distribution.quantile_values}
    require(q in values, "quantile-only query requires an explicitly stored level")
    return values[q]


def cdf(
    distribution: DistributionParameters | ProbabilisticForecast, x: float, strict: bool = False
) -> float:
    distribution = parameters(distribution)
    finite(x)
    require(
        distribution.family is not DistributionFamily.QUANTILE_SET,
        "quantile-only CDF unsupported",
    )
    if distribution.family is DistributionFamily.GAUSSIAN_LOCATION_SCALE:
        return normal_cdf((x - distribution.location) / distribution.scale)
    count = (
        bisect_left(
            distribution.samples, x, key=lambda atom: finite(distribution.location + atom)
        )
        if strict
        else bisect_right(
            distribution.samples, x, key=lambda atom: finite(distribution.location + atom)
        )
    )
    return count / len(distribution.samples)


def survival(
    distribution: DistributionParameters | ProbabilisticForecast,
    x: float,
    inclusive: bool = False,
) -> float:
    distribution = parameters(distribution)
    finite(x)
    require(
        distribution.family is not DistributionFamily.QUANTILE_SET,
        "quantile-only survival unsupported",
    )
    if distribution.family is DistributionFamily.GAUSSIAN_LOCATION_SCALE:
        return 0.5 * math.erfc((x - distribution.location) / distribution.scale / math.sqrt(2))
    count = (
        bisect_left(
            distribution.samples, x, key=lambda atom: finite(distribution.location + atom)
        )
        if inclusive
        else bisect_right(
            distribution.samples, x, key=lambda atom: finite(distribution.location + atom)
        )
    )
    return (len(distribution.samples) - count) / len(distribution.samples)


def density(distribution: DistributionParameters | ProbabilisticForecast, x: float) -> float:
    distribution = parameters(distribution)
    finite(x)
    require(
        distribution.family is DistributionFamily.GAUSSIAN_LOCATION_SCALE,
        "density requires Gaussian",
    )
    z = (x - distribution.location) / distribution.scale
    return finite(math.exp(-0.5 * z * z) / math.sqrt(2 * math.pi) / distribution.scale)


def expected_value(
    distribution: DistributionParameters | ProbabilisticForecast,
) -> float | None:
    distribution = parameters(distribution)
    if distribution.family is DistributionFamily.QUANTILE_SET:
        return None
    if distribution.family is DistributionFamily.GAUSSIAN_LOCATION_SCALE:
        return distribution.location
    return finite(distribution.location + moments(distribution.samples)[0])


def conditional_variance(
    distribution: DistributionParameters | ProbabilisticForecast,
) -> float | None:
    distribution = parameters(distribution)
    if distribution.family is DistributionFamily.QUANTILE_SET:
        return None
    std = (
        distribution.scale
        if distribution.family is DistributionFamily.GAUSSIAN_LOCATION_SCALE
        else moments(distribution.samples)[2]
    )
    return finite(std * std)

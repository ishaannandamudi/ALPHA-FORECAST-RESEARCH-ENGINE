"""Deterministic Type-7 empirical and bounded stdlib normal quantiles."""

from statistics import NormalDist

from afre.schema import require
from afre.statistical_models.linear_algebra import finite


def empirical_quantile(values: tuple[float, ...], q: float) -> float:
    finite(q)
    require(bool(values) and 0 < q < 1, "empirical quantile domain")
    require(
        all(values[i] <= values[i + 1] for i in range(len(values) - 1)),
        "empirical samples must be sorted",
    )
    return interpolate_sorted(values, q)


def interpolate_sorted(values: tuple[float, ...], q: float) -> float:
    """Constant-time query after the immutable distribution verified sorting."""
    finite(q)
    require(bool(values) and 0 < q < 1, "empirical quantile domain")
    position = (len(values) - 1) * q
    index = int(position)
    upper = min(index + 1, len(values) - 1)
    return finite(values[index] + finite(values[upper] - values[index]) * (position - index))


def normal_quantile(q: float) -> float:
    finite(q)
    require(1e-12 <= q <= 1 - 1e-12, "normal quantile numerical domain")
    return finite(NormalDist().inv_cdf(q))

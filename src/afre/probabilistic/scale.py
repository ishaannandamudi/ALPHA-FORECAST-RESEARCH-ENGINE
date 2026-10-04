"""TRAIN population spread and declared MAD/fixed continuous scale."""

import math
from statistics import median

from afre.probabilistic.definitions import ScaleSpec
from afre.probabilistic.schema import ScalePolicy
from afre.schema import require
from afre.statistical_models.linear_algebra import dot, finite, total


def moments(values: tuple[float, ...]) -> tuple[float, float, float, float]:
    require(bool(values), "empty probability observations")
    mean = finite(values[0] + total([finite(v - values[0]) for v in values]) / len(values))
    med = finite(float(median(values)))
    centered = tuple(finite(v - mean) for v in values)
    std = (
        0.0
        if min(values) == max(values)
        else finite(math.sqrt(dot(centered, centered) / len(values)))
    )
    mad = finite(float(median(tuple(abs(finite(v - med)) for v in values))))
    return mean, med, std, mad


def estimate_scale(values: tuple[float, ...], spec: ScaleSpec, continuous: bool) -> float:
    _, _, std, mad = moments(values)
    result = (
        spec.fixed_scale
        if spec.policy is ScalePolicy.FIXED_SCALE
        else finite(mad * spec.mad_consistency_factor)
        if spec.policy is ScalePolicy.TRAIN_RESIDUAL_MAD_SCALED
        else std
    )
    assert result is not None
    require(not continuous or result > 0, "degenerate zero continuous scale; no implicit floor")
    return finite(result)

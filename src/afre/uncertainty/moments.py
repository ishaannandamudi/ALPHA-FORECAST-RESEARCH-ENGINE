"""Exact finite-law moments and explicitly labelled supplied-state spreads."""

import math

from afre.mixture.artifacts import MixtureDistribution
from afre.mixture.probabilistic import mixture_expectation, mixture_variance
from afre.probabilistic.artifacts import DistributionParameters
from afre.probabilistic.distributions import conditional_variance, expected_value
from afre.schema import require
from afre.statistical_models.linear_algebra import finite, total
from afre.uncertainty.sources import Law


def variance(law: Law | None) -> float | None:
    return (
        mixture_variance(law)
        if isinstance(law, MixtureDistribution)
        else conditional_variance(law)
        if isinstance(law, DistributionParameters)
        else None
    )


def weighted_spread(
    weights: tuple[float, ...], values: tuple[float, ...], tolerance: float = 1e-10
) -> tuple[float, float]:
    require(
        bool(weights)
        and len(weights) == len(values) <= 32
        and all(w >= 0 for w in weights)
        and abs(total(list(weights)) - 1) <= tolerance,
        "explicit normalized finite weights required",
    )
    mean = total([finite(w * v) for w, v in zip(weights, values, strict=True)])
    spread = total(
        [
            finite(w * finite(finite(v - mean) * finite(v - mean)))
            for w, v in zip(weights, values, strict=True)
        ]
    )
    return mean, spread


def mixture_terms(law: MixtureDistribution) -> tuple[float, float, float]:
    require(len(law.components) <= 32, "mixture uncertainty expert bound")
    mean = mixture_expectation(law)
    within, between = [], []
    for component in law.components:
        mu, var = (
            expected_value(component.distribution),
            conditional_variance(component.distribution),
        )
        assert mu is not None and var is not None
        within.append(finite(component.weight * var))
        between.append(finite(component.weight * finite(finite(mu - mean) * finite(mu - mean))))
    return mixture_variance(law), total(within), total(between)


def entropy(weights: tuple[float, ...]) -> float:
    weighted_spread(weights, (0.0,) * len(weights))
    return total([finite(-w * math.log(w)) for w in weights if w > 0])

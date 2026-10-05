"""Finite component laws, exact mixture moments/events and bounded proper scores."""

from math import exp, fsum, hypot, log, pi, sqrt

from afre.mixture.artifacts import MixtureDistribution
from afre.probabilistic.artifacts import DistributionParameters, ProbabilityScore
from afre.probabilistic.definitions import ThresholdRequest
from afre.probabilistic.distributions import (
    cdf as component_cdf,
)
from afre.probabilistic.distributions import (
    conditional_variance,
    expected_value,
    normal_cdf,
)
from afre.probabilistic.schema import DistributionFamily, ScoreName, ScoreState
from afre.probabilistic.thresholds import threshold_probability as component_probability
from afre.schema import require
from afre.statistical_models.linear_algebra import finite


def bounded_probability(value: float, tolerance: float) -> float:
    require(-tolerance <= finite(value) <= 1 + tolerance, "mixture probability outside bounds")
    return min(1.0, max(0.0, value))


def mixture_cdf(distribution: MixtureDistribution, x: float, strict: bool = False) -> float:
    return bounded_probability(
        fsum(
            c.weight * component_cdf(c.distribution, x, strict) for c in distribution.components
        ),
        distribution.tolerance,
    )


def mixture_threshold(distribution: MixtureDistribution, request: ThresholdRequest) -> float:
    return bounded_probability(
        fsum(
            c.weight * component_probability(c.distribution, request)
            for c in distribution.components
        ),
        distribution.tolerance,
    )


def mixture_expectation(distribution: MixtureDistribution) -> float:
    means = tuple(expected_value(c.distribution) for c in distribution.components)
    require(all(m is not None for m in means), "mixture mean unsupported")
    return finite(
        fsum(
            c.weight * m
            for c, m in zip(distribution.components, means, strict=True)
            if m is not None
        )
    )


def mixture_variance(distribution: MixtureDistribution) -> float:
    mean = mixture_expectation(distribution)
    values = []
    for c in distribution.components:
        mu, var = expected_value(c.distribution), conditional_variance(c.distribution)
        require(mu is not None and var is not None, "mixture variance unsupported")
        assert mu is not None and var is not None
        values.append(
            finite(c.weight * finite(var + finite(finite(mu - mean) * finite(mu - mean))))
        )
    return finite(fsum(values))


def mixture_quantile(distribution: MixtureDistribution, q: float) -> float:
    require(False, "mixture quantiles unsupported; never average component quantiles")
    raise AssertionError("unreachable")


def normal_absolute(mean: float, scale: float) -> float:
    if scale == 0:
        return abs(mean)
    z = mean / scale
    return finite(2 * scale * exp(-0.5 * z * z) / sqrt(2 * pi) + mean * (2 * normal_cdf(z) - 1))


def absolute_between(left: DistributionParameters, right: DistributionParameters) -> float:
    a, b = left.family, right.family
    gaussian = DistributionFamily.GAUSSIAN_LOCATION_SCALE
    if a is gaussian and b is gaussian:
        return normal_absolute(left.location - right.location, hypot(left.scale, right.scale))
    if a is gaussian:
        return fsum(
            normal_absolute(left.location - right.location - v, left.scale)
            for v in right.samples
        ) / len(right.samples)
    if b is gaussian:
        return absolute_between(right, left)
    return fsum(
        abs(left.location + x - right.location - y) for x in left.samples for y in right.samples
    ) / (len(left.samples) * len(right.samples))


def mixture_crps(
    distribution: MixtureDistribution, truth: float, work_cells: int = 2_000_000
) -> float:
    finite(truth)
    components = distribution.components
    sizes = tuple(len(c.distribution.samples) or 1 for c in components)
    require(sum(sizes) ** 2 <= work_cells, "finite mixture score work bound")
    first = fsum(
        c.weight
        * (
            normal_absolute(c.distribution.location - truth, c.distribution.scale)
            if c.distribution.family is DistributionFamily.GAUSSIAN_LOCATION_SCALE
            else fsum(abs(c.distribution.location + a - truth) for a in c.distribution.samples)
            / len(c.distribution.samples)
        )
        for c in components
    )
    second = fsum(
        a.weight * b.weight * absolute_between(a.distribution, b.distribution)
        for a in components
        for b in components
    )
    value = finite(first - 0.5 * second)
    require(value >= -1e-12 * max(1.0, first), "negative finite mixture CRPS")
    return max(0.0, value)


def mixture_nll(distribution: MixtureDistribution, truth: float) -> float | None:
    finite(truth)
    if any(
        c.distribution.family is not DistributionFamily.GAUSSIAN_LOCATION_SCALE
        for c in distribution.components
    ):
        return None
    logs_list = []
    for c in distribution.components:
        z = finite(finite(truth - c.distribution.location) / c.distribution.scale)
        logs_list.append(
            finite(
                log(c.weight)
                - log(c.distribution.scale)
                - 0.5 * log(2 * pi)
                - 0.5 * finite(z * z)
            )
        )
    logs = tuple(logs_list)
    high = max(logs)
    return finite(-(high + log(fsum(exp(v - high) for v in logs))))


def mixture_scores(
    distribution: MixtureDistribution,
    truth: float,
    thresholds: tuple[ThresholdRequest, ...] = (),
    work_cells: int = 2_000_000,
) -> tuple[ProbabilityScore, ...]:
    nll = mixture_nll(distribution, truth)
    values = [
        ProbabilityScore(
            ScoreName.CRPS,
            mixture_crps(distribution, truth, work_cells),
            ScoreState.AVAILABLE,
            1,
        ),
        ProbabilityScore(
            ScoreName.NLL,
            nll,
            ScoreState.AVAILABLE if nll is not None else ScoreState.UNSUPPORTED,
            1,
        ),
        ProbabilityScore(
            ScoreName.PIT_MEAN, mixture_cdf(distribution, truth), ScoreState.AVAILABLE, 1
        ),
    ]
    for request in thresholds:
        from afre.probabilistic.thresholds import event_outcome

        p = mixture_threshold(distribution, request)
        values.append(
            ProbabilityScore(
                ScoreName.BRIER,
                (p - event_outcome(truth, request)) ** 2,
                ScoreState.AVAILABLE,
                1,
                threshold=request,
            )
        )
    return tuple(sorted(values, key=lambda s: s.key))

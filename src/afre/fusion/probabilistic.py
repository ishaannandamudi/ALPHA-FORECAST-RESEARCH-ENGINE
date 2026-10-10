"""Exact finite laws, preserving nested Gaussian and empirical component mixtures."""

from dataclasses import dataclass
from math import exp, fsum, log, pi

from afre.mixture.artifacts import MixtureDistribution
from afre.mixture.probabilistic import absolute_between, bounded_probability, normal_absolute
from afre.probabilistic.artifacts import DistributionParameters
from afre.probabilistic.distributions import cdf, conditional_variance, expected_value, survival
from afre.probabilistic.schema import DistributionFamily
from afre.schema import Artifact, contract, require
from afre.statistical_models.linear_algebra import finite

Law = DistributionParameters | MixtureDistribution


def law_mean(law: Law | None) -> float | None:
    if isinstance(law, MixtureDistribution):
        from afre.mixture.probabilistic import mixture_expectation

        return mixture_expectation(law)
    return expected_value(law) if law is not None else None


@contract("fus_component")
@dataclass(frozen=True, slots=True)
class FusionLawComponent(Artifact):
    source_id: str
    output_id: str
    component_id: str
    weight: float
    distribution: DistributionParameters

    def _validate(self) -> None:
        require(
            self.weight > 0 and self.distribution.family is not DistributionFamily.QUANTILE_SET,
            "INCOMPATIBLE: fusion requires positive-weight exact complete laws",
        )


@contract("fus_law")
@dataclass(frozen=True, slots=True)
class FusionDistribution(Artifact):
    components: tuple[FusionLawComponent, ...]
    tolerance: float = 1e-12

    def _normalize(self) -> None:
        self.ordered("components", "component_id")

    def _validate(self) -> None:
        require(
            0 < len(self.components) <= 32
            and 0 < self.tolerance <= 1e-12
            and abs(fsum(c.weight for c in self.components) - 1.0) <= self.tolerance,
            "finite fusion simplex/component bound",
        )


def blend(parts: tuple[tuple[str, str, float, Law], ...], maximum: int) -> FusionDistribution:
    result: list[FusionLawComponent] = []
    for source, output, weight, law in parts:
        if weight == 0:
            continue
        if isinstance(law, MixtureDistribution):
            result.extend(
                FusionLawComponent(
                    source,
                    output,
                    source + ":" + c.expert_id,
                    finite(weight * c.weight),
                    c.distribution,
                )
                for c in law.components
            )
        else:
            result.append(FusionLawComponent(source, output, source, weight, law))
    require(len(result) <= maximum, "fusion probability component bound")
    return FusionDistribution(tuple(result))


def mean(law: FusionDistribution) -> float:
    values = tuple(expected_value(c.distribution) for c in law.components)
    assert all(v is not None for v in values)
    return finite(
        fsum(c.weight * v for c, v in zip(law.components, values, strict=True) if v is not None)
    )


def variance_parts(law: FusionDistribution) -> tuple[float, float]:
    mu = mean(law)
    within, between = [], []
    for c in law.components:
        m, v = expected_value(c.distribution), conditional_variance(c.distribution)
        assert m is not None and v is not None
        within.append(finite(c.weight * v))
        between.append(finite(c.weight * finite((m - mu) * (m - mu))))
    return finite(fsum(within)), finite(fsum(between))


def mixture_cdf(law: FusionDistribution, x: float) -> float:
    return bounded_probability(
        fsum(c.weight * cdf(c.distribution, x) for c in law.components), law.tolerance
    )


def threshold_probability(law: FusionDistribution, x: float) -> float:
    return bounded_probability(
        fsum(c.weight * survival(c.distribution, x) for c in law.components), law.tolerance
    )


def crps(law: FusionDistribution, truth: float, work_cells: int = 2000000) -> float:
    sizes = tuple(len(c.distribution.samples) or 1 for c in law.components)
    require(sum(sizes) ** 2 <= work_cells, "fusion CRPS work bound")
    first = fsum(
        c.weight
        * (
            normal_absolute(c.distribution.location - truth, c.distribution.scale)
            if c.distribution.family is DistributionFamily.GAUSSIAN_LOCATION_SCALE
            else fsum(abs(c.distribution.location + a - truth) for a in c.distribution.samples)
            / len(c.distribution.samples)
        )
        for c in law.components
    )
    second = fsum(
        a.weight * b.weight * absolute_between(a.distribution, b.distribution)
        for a in law.components
        for b in law.components
    )
    require(first - second / 2 >= -1e-12 * max(1.0, first), "negative fusion CRPS")
    return finite(max(0.0, first - second / 2))


def nll(law: FusionDistribution, truth: float) -> float | None:
    finite(truth)
    if any(
        c.distribution.family is not DistributionFamily.GAUSSIAN_LOCATION_SCALE
        for c in law.components
    ):
        return None
    logs = tuple(
        finite(
            log(c.weight)
            - log(c.distribution.scale)
            - 0.5 * log(2 * pi)
            - 0.5 * finite(((truth - c.distribution.location) / c.distribution.scale) ** 2)
        )
        for c in law.components
    )
    high = max(logs)
    return finite(-(high + log(fsum(exp(v - high) for v in logs))))


def quantile(law: FusionDistribution, q: float) -> float:
    require(False, "fusion mixture quantiles unavailable; no averaging of quantiles")
    raise AssertionError("unreachable")

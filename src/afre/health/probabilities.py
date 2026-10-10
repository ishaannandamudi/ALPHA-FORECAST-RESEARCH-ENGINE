"""Exact native laws only; no invented distribution distance or mixture quantiles."""

from typing import TYPE_CHECKING

from afre.calibration.artifacts import CalibratedForecast, IntervalValue
from afre.fusion.artifacts import FusedForecast
from afre.fusion.probabilistic import (
    FusionDistribution,
    blend,
    crps,
    nll,
    threshold_probability,
    variance_parts,
)
from afre.mixture.artifacts import MixtureDistribution
from afre.probabilistic.artifacts import DistributionParameters
from afre.probabilistic.distributions import quantile
from afre.probabilistic.schema import DistributionFamily, ThresholdComparison
from afre.schema import require
from afre.uncertainty.moments import variance as native_variance
from afre.uncertainty.sources import source_for

if TYPE_CHECKING:
    from afre.health.repository import HealthRepository

Law = DistributionParameters | MixtureDistribution | FusionDistribution


def predictive_variance(law: Law | None) -> float | None:
    if isinstance(law, FusionDistribution):
        a, b = variance_parts(law)
        return a + b
    return native_variance(law)


def law_for(repo: "HealthRepository", identity: str) -> tuple[Law | None, IntervalValue | None]:
    raw = repo.get_any(identity)
    if isinstance(raw, FusedForecast):
        return raw.law, None
    source = source_for(repo, identity)
    return source.law, source.interval


def exact_mixture(law: Law) -> FusionDistribution | None:
    if isinstance(law, FusionDistribution):
        return law
    if (
        isinstance(law, DistributionParameters)
        and law.family is DistributionFamily.QUANTILE_SET
    ):
        return None
    return blend(((law.fingerprint, law.fingerprint, 1.0, law),), 32)


def event_probability(
    repo: "HealthRepository", identity: str, threshold: float
) -> float | None:
    law, _ = law_for(repo, identity)
    if law is not None and (mixture := exact_mixture(law)) is not None:
        return threshold_probability(mixture, threshold)
    raw = repo.get_any(identity)
    if isinstance(raw, CalibratedForecast):
        return next(
            (
                p.probability
                for p in raw.probabilities
                if p.request.value == threshold
                and p.request.comparison is ThresholdComparison.GT
            ),
            None,
        )
    return None


def interval_for(
    repo: "HealthRepository", identity: str, levels: tuple[float, float]
) -> tuple[float, float] | None:
    law, interval = law_for(repo, identity)
    if interval is not None:
        if (interval.lower_level, interval.upper_level) != levels:
            return None
        return interval.lower, interval.upper
    if isinstance(law, DistributionParameters):
        return quantile(law, levels[0]), quantile(law, levels[1])
    return None


def proper_score(
    repo: "HealthRepository", identity: str, truth: float, negative_log: bool
) -> float | None:
    law, _ = law_for(repo, identity)
    if law is None:
        return None
    mixture = exact_mixture(law)
    if mixture is None:
        return None
    require(
        len(mixture.components) <= repo.health_bounds.sources,
        "health probability component bound",
    )
    return nll(mixture, truth) if negative_log else crps(mixture, truth)

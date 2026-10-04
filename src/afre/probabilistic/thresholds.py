"""Four explicit event inequalities, including exact empirical atom endpoints."""

from afre.probabilistic.artifacts import DistributionParameters
from afre.probabilistic.definitions import ThresholdRequest
from afre.probabilistic.distributions import cdf, survival
from afre.probabilistic.schema import ThresholdComparison
from afre.schema import require


def threshold_probability(
    distribution: DistributionParameters, request: ThresholdRequest
) -> float:
    comparison = request.comparison
    value = (
        survival(distribution, request.value)
        if comparison is ThresholdComparison.GT
        else survival(distribution, request.value, True)
        if comparison is ThresholdComparison.GE
        else cdf(distribution, request.value, True)
        if comparison is ThresholdComparison.LT
        else cdf(distribution, request.value)
    )
    require(0 <= value <= 1, "invalid distribution event probability")
    return value


def event_outcome(truth: float, request: ThresholdRequest) -> bool:
    return (
        truth > request.value
        if request.comparison is ThresholdComparison.GT
        else truth >= request.value
        if request.comparison is ThresholdComparison.GE
        else truth < request.value
        if request.comparison is ThresholdComparison.LT
        else truth <= request.value
    )

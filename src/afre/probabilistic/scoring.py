"""Proper scores and immutable diagnostic coverage/PIT; no fitting transforms."""

import math
from dataclasses import replace

from afre.probabilistic.artifacts import (
    DistributionParameters,
    ProbabilisticForecast,
    ProbabilityScore,
)
from afre.probabilistic.definitions import ProbabilisticEvaluationProtocol
from afre.probabilistic.distributions import cdf, quantile
from afre.probabilistic.schema import DistributionFamily, ScoreName, ScoreState
from afre.probabilistic.thresholds import event_outcome
from afre.schema import require
from afre.statistical_models.linear_algebra import finite, total


def negative_log_likelihood(distribution: DistributionParameters, truth: float) -> float:
    finite(truth)
    require(
        distribution.family is DistributionFamily.GAUSSIAN_LOCATION_SCALE,
        "NLL requires continuous Gaussian density",
    )
    z = finite(finite(truth - distribution.location) / distribution.scale)
    return finite(
        math.log(distribution.scale) + 0.5 * math.log(2 * math.pi) + finite(0.5 * finite(z * z))
    )


def gaussian_crps(distribution: DistributionParameters, truth: float) -> float:
    finite(truth)
    require(
        distribution.family is DistributionFamily.GAUSSIAN_LOCATION_SCALE,
        "Gaussian CRPS family mismatch",
    )
    difference = finite(truth - distribution.location)
    z = difference / distribution.scale
    phi = math.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)
    return finite(
        difference * math.erf(z / math.sqrt(2))
        + distribution.scale * (2 * phi - 1 / math.sqrt(math.pi))
    )


def empirical_crps(distribution: DistributionParameters, truth: float) -> float:
    finite(truth)
    require(
        distribution.family is DistributionFamily.EMPIRICAL_RESIDUAL,
        "empirical CRPS family mismatch",
    )
    count = len(distribution.samples)
    # Exact integral of quantile loss over the equal-mass step CDF; positive terms
    # avoid cancellation in E|X-y| - E|X-X'|/2. This is not fair-ensemble CRPS.
    terms = []
    for i, value in enumerate(distribution.samples):
        difference = finite(truth - finite(distribution.location + value))
        q = (i + 0.5) / count
        terms.append(finite((q if difference >= 0 else 1 - q) * abs(difference)))
    return finite(2 * (total(terms) / count))


def pinball_loss(q: float, prediction: float, truth: float) -> float:
    finite(q)
    require(0 < q < 1, "pinball quantile domain")
    finite(prediction)
    finite(truth)
    difference = finite(truth - prediction)
    return finite((q if difference >= 0 else q - 1) * difference)


def brier_score(probability: float, outcome: bool) -> float:
    finite(probability)
    require(0 <= probability <= 1 and type(outcome) is bool, "Brier probability/outcome domain")
    return finite((probability - float(outcome)) ** 2)


def score_forecast(
    forecast: ProbabilisticForecast, truth: float, protocol: ProbabilisticEvaluationProtocol
) -> tuple[tuple[ProbabilityScore, ...], float | None]:
    finite(truth)
    require(
        protocol.implementation_version == "proper-scores-v1", "unknown evaluation protocol"
    )
    distribution = forecast.distribution
    family = distribution.family
    scores = []

    def add(
        name: ScoreName,
        value: float | None,
        level: float | None = None,
        upper: float | None = None,
    ) -> None:
        scores.append(
            ProbabilityScore(
                name,
                value,
                ScoreState.AVAILABLE if value is not None else ScoreState.UNSUPPORTED,
                1,
                level,
                upper,
            )
        )

    add(ScoreName.COUNT, 1.0)
    add(
        ScoreName.NLL,
        negative_log_likelihood(distribution, truth)
        if family is DistributionFamily.GAUSSIAN_LOCATION_SCALE
        else None,
    )
    add(
        ScoreName.CRPS,
        gaussian_crps(distribution, truth)
        if family is DistributionFamily.GAUSSIAN_LOCATION_SCALE
        else empirical_crps(distribution, truth)
        if family is DistributionFamily.EMPIRICAL_RESIDUAL
        else None,
    )
    pinballs = []
    for value in forecast.quantiles:
        loss = pinball_loss(value.level, value.value, truth)
        pinballs.append(loss)
        add(ScoreName.PINBALL, loss, value.level)
        add(ScoreName.QUANTILE_FREQUENCY, float(truth <= value.value), value.level)
    add(ScoreName.PINBALL, finite(total(pinballs) / len(pinballs)))
    briers = []
    for event in forecast.threshold_probabilities:
        loss = brier_score(event.probability, event_outcome(truth, event.request))
        briers.append(loss)
        scores.append(
            ProbabilityScore(
                ScoreName.BRIER, loss, ScoreState.AVAILABLE, 1, threshold=event.request
            )
        )
    add(ScoreName.BRIER, finite(total(briers) / len(briers)) if briers else None)
    for interval in protocol.intervals:
        levels = {q.level for q in forecast.quantiles}
        require(
            interval.lower in levels and interval.upper in levels,
            "coverage interval must use requested quantiles",
        )
        low, high = (
            quantile(distribution, interval.lower),
            quantile(distribution, interval.upper),
        )
        add(
            ScoreName.INTERVAL_COVERAGE,
            float(low <= truth <= high),
            interval.lower,
            interval.upper,
        )
        add(ScoreName.INTERVAL_WIDTH, finite(high - low), interval.lower, interval.upper)
    pit = None if family is DistributionFamily.QUANTILE_SET else cdf(distribution, truth)
    add(ScoreName.PIT_MEAN, pit)
    add(ScoreName.SHARPNESS_SCALE, distribution.scale)
    return tuple(sorted(scores, key=lambda s: s.key)), pit


def aggregate_scores(
    groups: tuple[tuple[ProbabilityScore, ...], ...], template: tuple[ProbabilityScore, ...]
) -> tuple[ProbabilityScore, ...]:
    if not groups:
        return tuple(
            replace(
                s,
                value=0.0 if s.name is ScoreName.COUNT else None,
                state=ScoreState.AVAILABLE
                if s.name is ScoreName.COUNT
                else ScoreState.INSUFFICIENT_OBSERVATIONS,
                sample_count=0,
            )
            for s in template
        )
    require(
        all(tuple(s.key for s in group) == tuple(s.key for s in template) for group in groups),
        "score protocol mismatch",
    )
    result = []
    for index, prototype in enumerate(template):
        values = [group[index].value for group in groups]
        if any(v is None for v in values):
            result.append(
                replace(
                    prototype,
                    value=None,
                    state=ScoreState.UNSUPPORTED,
                    sample_count=len(groups),
                )
            )
        else:
            valid = [v for v in values if v is not None]
            value = (
                float(len(groups))
                if prototype.name is ScoreName.COUNT
                else finite(total(valid) / len(valid))
            )
            result.append(
                replace(
                    prototype, value=value, state=ScoreState.AVAILABLE, sample_count=len(groups)
                )
            )
    return tuple(result)

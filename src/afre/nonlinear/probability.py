"""Reuse AFRE-6 finite-law scoring and event/quantile arithmetic without new laws."""

from afre.nonlinear.artifacts import NonlinearProbabilityView
from afre.probabilistic.artifacts import ProbabilityScore
from afre.probabilistic.definitions import ThresholdRequest
from afre.probabilistic.distributions import cdf
from afre.probabilistic.schema import DistributionFamily, ScoreName, ScoreState
from afre.probabilistic.scoring import (
    brier_score,
    empirical_crps,
    gaussian_crps,
    negative_log_likelihood,
    pinball_loss,
)
from afre.probabilistic.thresholds import event_outcome, threshold_probability


def probability_scores(
    view: NonlinearProbabilityView, truth: float, requests: tuple[ThresholdRequest, ...]
) -> tuple[ProbabilityScore, ...]:
    law = view.distribution
    gaussian = law.family is DistributionFamily.GAUSSIAN_LOCATION_SCALE
    empirical = law.family is DistributionFamily.EMPIRICAL_RESIDUAL
    values = [
        (ScoreName.COUNT, 1.0),
        (ScoreName.NLL, negative_log_likelihood(law, truth) if gaussian else None),
        (
            ScoreName.CRPS,
            gaussian_crps(law, truth)
            if gaussian
            else empirical_crps(law, truth)
            if empirical
            else None,
        ),
        (ScoreName.PIT_MEAN, cdf(law, truth) if gaussian or empirical else None),
        (ScoreName.SHARPNESS_SCALE, law.scale),
    ]
    scores = [
        ProbabilityScore(
            name,
            value,
            ScoreState.AVAILABLE if value is not None else ScoreState.UNSUPPORTED,
            1,
        )
        for name, value in values
    ]
    for q in view.quantiles:
        scores.append(
            ProbabilityScore(
                ScoreName.PINBALL,
                pinball_loss(q.level, q.value, truth),
                ScoreState.AVAILABLE,
                1,
                q.level,
            )
        )
        scores.append(
            ProbabilityScore(
                ScoreName.QUANTILE_FREQUENCY,
                float(truth <= q.value),
                ScoreState.AVAILABLE,
                1,
                q.level,
            )
        )
    for request in requests:
        scores.append(
            ProbabilityScore(
                ScoreName.BRIER,
                brier_score(threshold_probability(law, request), event_outcome(truth, request)),
                ScoreState.AVAILABLE,
                1,
                threshold=request,
            )
        )
    return tuple(sorted(scores, key=lambda s: s.key))

"""Existing proper-score arithmetic; calibrated marginals do not invent a full law."""

from afre.calibration.artifacts import CalibratedForecast
from afre.mixture.artifacts import MixtureDistribution
from afre.mixture.probabilistic import mixture_scores, mixture_threshold
from afre.probabilistic.artifacts import DistributionParameters, ProbabilityScore
from afre.probabilistic.definitions import ThresholdRequest
from afre.probabilistic.distributions import quantile
from afre.probabilistic.schema import DistributionFamily, ScoreName, ScoreState
from afre.probabilistic.scoring import (
    brier_score,
    empirical_crps,
    gaussian_crps,
    negative_log_likelihood,
    pinball_loss,
)
from afre.probabilistic.thresholds import event_outcome, threshold_probability
from afre.uncertainty.sources import ForecastSource


def scores_for(
    source: ForecastSource,
    truth: float,
    levels: tuple[float, float],
    thresholds: tuple[ThresholdRequest, ...],
    work_cells: int,
) -> tuple[ProbabilityScore, ...]:
    law = source.law
    nll = crps = None
    qs: dict[float, float] = {}
    ps: dict[ThresholdRequest, float] = {}
    if isinstance(law, MixtureDistribution):
        existing = mixture_scores(law, truth, thresholds, work_cells)
        nll = next(s.value for s in existing if s.name is ScoreName.NLL)
        crps = next(s.value for s in existing if s.name is ScoreName.CRPS)
        ps = {request: mixture_threshold(law, request) for request in thresholds}
    elif isinstance(law, DistributionParameters):
        if law.family is DistributionFamily.GAUSSIAN_LOCATION_SCALE:
            nll, crps = negative_log_likelihood(law, truth), gaussian_crps(law, truth)
        elif law.family is DistributionFamily.EMPIRICAL_RESIDUAL:
            crps = empirical_crps(law, truth)
        qs = {
            q: quantile(law, q)
            for q in sorted({*levels, 0.5})
            if law.family is not DistributionFamily.QUANTILE_SET
            or q in {v.level for v in law.quantile_values}
        }
        if law.family is not DistributionFamily.QUANTILE_SET:
            ps = {request: threshold_probability(law, request) for request in thresholds}
    if isinstance(source.artifact, CalibratedForecast):
        qs = {q.level: q.value for q in source.artifact.quantiles}
        ps = {p.request: p.probability for p in source.artifact.probabilities}
    results = [
        ProbabilityScore(
            name,
            value,
            ScoreState.AVAILABLE if value is not None else ScoreState.UNSUPPORTED,
            1,
        )
        for name, value in ((ScoreName.NLL, nll), (ScoreName.CRPS, crps))
    ]
    for q in sorted({*levels, 0.5}):
        value = pinball_loss(q, qs[q], truth) if q in qs else None
        results.append(
            ProbabilityScore(
                ScoreName.PINBALL,
                value,
                ScoreState.AVAILABLE if value is not None else ScoreState.UNSUPPORTED,
                1,
                q,
            )
        )
    for request in thresholds:
        value = (
            brier_score(ps[request], event_outcome(truth, request)) if request in ps else None
        )
        results.append(
            ProbabilityScore(
                ScoreName.BRIER,
                value,
                ScoreState.AVAILABLE if value is not None else ScoreState.UNSUPPORTED,
                1,
                threshold=request,
            )
        )
    return tuple(sorted(results, key=lambda s: s.key))

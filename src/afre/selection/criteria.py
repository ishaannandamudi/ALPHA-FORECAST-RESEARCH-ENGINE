"""Exact native point metrics and supported native probability scores."""

import math

from afre.probabilistic.artifacts import DistributionParameters
from afre.probabilistic.schema import DistributionFamily
from afre.probabilistic.scoring import empirical_crps, gaussian_crps, negative_log_likelihood
from afre.schema import require
from afre.selection.results import CandidateValidationPair
from afre.selection.schema import SelectionCriterion
from afre.statistical_models.metrics import point_metrics
from afre.statistical_models.schema import MetricName


def loss(
    criterion: SelectionCriterion,
    prediction: float,
    truth: float,
    law: DistributionParameters | None,
) -> float | None:
    if criterion is SelectionCriterion.MIN_MAE:
        return abs(prediction - truth)
    if criterion in (SelectionCriterion.MIN_MSE, SelectionCriterion.MAX_R2):
        return (prediction - truth) ** 2
    if law is None:
        return None
    if criterion is SelectionCriterion.MIN_NLL:
        return (
            negative_log_likelihood(law, truth)
            if law.family is DistributionFamily.GAUSSIAN_LOCATION_SCALE
            else None
        )
    if law.family is DistributionFamily.GAUSSIAN_LOCATION_SCALE:
        return gaussian_crps(law, truth)
    return (
        empirical_crps(law, truth)
        if law.family is DistributionFamily.EMPIRICAL_RESIDUAL
        else None
    )


def metric(
    criterion: SelectionCriterion,
    pairs: tuple[CandidateValidationPair, ...],
    losses: tuple[float | None, ...],
) -> float | None:
    if not pairs:
        return None
    if criterion in (
        SelectionCriterion.MIN_MSE,
        SelectionCriterion.MIN_MAE,
        SelectionCriterion.MAX_R2,
    ):
        name = {
            SelectionCriterion.MIN_MSE: MetricName.MSE,
            SelectionCriterion.MIN_MAE: MetricName.MAE,
            SelectionCriterion.MAX_R2: MetricName.R_SQUARED,
        }[criterion]
        return next(
            m.value
            for m in point_metrics(
                tuple(p.prediction for p in pairs), tuple(p.truth for p in pairs)
            )
            if m.name is name
        )
    if any(v is None for v in losses):
        return None
    values = tuple(v for v in losses if v is not None)
    value = math.fsum(values) / len(values)
    require(math.isfinite(value), "nonfinite selection metric")
    return value

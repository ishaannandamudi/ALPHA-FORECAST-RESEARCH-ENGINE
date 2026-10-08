"""Affine raw-scale conversion and exact sign summaries of supplied frozen fits."""

from statistics import fmean, median
from typing import TYPE_CHECKING

from afre.feature_store.normalization import NormalizationMethod
from afre.invariance.artifacts import StabilityParameterSummary
from afre.research_datasets.preprocessing import FoldPreprocessingState
from afre.schema import require
from afre.statistical_models.artifacts import FittedModelArtifact, ModelFitInputs
from afre.statistical_models.linear_algebra import finite

if TYPE_CHECKING:
    from afre.invariance.repository import InvarianceRepository


def affine_parameters(state: FoldPreprocessingState) -> tuple[float, float] | None:
    method = state.normalization.spec.method
    p = {x.name: float(x.value) for x in state.normalization.parameters}
    if method is NormalizationMethod.NONE:
        return 0.0, 1.0
    keys = {
        NormalizationMethod.STANDARDIZE: ("mean", "stddev"),
        NormalizationMethod.ROBUST_STANDARDIZE: ("median", "iqr"),
        NormalizationMethod.MINMAX: ("minimum", "range"),
    }
    if method not in keys:
        return None
    center, scale = keys[method]
    require(p[scale] > 0, "raw coefficient positive scale")
    return p[center], p[scale]


def raw_coefficients(
    repo: "InvarianceRepository", model: FittedModelArtifact
) -> tuple[float, tuple[float, ...]] | None:
    inputs = repo.resolve(ModelFitInputs, model.fit_inputs_id)
    states = tuple(
        repo.resolve(FoldPreprocessingState, i) for i in inputs.preprocessing_state_ids
    )
    by_feature = {s.spec.normalization.feature.definition.fingerprint: s for s in states}
    require(len(by_feature) == len(states), "unique preprocessing per feature")
    intercept, coefficients = model.intercept, []
    for feature, beta in zip(model.feature_ids, model.coefficients, strict=True):
        affine = affine_parameters(by_feature[feature]) if feature in by_feature else (0.0, 1.0)
        if affine is None:
            return None
        center, scale = affine
        coefficient = finite(beta / scale)
        intercept = finite(intercept - coefficient * center)
        coefficients.append(coefficient)
    return intercept, tuple(coefficients)


def parameter_summary(name: str, values: tuple[float, ...]) -> StabilityParameterSummary:
    require(bool(values), "nonempty parameter summary")
    negative, zero, positive = (
        sum(v < 0 for v in values) / len(values),
        sum(v == 0 for v in values) / len(values),
        sum(v > 0 for v in values) / len(values),
    )
    return StabilityParameterSummary(
        name,
        min(values),
        max(values),
        finite(fmean(values)),
        finite(median(values)),
        negative,
        zero,
        positive,
        max(negative, zero, positive),
    )

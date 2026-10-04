"""Transparent reference statistics and deterministic fixed-penalty linear fits."""

import math
from dataclasses import dataclass
from statistics import median

from afre.schema import require
from afre.statistical_models.artifacts import DesignMatrix, FitDiagnostics
from afre.statistical_models.definitions import CONSTANT_FAMILIES, BaselineModelSpec
from afre.statistical_models.elastic import coordinate_descent
from afre.statistical_models.linear_algebra import dot, finite, householder_qr, total
from afre.statistical_models.schema import (
    InterceptPolicy,
    ModelBounds,
    ModelFamily,
    NonconvergencePolicy,
)


@dataclass(frozen=True)
class FitResult:
    intercept: float
    coefficients: tuple[float, ...]
    reference_value: float | None
    diagnostics: FitDiagnostics


def fit_values(
    spec: BaselineModelSpec,
    matrix: DesignMatrix,
    bounds: ModelBounds,
) -> FitResult:
    require(
        0 < len(matrix.rows) <= bounds.samples
        and len(matrix.feature_ids) <= bounds.features
        and len(matrix.rows) * max(1, len(matrix.feature_ids)) <= bounds.dense_cells,
        "fit sample/feature/dense-cell bound",
    )
    require(spec.max_iterations <= bounds.iterations, "fit iteration bound")
    x = tuple(r.values for r in matrix.rows)
    y = tuple(r.response for r in matrix.rows)
    count, width = len(y), len(matrix.feature_ids)
    require(
        width + (spec.intercept is InterceptPolicy.GLOBAL) <= bounds.coefficients,
        "fit coefficient bound",
    )
    average = finite(y[0] + total([finite(v - y[0]) for v in y]) / count)
    centered = tuple(finite(v - average) for v in y)
    stddev = (
        0.0 if min(y) == max(y) else finite(math.sqrt(finite(dot(centered, centered) / count)))
    )
    reference = None
    intercept, betas, rank, proxy, iterations, converged, kkt = (
        0.0,
        (0.0,) * width,
        None,
        None,
        0,
        True,
        0.0,
    )
    if spec.family in CONSTANT_FAMILIES:
        if spec.family is ModelFamily.PERSISTENCE:
            assert spec.persistence is not None
            index = matrix.feature_ids.index(spec.persistence.feature_definition_id)
            betas = tuple(1.0 if j == index else 0.0 for j in range(width))
        else:
            reference = (
                average
                if spec.family is ModelFamily.UNCONDITIONAL_MEAN
                else float(median(y))
                if spec.family is ModelFamily.UNCONDITIONAL_MEDIAN
                else spec.reference_value
            )
            assert reference is not None
            intercept = reference
    else:
        has_intercept = spec.intercept is InterceptPolicy.GLOBAL
        design = tuple((1.0, *r) if has_intercept else r for r in x)
        if spec.family in (ModelFamily.LASSO_REGRESSION, ModelFamily.ELASTIC_NET):
            solution = coordinate_descent(
                design,
                y,
                spec.l1_penalty,
                spec.l2_penalty,
                spec.max_iterations,
                spec.tolerance,
                has_intercept and not spec.regularize_intercept,
            )
            coefficients = solution.coefficients
            iterations, converged, kkt = (
                solution.iterations,
                solution.converged,
                solution.kkt_residual,
            )
            require(
                converged or spec.nonconvergence is NonconvergencePolicy.RETURN_NONCONVERGED,
                "coordinate descent did not converge",
            )
        else:
            response = y
            if spec.l2_penalty > 0:
                penalty = finite(math.sqrt(spec.l2_penalty))
                padded = []
                for j in range(len(design[0])):
                    if j == 0 and has_intercept and not spec.regularize_intercept:
                        continue
                    padded.append(
                        tuple(penalty if k == j else 0.0 for k in range(len(design[0])))
                    )
                design = (*design, *padded)
                response = (*response, *((0.0,) * len(padded)))
            qr = householder_qr(design, response, spec.tolerance, spec.condition_limit)
            coefficients, rank, proxy, iterations = (
                qr.coefficients,
                qr.rank,
                qr.condition_proxy,
                1,
            )
        intercept = coefficients[0] if has_intercept else 0.0
        betas = coefficients[1:] if has_intercept else coefficients
    residual = tuple(
        finite(truth - finite(intercept + dot(row, betas)))
        for row, truth in zip(x, y, strict=True)
    )
    scales = tuple(finite(math.hypot(*(row[j] for row in x))) for j in range(width))
    diagnostics = FitDiagnostics(
        count,
        width,
        average,
        stddev,
        dot(residual, residual),
        finite(math.hypot(*betas)),
        rank,
        proxy,
        scales,
        iterations,
        converged,
        kkt,
    )
    return FitResult(finite(intercept), betas, reference, diagnostics)

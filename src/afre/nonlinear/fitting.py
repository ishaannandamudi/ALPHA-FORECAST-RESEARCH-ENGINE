"""AFRE-5 pivoted QR plus fixed ridge, or deterministic shallow TRAIN SSE trees."""

import math
from statistics import pstdev

from afre.nonlinear.artifacts import InteractionMatrix, NonlinearModelArtifact, TreeNode
from afre.nonlinear.definitions import NonlinearModelSpec
from afre.nonlinear.schema import NonlinearBounds, NonlinearFamily, NonlinearPreprocessing
from afre.nonlinear.trees import fit_tree, tree_prediction
from afre.schema import require
from afre.statistical_models.linear_algebra import dot, finite, householder_qr, total


def fit_model(
    spec: NonlinearModelSpec,
    matrix: InteractionMatrix,
    started_ns: int,
    completed_ns: int,
    available_ns: int,
    bounds: NonlinearBounds,
) -> NonlinearModelArtifact:
    require(
        matrix.spec_id == spec.fingerprint
        and matrix.columns == spec.columns
        and started_ns >= matrix.computed_ns,
        "model exact matrix/fit time",
    )
    x = tuple(r.values for r in matrix.rows)
    y = tuple(r.response for r in matrix.rows)
    count, width = len(x), len(matrix.columns)
    require(
        count <= bounds.training_rows
        and width <= bounds.features
        and count * width <= bounds.work_cells,
        "nonlinear fit work bound",
    )
    centers = (0.0,) * width
    scales = (1.0,) * width
    if spec.preprocessing is NonlinearPreprocessing.STANDARDIZE:
        centers = tuple(finite(total([r[j] for r in x]) / count) for j in range(width))
        scales = tuple(finite(pstdev(tuple(r[j] for r in x))) for j in range(width))
        require(all(v > 0 for v in scales), "zero TRAIN scale; no silent replacement")
        x = tuple(
            tuple(finite((v - c) / s) for v, c, s in zip(r, centers, scales, strict=True))
            for r in x
        )
    nodes: tuple[TreeNode, ...] = ()
    intercept = 0.0
    coefficients: tuple[float, ...] = ()
    rank = None
    condition = None
    if spec.family is NonlinearFamily.SHALLOW_REGRESSION_TREE:
        assert spec.tree is not None
        nodes = fit_tree(
            matrix.columns, x, y, tuple(r.sample_id for r in matrix.rows), spec.tree, bounds
        )
        predictions = tuple(tree_prediction(nodes, matrix.columns, r)[0] for r in x)
    else:
        design = tuple((1.0, *r) for r in x)
        response = y
        if spec.ridge_penalty > 0:
            penalty = finite(math.sqrt(spec.ridge_penalty))
            padded = tuple(
                tuple(penalty if k == j else 0.0 for k in range(width + 1))
                for j in range(1, width + 1)
            )
            design = (*design, *padded)
            response = (*response, *((0.0,) * width))
        result = householder_qr(design, response, spec.tolerance, spec.condition_limit)
        intercept, coefficients = result.coefficients[0], result.coefficients[1:]
        rank, condition = result.rank, result.condition_proxy
        predictions = tuple(finite(intercept + dot(r, coefficients)) for r in x)
    residual = tuple(finite(a - b) for a, b in zip(y, predictions, strict=True))
    return NonlinearModelArtifact(
        spec.fingerprint,
        matrix.fingerprint,
        tuple(r.sample_id for r in matrix.rows),
        matrix.transform_ids,
        matrix.columns,
        spec.family,
        centers,
        scales,
        intercept,
        coefficients,
        nodes,
        dot(residual, residual),
        rank,
        condition,
        spec.cutoff_ns,
        started_ns,
        completed_ns,
        available_ns,
    )

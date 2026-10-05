"""Deterministic simplex-constrained mean squared loss; no architecture search."""

from math import fsum

from afre.schema import require
from afre.statistical_models.linear_algebra import finite


def project_simplex(values: tuple[float, ...]) -> tuple[float, ...]:
    require(bool(values), "empty simplex projection")
    ordered = sorted((finite(v) for v in values), reverse=True)
    prefix = 0.0
    theta = 0.0
    for index, value in enumerate(ordered, 1):
        prefix = finite(prefix + value)
        candidate = (prefix - 1.0) / index
        if value > candidate:
            theta = candidate
    return tuple(max(0.0, finite(v - theta)) for v in values)


def solve_simplex(
    matrix: tuple[tuple[float, ...], ...],
    responses: tuple[float, ...],
    ridge: float = 0.0,
    maximum_iterations: int = 10_000,
    tolerance: float = 1e-10,
    work_cells: int = 2_000_000,
) -> tuple[tuple[float, ...], int, float, float]:
    require(
        bool(matrix) and len(matrix) == len(responses) and bool(matrix[0]),
        "simplex training matrix shape",
    )
    n, m = len(matrix), len(matrix[0])
    require(all(len(row) == m for row in matrix), "ragged simplex matrix")
    require(
        n * m * m <= work_cells and maximum_iterations * m * m <= work_cells,
        "simplex solver work bound",
    )
    require(ridge >= 0 and maximum_iterations > 0 and tolerance > 0, "simplex numerical policy")
    scale = (
        max(
            *(abs(finite(v)) for row in matrix for v in row),
            *(abs(finite(y)) for y in responses),
        )
        or 1.0
    )
    x = tuple(tuple(v / scale for v in row) for row in matrix)
    y = tuple(v / scale for v in responses)
    penalty = ridge / scale / scale
    gram = tuple(
        tuple(fsum(row[i] * row[j] for row in x) / n for j in range(m)) for i in range(m)
    )
    xy = tuple(
        fsum(row[i] * target for row, target in zip(x, y, strict=True)) / n for i in range(m)
    )
    lipschitz = 2 * max(fsum(abs(g) for g in row) + penalty for row in gram)
    step = 1 / max(1.0, lipschitz)
    weights = tuple(1 / m for _ in range(m))
    residual = float("inf")
    for iteration in range(1, maximum_iterations + 1):
        gradient = tuple(
            2
            * (
                fsum(g * w for g, w in zip(row, weights, strict=True))
                - xy[i]
                + penalty * weights[i]
            )
            for i, row in enumerate(gram)
        )
        projected = project_simplex(
            tuple(w - g for w, g in zip(weights, gradient, strict=True))
        )
        residual = max(abs(w - p) for w, p in zip(weights, projected, strict=True))
        if residual <= tolerance:
            objective = finite(
                fsum(
                    finite(fsum(a * w for a, w in zip(row, weights, strict=True)) - target)
                    * finite(fsum(a * w for a, w in zip(row, weights, strict=True)) - target)
                    for row, target in zip(matrix, responses, strict=True)
                )
                / n
                + ridge * fsum(w * w for w in weights)
            )
            return weights, iteration, residual, objective
        weights = project_simplex(
            tuple(w - step * g for w, g in zip(weights, gradient, strict=True))
        )
    require(False, "simplex gate did not converge within declared iteration limit")
    raise AssertionError("unreachable")

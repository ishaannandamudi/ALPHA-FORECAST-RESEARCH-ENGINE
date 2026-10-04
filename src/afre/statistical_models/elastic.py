"""Cyclic coordinate descent for sum SSE + L1*|beta| + L2*beta²."""

from dataclasses import dataclass

from afre.schema import require
from afre.statistical_models.linear_algebra import dot, finite, total


@dataclass(frozen=True)
class CoordinateSolution:
    coefficients: tuple[float, ...]
    iterations: int
    converged: bool
    kkt_residual: float


def coordinate_descent(
    matrix: tuple[tuple[float, ...], ...],
    response: tuple[float, ...],
    l1: float,
    l2: float,
    max_iterations: int,
    tolerance: float,
    unpenalized_intercept: bool,
) -> CoordinateSolution:
    require(bool(matrix) and len(matrix) == len(response), "coordinate descent row shape")
    width = len(matrix[0])
    require(width > 0 and all(len(r) == width for r in matrix), "coordinate descent columns")
    require(
        l1 >= 0 and l2 >= 0 and max_iterations > 0 and 0 < tolerance < 1,
        "coordinate descent policy",
    )
    for row in matrix:
        for value in row:
            finite(value)
    for value in response:
        finite(value)
    columns = tuple(tuple(row[j] for row in matrix) for j in range(width))
    norms = tuple(dot(c, c) for c in columns)
    betas, residual = [0.0] * width, list(response)
    threshold = finite(
        tolerance * (1 + max(abs(finite(2 * dot(c, response))) for c in columns))
    )
    kkt = 0.0
    for iteration in range(1, max_iterations + 1):
        largest_change = 0.0
        for j, column in enumerate(columns):
            old = betas[j]
            penalty1 = 0.0 if j == 0 and unpenalized_intercept else l1
            penalty2 = 0.0 if j == 0 and unpenalized_intercept else l2
            correlation = total(
                [
                    finite(x * finite(r + finite(x * old)))
                    for x, r in zip(column, residual, strict=True)
                ]
            )
            denominator = finite(norms[j] + penalty2)
            soft = max(0.0, abs(correlation) - penalty1 / 2)
            updated = (
                finite((soft if correlation >= 0 else -soft) / denominator)
                if denominator > 0
                else 0.0
            )
            change = finite(updated - old)
            betas[j] = updated
            largest_change = max(largest_change, abs(change))
            residual = [
                finite(r - finite(x * change)) for x, r in zip(column, residual, strict=True)
            ]
        # Recompute from the fixed row order to avoid cumulative residual drift.
        residual = [
            finite(y - dot(row, tuple(betas))) for row, y in zip(matrix, response, strict=True)
        ]
        violations = []
        for j, column in enumerate(columns):
            penalty1 = 0.0 if j == 0 and unpenalized_intercept else l1
            penalty2 = 0.0 if j == 0 and unpenalized_intercept else l2
            gradient = finite(
                2 * finite(dot(column, tuple(residual)) - finite(penalty2 * betas[j]))
            )
            violations.append(
                abs(gradient - penalty1)
                if betas[j] > 0
                else abs(gradient + penalty1)
                if betas[j] < 0
                else max(0.0, abs(gradient) - penalty1)
            )
        kkt = finite(max(violations))
        if kkt <= threshold and largest_change <= tolerance * (1 + max(map(abs, betas))):
            return CoordinateSolution(tuple(betas), iteration, True, kkt)
    return CoordinateSolution(tuple(betas), max_iterations, False, kkt)

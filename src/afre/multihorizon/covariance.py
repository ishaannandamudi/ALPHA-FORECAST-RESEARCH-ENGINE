"""Deterministic bounded empirical covariance and explicit tolerant PSD validation."""

import math

from afre.multihorizon.schema import Denominator
from afre.schema import require
from afre.statistical_models.linear_algebra import finite, total


def validate_psd(matrix: tuple[tuple[float, ...], ...], tolerance: float) -> None:
    n = len(matrix)
    require(
        0 < n <= 64
        and 0 < tolerance <= 1e-6
        and all(len(r) == n and all(math.isfinite(x) for x in r) for r in matrix),
        "PSD shape/finite/tolerance",
    )
    require(all(matrix[i][i] >= 0 for i in range(n)), "negative covariance variance")
    scale = max(1.0, max(abs(x) for r in matrix for x in r))
    bound = finite(tolerance * scale)
    require(
        all(abs(matrix[i][j] - matrix[j][i]) <= bound for i in range(n) for j in range(i)),
        "asymmetric covariance",
    )
    lower = [[0.0] * n for _ in range(n)]
    for i in range(n):
        pivot = finite(matrix[i][i] - total([finite(lower[i][k] ** 2) for k in range(i)]))
        require(pivot >= -bound, "covariance is not PSD")
        lower[i][i] = math.sqrt(pivot) if pivot > bound else 0.0
        for j in range(i + 1, n):
            residual = finite(
                matrix[j][i] - total([finite(lower[j][k] * lower[i][k]) for k in range(i)])
            )
            if lower[i][i] == 0:
                require(abs(residual) <= bound, "zero PSD pivot has nonzero column")
            else:
                lower[j][i] = finite(residual / lower[i][i])


def empirical_covariance(
    rows: tuple[tuple[float, ...], ...], denominator: Denominator
) -> tuple[tuple[float, ...], tuple[tuple[float, ...], ...]]:
    require(
        bool(rows) and 0 < len(rows[0]) <= 64 and all(len(r) == len(rows[0]) for r in rows),
        "residual matrix shape",
    )
    n, width = len(rows), len(rows[0])
    divisor = n if denominator is Denominator.POPULATION else n - 1
    require(divisor > 0, "covariance denominator insufficient")
    means = tuple(finite(total([r[h] for r in rows]) / n) for h in range(width))
    centered = tuple(tuple(finite(x - m) for x, m in zip(r, means, strict=True)) for r in rows)
    values = {
        (i, j): finite(total([finite(r[i] * r[j]) for r in centered]) / divisor)
        for i in range(width)
        for j in range(i, width)
    }
    matrix = tuple(
        tuple(values[min(i, j), max(i, j)] for j in range(width)) for i in range(width)
    )
    return means, matrix

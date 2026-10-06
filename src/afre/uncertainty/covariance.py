"""Pivoted Householder QR covariance; declared iid homoskedastic fixed-design OLS."""

import math

from afre.schema import require
from afre.statistical_models.linear_algebra import finite, total


def inverse_crossproduct(
    design: tuple[tuple[float, ...], ...], tolerance: float, condition_limit: float
) -> tuple[tuple[tuple[float, ...], ...], float]:
    require(bool(design) and bool(design[0]), "empty covariance design")
    n, p = len(design), len(design[0])
    require(
        n >= p and p <= 17 and n <= 2000 and all(len(r) == p for r in design),
        "covariance rectangular full-rank design bounds",
    )
    a, permutation = [list(r) for r in design], list(range(p))
    scale = finite(max(math.hypot(*(r[j] for r in design)) for j in range(p)))
    require(scale > 0, "rank-deficient covariance design")
    for k in range(p):
        norms = {j: finite(math.hypot(*(a[i][j] for i in range(k, n)))) for j in range(k, p)}
        pivot = max(norms, key=lambda j: (norms[j], -permutation[j]))
        norm = norms[pivot]
        require(norm > finite(tolerance * scale), "rank-deficient covariance design")
        if pivot != k:
            for row in a:
                row[k], row[pivot] = row[pivot], row[k]
            permutation[k], permutation[pivot] = permutation[pivot], permutation[k]
        alpha = -math.copysign(norm, a[k][k])
        vector = [a[i][k] for i in range(k, n)]
        vector[0] = finite(vector[0] - alpha)
        length = finite(math.hypot(*vector))
        vector = [finite(v / length) for v in vector]
        for j in range(k, p):
            projection = finite(
                2 * total([finite(v * a[k + i][j]) for i, v in enumerate(vector)])
            )
            for i, v in enumerate(vector):
                a[k + i][j] = finite(a[k + i][j] - finite(projection * v))
        a[k][k] = alpha
        for i in range(k + 1, n):
            a[i][k] = 0.0
    inverse = [[0.0] * p for _ in range(p)]
    for column in range(p):
        for i in reversed(range(p)):
            rhs = float(i == column) - total(
                [finite(a[i][j] * inverse[j][column]) for j in range(i + 1, p)]
            )
            inverse[i][column] = finite(rhs / a[i][i])
    # Frobenius condition bound for R is stronger than a diagonal ratio alone.
    condition = finite(
        math.hypot(*(a[i][j] for i in range(p) for j in range(i, p)))
        * math.hypot(*(v for row in inverse for v in row))
    )
    require(condition <= condition_limit, "ill-conditioned covariance design")
    result = [[0.0] * p for _ in range(p)]
    for i in range(p):
        for j in range(i, p):
            entry = total([finite(inverse[i][k] * inverse[j][k]) for k in range(p)])
            result[permutation[i]][permutation[j]] = entry
            result[permutation[j]][permutation[i]] = entry
    return tuple(tuple(r) for r in result), condition


def quadratic_variance(
    design: tuple[float, ...], covariance: tuple[tuple[float, ...], ...]
) -> float:
    require(
        bool(design)
        and len(design) == len(covariance) <= 17
        and all(len(r) == len(design) for r in covariance),
        "prediction covariance shape",
    )
    value = total(
        [
            finite(design[i] * finite(covariance[i][j] * design[j]))
            for i in range(len(design))
            for j in range(len(design))
        ]
    )
    require(value >= 0, "negative parameter prediction variance; no silent clamp")
    return value

"""Deterministic column-pivoted Householder QR; no inversion or normal equations."""

import math
from dataclasses import dataclass

from afre.schema import ContractError, require


def finite(value: float) -> float:
    require(math.isfinite(value), "numerical overflow/nonfinite result")
    return 0.0 if value == 0 else value


def total(values: tuple[float, ...] | list[float]) -> float:
    try:
        return finite(math.fsum(values))
    except (OverflowError, ValueError) as error:
        raise ContractError("numerical accumulation overflow") from error


def dot(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    require(len(left) == len(right), "dot-product shape mismatch")
    return total([finite(a * b) for a, b in zip(left, right, strict=True)])


@dataclass(frozen=True)
class QRSolution:
    coefficients: tuple[float, ...]
    rank: int
    condition_proxy: float


def householder_qr(
    matrix: tuple[tuple[float, ...], ...],
    response: tuple[float, ...],
    tolerance: float,
    condition_limit: float,
) -> QRSolution:
    require(bool(matrix) and len(matrix) == len(response), "QR row shape mismatch")
    width = len(matrix[0])
    require(
        width > 0 and len(matrix) >= width and all(len(r) == width for r in matrix),
        "QR requires a tall rectangular system",
    )
    require(0 < tolerance < 1 and condition_limit >= 1, "QR numerical policy")
    require(
        all(math.isfinite(v) for r in matrix for v in r)
        and all(math.isfinite(v) for v in response),
        "nonfinite QR inputs",
    )
    a, b, permutation = [list(r) for r in matrix], list(response), list(range(width))
    scale = finite(max(math.hypot(*(r[j] for r in matrix)) for j in range(width)))
    require(scale > 0, "rank-deficient system: all columns are zero")
    diagonal = []
    for k in range(width):
        norms = {
            j: finite(math.hypot(*(a[i][j] for i in range(k, len(a))))) for j in range(k, width)
        }
        pivot = max(norms, key=lambda j: (norms[j], -permutation[j]))
        norm = norms[pivot]
        require(norm > finite(tolerance * scale), "rank-deficient system: ridge required")
        if pivot != k:
            for row in a:
                row[k], row[pivot] = row[pivot], row[k]
            permutation[k], permutation[pivot] = permutation[pivot], permutation[k]
        alpha = -math.copysign(norm, a[k][k])
        vector = [a[i][k] for i in range(k, len(a))]
        vector[0] = finite(vector[0] - alpha)
        vector_norm = finite(math.hypot(*vector))
        vector = [finite(v / vector_norm) for v in vector]
        for j in range(k, width):
            projection = finite(
                2 * total([finite(v * a[k + i][j]) for i, v in enumerate(vector)])
            )
            for i, v in enumerate(vector):
                a[k + i][j] = finite(a[k + i][j] - finite(projection * v))
        projection = finite(2 * total([finite(v * b[k + i]) for i, v in enumerate(vector)]))
        for i, v in enumerate(vector):
            b[k + i] = finite(b[k + i] - finite(projection * v))
        a[k][k] = alpha
        for i in range(k + 1, len(a)):
            a[i][k] = 0.0
        diagonal.append(abs(alpha))
    proxy = finite(max(diagonal) / min(diagonal))
    require(proxy <= condition_limit, "ill-conditioned QR diagonal proxy: ridge required")
    solution = [0.0] * width
    for i in reversed(range(width)):
        remainder = total([finite(a[i][j] * solution[j]) for j in range(i + 1, width)])
        solution[i] = finite((b[i] - remainder) / a[i][i])
    original = [0.0] * width
    for index, value in zip(permutation, solution, strict=True):
        original[index] = value
    return QRSolution(tuple(original), width, proxy)

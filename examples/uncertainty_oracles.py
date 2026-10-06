"""Independent small-fixture arithmetic; never imported by the AFRE runtime."""

from math import fsum


def inverse(matrix: tuple[tuple[float, ...], ...]) -> tuple[tuple[float, ...], ...]:
    n = len(matrix)
    assert 0 < n <= 17 and all(len(r) == n for r in matrix)
    a = [list(r) + [float(i == j) for j in range(n)] for i, r in enumerate(matrix)]
    for k in range(n):
        pivot = max(range(k, n), key=lambda i: abs(a[i][k]))
        assert abs(a[pivot][k]) > 1e-18
        a[k], a[pivot] = a[pivot], a[k]
        scale = a[k][k]
        a[k] = [v / scale for v in a[k]]
        for i in range(n):
            if i != k:
                factor = a[i][k]
                a[i] = [v - factor * w for v, w in zip(a[i], a[k], strict=True)]
    return tuple(tuple(r[n:]) for r in a)


def ols_covariance(
    design: tuple[tuple[float, ...], ...], response: tuple[float, ...]
) -> tuple[tuple[tuple[float, ...], ...], float]:
    n, p = len(design), len(design[0])
    assert n > p and len(response) == n
    gram = tuple(tuple(fsum(r[i] * r[j] for r in design) for j in range(p)) for i in range(p))
    precision = inverse(gram)
    rhs = tuple(fsum(r[j] * y for r, y in zip(design, response, strict=True)) for j in range(p))
    beta = tuple(fsum(v * b for v, b in zip(row, rhs, strict=True)) for row in precision)
    sse = fsum(
        (y - fsum(x * b for x, b in zip(row, beta, strict=True))) ** 2
        for row, y in zip(design, response, strict=True)
    )
    sigma = sse / (n - p)
    return tuple(tuple(sigma * v for v in row) for row in precision), sigma


def prediction_variance(
    x: tuple[float, ...], covariance: tuple[tuple[float, ...], ...]
) -> float:
    return fsum(x[i] * covariance[i][j] * x[j] for i in range(len(x)) for j in range(len(x)))

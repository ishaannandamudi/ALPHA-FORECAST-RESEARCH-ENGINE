"""Independent offline causal fixtures."""

import math


def mean(values: tuple[float, ...]) -> float:
    return math.fsum(values) / len(values)


def variance(values: tuple[float, ...]) -> float:
    center = mean(values)
    return math.fsum((v - center) ** 2 for v in values) / len(values)


def pearson(x: tuple[float, ...], y: tuple[float, ...]) -> float:
    a, b = mean(x), mean(y)
    xx, yy = math.fsum((v - a) ** 2 for v in x), math.fsum((v - b) ** 2 for v in y)
    return math.fsum((v - a) * (w - b) for v, w in zip(x, y, strict=True)) / math.sqrt(xx * yy)


def ranks(values: tuple[float, ...]) -> tuple[float, ...]:
    return tuple(
        1.0 + sum(w < v for w in values) + (sum(w == v for w in values) - 1) / 2 for v in values
    )


def spearman(x: tuple[float, ...], y: tuple[float, ...]) -> float:
    return pearson(ranks(x), ranks(y))


def ols(
    x: tuple[tuple[float, ...], ...], y: tuple[float, ...], intercept: bool = True
) -> tuple[float, ...]:
    design = tuple((1.0, *r) if intercept else r for r in x)
    width = len(design[0])
    a = [
        [math.fsum(r[i] * r[j] for r in design) for j in range(width)]
        + [math.fsum(r[i] * v for r, v in zip(design, y, strict=True))]
        for i in range(width)
    ]
    for k in range(width):
        pivot = max(range(k, width), key=lambda j: abs(a[j][k]))
        a[k], a[pivot] = a[pivot], a[k]
        denominator = a[k][k]
        assert abs(denominator) > 1e-14
        a[k] = [v / denominator for v in a[k]]
        for j in range(width):
            if j != k:
                scale = a[j][k]
                a[j] = [v - scale * w for v, w in zip(a[j], a[k], strict=True)]
    return tuple(r[-1] for r in a)


def predict(
    x: tuple[tuple[float, ...], ...], coefficients: tuple[float, ...], intercept: bool = True
) -> tuple[float, ...]:
    return tuple(
        math.fsum(
            a * b for a, b in zip((1.0, *r) if intercept else r, coefficients, strict=True)
        )
        for r in x
    )


def metrics(p: tuple[float, ...], y: tuple[float, ...]) -> tuple[float, float, float, float]:
    errors = tuple(a - b for a, b in zip(p, y, strict=True))
    mse = mean(tuple(v * v for v in errors))
    return mse, math.sqrt(mse), mean(tuple(abs(v) for v in errors)), 1 - mse / variance(y)

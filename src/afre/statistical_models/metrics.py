"""Point metrics and per-origin IC with explicit zero-variance/tie conventions."""

import math

from afre.schema import require
from afre.statistical_models.artifacts import PointMetric
from afre.statistical_models.linear_algebra import dot, finite, total
from afre.statistical_models.schema import MetricName, MetricState


def ranks(values: tuple[float, ...]) -> tuple[float, ...]:
    ordered = sorted(range(len(values)), key=lambda i: (values[i], i))
    result = [0.0] * len(values)
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and values[ordered[end]] == values[ordered[start]]:
            end += 1
        average = (start + 1 + end) / 2
        for index in ordered[start:end]:
            result[index] = average
        start = end
    return tuple(result)


def correlation(
    predictions: tuple[float, ...],
    truths: tuple[float, ...],
    name: MetricName = MetricName.PEARSON_CORRELATION,
) -> PointMetric:
    require(len(predictions) == len(truths), "correlation shape mismatch")
    for value in (*predictions, *truths):
        finite(value)
    n = len(truths)
    if n < 2:
        return PointMetric(name, None, MetricState.INSUFFICIENT_OBSERVATIONS, n)
    if min(truths) == max(truths):
        return PointMetric(name, None, MetricState.CONSTANT_TARGET, n)
    if min(predictions) == max(predictions):
        return PointMetric(name, None, MetricState.CONSTANT_PREDICTION, n)
    if name is MetricName.SPEARMAN_CORRELATION:
        predictions, truths = ranks(predictions), ranks(truths)
    mean_p, mean_y = total(list(predictions)) / n, total(list(truths)) / n
    p = tuple(finite(v - mean_p) for v in predictions)
    y = tuple(finite(v - mean_y) for v in truths)
    p_norm, y_norm = finite(math.hypot(*p)), finite(math.hypot(*y))
    if y_norm == 0:
        return PointMetric(name, None, MetricState.CONSTANT_TARGET, n)
    if p_norm == 0:
        return PointMetric(name, None, MetricState.CONSTANT_PREDICTION, n)
    value = dot(tuple(v / p_norm for v in p), tuple(v / y_norm for v in y))
    return PointMetric(name, max(-1.0, min(1.0, value)), MetricState.AVAILABLE, n)


def point_metrics(
    predictions: tuple[float, ...], truths: tuple[float, ...]
) -> tuple[PointMetric, ...]:
    require(len(predictions) == len(truths), "metric shape mismatch")
    for value in (*predictions, *truths):
        finite(value)
    n = len(truths)
    if not n:
        return tuple(
            PointMetric(
                name,
                0.0 if name is MetricName.COUNT else None,
                MetricState.AVAILABLE
                if name is MetricName.COUNT
                else MetricState.INSUFFICIENT_OBSERVATIONS,
                0,
            )
            for name in MetricName
        )
    errors = tuple(finite(p - y) for p, y in zip(predictions, truths, strict=True))
    sse = dot(errors, errors)
    mean = total(list(truths)) / n
    centered = tuple(finite(y - mean) for y in truths)
    sst = 0.0 if min(truths) == max(truths) else dot(centered, centered)
    values = {
        MetricName.COUNT: float(n),
        MetricName.MEAN_ERROR: finite(total(list(errors)) / n),
        MetricName.MAE: finite(total([abs(e) for e in errors]) / n),
        MetricName.MSE: finite(sse / n),
        MetricName.RMSE: finite(math.sqrt(sse / n)),
        MetricName.DIRECTIONAL_ACCURACY: sum(
            (p > 0) - (p < 0) == (y > 0) - (y < 0)
            for p, y in zip(predictions, truths, strict=True)
        )
        / n,
    }
    results = [
        PointMetric(name, value, MetricState.AVAILABLE, n) for name, value in values.items()
    ]
    results.append(
        PointMetric(
            MetricName.R_SQUARED,
            finite(1 - sse / sst) if sst > 0 else None,
            MetricState.AVAILABLE if sst > 0 else MetricState.CONSTANT_TARGET,
            n,
        )
    )
    results.extend(
        correlation(predictions, truths, name)
        for name in (MetricName.PEARSON_CORRELATION, MetricName.SPEARMAN_CORRELATION)
    )
    return tuple(sorted(results, key=lambda m: m.name.value))

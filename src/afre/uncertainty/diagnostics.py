"""Deterministic descriptive error, buckets and known-window drift; no refit or selection."""

from typing import TYPE_CHECKING

from afre.schema import require
from afre.statistical_models.artifacts import PointMetric
from afre.statistical_models.linear_algebra import finite, total
from afre.statistical_models.metrics import correlation
from afre.statistical_models.schema import MetricName, MetricState
from afre.uncertainty.artifacts import ForecastUncertaintyDecomposition
from afre.uncertainty.evaluation_artifacts import (
    UncertaintyBucket,
    UncertaintyDrift,
    UncertaintyErrorDiagnostic,
    UncertaintyEvaluation,
    UncertaintyEvaluationPair,
)
from afre.uncertainty.schema import IdentifiabilityStatus as Status

if TYPE_CHECKING:
    from afre.uncertainty.repository import UncertaintyRepository


def buckets_for(
    pairs: tuple[UncertaintyEvaluationPair, ...], count: int, minimum: int
) -> tuple[UncertaintyBucket, ...]:
    require(
        1 <= count <= 20 and 2 <= minimum <= 2000 and len(pairs) <= 2000,
        "uncertainty bucket bounds",
    )
    ordered = tuple(
        sorted(
            (p for p in pairs if p.variance is not None),
            key=lambda p: (p.variance, p.sample_id),
        )
    )
    groups: dict[int, list[UncertaintyEvaluationPair]] = {}
    for index, pair in enumerate(ordered):
        groups.setdefault(index * min(count, len(ordered)) // len(ordered), []).append(pair)
    result = []
    for index, rows in sorted(groups.items()):
        values = tuple(p.variance for p in rows if p.variance is not None)
        errors = tuple(finite(p.truth - p.prediction) for p in rows)
        sufficient = len(rows) >= minimum
        result.append(
            UncertaintyBucket(
                index,
                tuple(p.sample_id for p in rows),
                min(values),
                max(values),
                total(list(values)) / len(values),
                total([abs(e) for e in errors]) / len(errors) if sufficient else None,
                total([finite(e * e) for e in errors]) / len(errors) if sufficient else None,
                Status.IDENTIFIED if sufficient else Status.INSUFFICIENT_DATA,
            )
        )
    return tuple(result)


def error_for(
    pairs: tuple[UncertaintyEvaluationPair, ...],
    buckets: tuple[UncertaintyBucket, ...],
    minimum: int,
) -> UncertaintyErrorDiagnostic:
    rows = tuple(p for p in pairs if p.variance is not None)
    variances = tuple(p.variance for p in rows if p.variance is not None)
    absolute = tuple(abs(finite(p.truth - p.prediction)) for p in rows)
    squared = tuple(finite(v * v) for v in absolute)

    def metric(values: tuple[float, ...], name: MetricName) -> PointMetric:
        return (
            correlation(variances, values, name)
            if len(rows) >= minimum
            else PointMetric(name, None, MetricState.INSUFFICIENT_OBSERVATIONS, len(rows))
        )

    errors = tuple(b.mean_absolute_error for b in buckets)
    monotonic = (
        all(
            a <= b
            for a, b in zip(
                tuple(v for v in errors if v is not None),
                tuple(v for v in errors[1:] if v is not None),
                strict=False,
            )
        )
        if len(errors) >= 2 and all(v is not None for v in errors)
        else None
    )
    return UncertaintyErrorDiagnostic(
        tuple(p.sample_id for p in rows),
        metric(absolute, MetricName.PEARSON_CORRELATION),
        metric(absolute, MetricName.SPEARMAN_CORRELATION),
        metric(squared, MetricName.PEARSON_CORRELATION),
        metric(squared, MetricName.SPEARMAN_CORRELATION),
        monotonic,
    )


def drift_for(
    repo: "UncertaintyRepository", ids: tuple[str, ...], available_ns: int
) -> UncertaintyDrift:
    require(
        2 <= len(ids) <= repo.uncertainty_bounds.drift_windows and len(set(ids)) == len(ids),
        "uncertainty drift window bounds",
    )
    evaluations = tuple(repo.resolve(UncertaintyEvaluation, i) for i in ids)
    first = evaluations[0]
    windows, shares = [], []
    for evaluation in evaluations:
        require(
            (
                evaluation.target_definition_id,
                evaluation.horizon_id,
                evaluation.fold_id,
                evaluation.interval_levels,
            )
            == (
                first.target_definition_id,
                first.horizon_id,
                first.fold_id,
                first.interval_levels,
            )
            and available_ns >= evaluation.available_ns,
            "uncertainty drift compatibility/availability",
        )
        decompositions = tuple(
            repo.resolve(ForecastUncertaintyDecomposition, i)
            for i in evaluation.decomposition_ids
        )
        times = tuple(d.origin.timestamp_ns for d in decompositions)
        windows.append((min(times), max(times)))
        kinds = sorted({kind.value for d in decompositions for kind, _ in d.shares})
        current = []
        for kind in kinds:
            values = tuple(v for d in decompositions for t, v in d.shares if t.value == kind)
            current.append(
                (
                    kind,
                    total([v for v in values if v is not None]) / len(values)
                    if values and all(v is not None for v in values)
                    else None,
                )
            )
        shares.append(tuple(current))
    require(
        all(a[1] < b[0] for a, b in zip(windows, windows[1:], strict=False)),
        "drift windows must be ordered and disjoint",
    )
    variances = tuple(e.coverage.mean_variance for e in evaluations)
    shifts = tuple(
        finite(b - a) if a is not None and b is not None else None
        for a, b in zip(variances, variances[1:], strict=False)
    )
    return UncertaintyDrift(
        ids,
        variances,
        shifts,
        tuple(e.coverage.coverage_error for e in evaluations),
        tuple(e.error_diagnostic.absolute_pearson.value for e in evaluations),
        tuple(shares),
        available_ns,
    )

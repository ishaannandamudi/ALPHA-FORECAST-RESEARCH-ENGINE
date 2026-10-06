"""Held-out exact intersections; no fit, selection, tuning or automatic acceptance."""

from typing import TYPE_CHECKING

from afre.orthogonalization.alignment import validate_cross_sectional_grid
from afre.orthogonalization.artifacts import (
    AlignedSignalRow,
    OrthogonalSignalValue,
    ProjectionArtifact,
)
from afre.orthogonalization.definitions import OrthogonalizationSpec
from afre.orthogonalization.evaluation_artifacts import (
    PredictiveModelPair,
    RedundancyEvaluation,
)
from afre.orthogonalization.projection import numeric, population_variance, transform
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.research_datasets.splits import TestEvaluation
from afre.schema import require
from afre.statistical_models.artifacts import PointMetric
from afre.statistical_models.linear_algebra import dot, finite
from afre.statistical_models.metrics import correlation, point_metrics
from afre.statistical_models.schema import MetricName
from afre.target_engine.models import TargetVintage
from afre.target_engine.validation import target_known_by_cutoff

if TYPE_CHECKING:
    from afre.orthogonalization.repository import OrthogonalizationRepository


def metric_delta(
    base: tuple[PointMetric, ...], augmented: tuple[PointMetric, ...]
) -> tuple[PointMetric, ...]:
    names = (
        MetricName.MSE,
        MetricName.RMSE,
        MetricName.MAE,
        MetricName.R_SQUARED,
        MetricName.PEARSON_CORRELATION,
    )
    b = {m.name: m for m in base}
    a = {m.name: m for m in augmented}
    return tuple(
        PointMetric(
            n,
            finite(numeric(a[n].value) - numeric(b[n].value))
            if a[n].value is not None and b[n].value is not None
            else None,
            a[n].state if a[n].value is None else b[n].state,
            a[n].sample_count,
        )
        for n in names
    )


def evaluation_for(
    repo: "OrthogonalizationRepository",
    ids: tuple[str, ...],
    cutoff_ns: int,
    available_ns: int,
    pair_id: str | None,
    target_diagnostics: bool,
    seal: TestEvaluation | None,
) -> RedundancyEvaluation:
    require(
        0 < len(ids) <= repo.orthogonalization_bounds.rows and len(set(ids)) == len(ids),
        "evaluation residual count/duplicates",
    )
    residuals = tuple(repo.resolve(OrthogonalSignalValue, i) for i in ids)
    rows = tuple(repo.resolve(AlignedSignalRow, v.row_id) for v in residuals)
    require(
        len({r.sample_id for r in rows}) == len(rows)
        and all(r.partition is rows[0].partition and r.spec_id == rows[0].spec_id for r in rows)
        and rows[0].partition in (Partition.VALIDATION, Partition.TEST),
        "held-out exact spec/fold/partition/intersection",
    )
    validate_cross_sectional_grid(repo, rows)
    model = repo.resolve(ProjectionArtifact, residuals[0].projection_id)
    spec = repo.resolve(OrthogonalizationSpec, model.spec_id)
    require(
        all(
            v.projection_id == model.fingerprint and v.available_ns <= cutoff_ns
            for v in residuals
        )
        and available_ns >= cutoff_ns,
        "evaluation frozen projection/availability",
    )
    require((seal is not None) == (rows[0].partition is Partition.TEST), "TEST evaluation seal")
    if seal:
        require(
            seal.fold_id == spec.fold_id
            and seal.evaluated_ns == cutoff_ns
            and all(r.sample_id in seal.sample_ids for r in rows),
            "exact TEST sample/cutoff seal",
        )
    available = tuple(
        sorted(
            ((v, r) for v, r in zip(residuals, rows, strict=True) if v.residual is not None),
            key=lambda z: z[1].sample_id,
        )
    )
    candidate = tuple(numeric(v.raw_candidate) for v, _ in available)
    predicted = tuple(numeric(v.projected) for v, _ in available)
    remaining = tuple(numeric(v.residual) for v, _ in available)
    xs = tuple(
        transform(tuple(numeric(a) for a in r.references), model.centers, model.scales)
        for _, r in available
    )
    cv, rv = population_variance(candidate), population_variance(remaining)
    ratio = finite(rv / cv) if cv is not None and rv is not None and cv > 0 else None
    raw_corr = tuple(
        correlation(candidate, tuple(x[j] for x in xs)) for j in range(len(spec.references))
    )
    res_corr = tuple(
        correlation(remaining, tuple(x[j] for x in xs)) for j in range(len(spec.references))
    )
    targets = []
    if target_diagnostics or pair_id:
        for _, row in available:
            sample = repo.resolve(ResearchSample, row.sample_id)
            require(sample.target_id is not None, "evaluation known exact target required")
            assert sample.target_id is not None
            t = repo.resolve(TargetVintage, sample.target_id)
            require(
                target_known_by_cutoff(t, cutoff_ns)
                and t.origin == row.origin
                and t.definition == spec.target,
                "evaluation exact known target/horizon",
            )
            targets.append(t)
    y = tuple(numeric(t.value) for t in targets)
    base_metrics: tuple[PointMetric, ...] = ()
    aug_metrics: tuple[PointMetric, ...] = ()
    deltas: tuple[PointMetric, ...] = ()
    partial: tuple[PointMetric, ...] = ()
    if pair_id:
        require(bool(available), "incremental evaluation requires complete samples")
        pair = repo.resolve(PredictiveModelPair, pair_id)
        require(
            pair.projection_id == model.fingerprint
            and pair.available_ns <= min(r.origin.availability_cutoff_ns for _, r in available),
            "incremental exact causal target models",
        )
        base = tuple(finite(pair.base_intercept + dot(x, pair.base_coefficients)) for x in xs)
        augmented = tuple(
            finite(pair.augmented_intercept + dot((*x, extra), pair.augmented_coefficients))
            for x, extra in zip(
                xs, remaining if pair.augmented_uses_residual else candidate, strict=True
            )
        )
        base_metrics, aug_metrics = point_metrics(base, y), point_metrics(augmented, y)
        deltas = metric_delta(base_metrics, aug_metrics)
        target_residual = tuple(finite(a - b) for a, b in zip(y, base, strict=True))
        partial = tuple(
            correlation(remaining, target_residual, n)
            for n in (MetricName.PEARSON_CORRELATION, MetricName.SPEARMAN_CORRELATION)
        )
    raw_truth = (
        tuple(
            correlation(candidate, y, n)
            for n in (MetricName.PEARSON_CORRELATION, MetricName.SPEARMAN_CORRELATION)
        )
        if targets
        else ()
    )
    res_truth = (
        tuple(
            correlation(remaining, y, n)
            for n in (MetricName.PEARSON_CORRELATION, MetricName.SPEARMAN_CORRELATION)
        )
        if targets
        else ()
    )
    times = sorted({r.origin.timestamp_ns for _, r in available})
    ics = []
    if targets:
        for at in times:
            indexes = tuple(
                i for i, (_, r) in enumerate(available) if r.origin.timestamp_ns == at
            )
            ics.append(
                (
                    at,
                    correlation(
                        tuple(candidate[i] for i in indexes),
                        tuple(y[i] for i in indexes),
                        MetricName.SPEARMAN_CORRELATION,
                    ),
                    correlation(
                        tuple(remaining[i] for i in indexes),
                        tuple(y[i] for i in indexes),
                        MetricName.SPEARMAN_CORRELATION,
                    ),
                )
            )
    return RedundancyEvaluation(
        model.fingerprint,
        tuple(
            v.fingerprint
            for v, r in sorted(zip(residuals, rows, strict=True), key=lambda z: z[1].sample_id)
        ),
        tuple(r.sample_id for _, r in available),
        rows[0].partition,
        point_metrics(predicted, candidate),
        cv,
        rv,
        ratio,
        1 - ratio if ratio is not None else None,
        raw_corr,
        res_corr,
        pair_id,
        tuple(t.fingerprint for t in targets),
        y,
        base_metrics,
        aug_metrics,
        deltas,
        raw_truth,
        res_truth,
        partial,
        tuple(ics),
        cutoff_ns,
        available_ns,
        seal.fingerprint if seal else None,
    )

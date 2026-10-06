"""TRAIN-only candidate-on-reference QR; explicit preprocessing and stable condition gate."""

import math
from typing import TYPE_CHECKING

from afre.orthogonalization.alignment import complete, rows_for, validate_cross_sectional_grid
from afre.orthogonalization.artifacts import ProjectionArtifact, RedundancyMatrix
from afre.orthogonalization.definitions import OrthogonalizationSpec
from afre.orthogonalization.schema import ProjectionIntercept, ProjectionPreprocessing
from afre.research_datasets.schema import Partition
from afre.schema import ContractError, require
from afre.statistical_models.linear_algebra import dot, finite, householder_qr, total
from afre.statistical_models.metrics import point_metrics
from afre.uncertainty.covariance import inverse_crossproduct

if TYPE_CHECKING:
    from afre.orthogonalization.repository import OrthogonalizationRepository


def numeric(value: float | None) -> float:
    require(value is not None, "missing scalar cannot become numerical zero")
    assert value is not None
    return value


def population_variance(values: tuple[float, ...]) -> float | None:
    if not values:
        return None
    mean = total(list(values)) / len(values)
    return dot(
        tuple(finite(v - mean) for v in values), tuple(finite(v - mean) for v in values)
    ) / len(values)


def transform(
    values: tuple[float, ...], centers: tuple[float, ...], scales: tuple[float, ...]
) -> tuple[float, ...]:
    return tuple(finite((v - c) / s) for v, c, s in zip(values, centers, scales, strict=True))


def solve(
    spec: OrthogonalizationSpec, x: tuple[tuple[float, ...], ...], y: tuple[float, ...]
) -> tuple[float, tuple[float, ...], int, float]:
    intercept = spec.intercept is ProjectionIntercept.WITH_INTERCEPT
    design = tuple((1.0, *r) if intercept else r for r in x)
    result = householder_qr(design, y, spec.tolerance, spec.condition_limit)
    _, condition = inverse_crossproduct(design, spec.tolerance, spec.condition_limit)
    condition = max(1.0, condition)
    return (
        (result.coefficients[0], result.coefficients[1:], result.rank, condition)
        if intercept
        else (0.0, result.coefficients, result.rank, condition)
    )


def vif_for(
    x: tuple[tuple[float, ...], ...], spec: OrthogonalizationSpec
) -> tuple[float | None, ...]:
    values: list[float | None] = []
    # VIF is the conventional centered auxiliary regression, independent of primary intercept.
    from dataclasses import replace

    policy = replace(spec, intercept=ProjectionIntercept.WITH_INTERCEPT)
    for j in range(len(x[0])):
        y = tuple(r[j] for r in x)
        variance = population_variance(y)
        assert variance is not None
        if variance == 0:
            values.append(None)
            continue
        if len(x[0]) == 1:
            values.append(1.0)
            continue
        controls = tuple(tuple(v for k, v in enumerate(r) if k != j) for r in x)
        try:
            intercept, beta, _, _ = solve(policy, controls, y)
        except ContractError:
            values.append(None)
            continue
        residual = tuple(
            finite(v - intercept - dot(r, beta)) for r, v in zip(controls, y, strict=True)
        )
        denominator = dot(residual, residual)
        values.append(
            finite(len(y) * variance / denominator)
            if denominator > spec.tolerance * len(y) * variance
            else None
        )
    return tuple(values)


def projection_for(
    repo: "OrthogonalizationRepository",
    spec: OrthogonalizationSpec,
    ids: tuple[str, ...],
    matrix_id: str,
    computed_ns: int,
    matrix: RedundancyMatrix | None = None,
) -> ProjectionArtifact:
    rows = rows_for(repo, spec.fingerprint, ids)
    validate_cross_sectional_grid(repo, rows)
    matrix = matrix or repo.resolve(RedundancyMatrix, matrix_id)
    require(
        matrix.fingerprint == matrix_id
        and matrix.spec_id == spec.fingerprint
        and set(matrix.row_ids) == set(ids)
        and matrix.partition is Partition.TRAIN
        and matrix.available_ns <= computed_ns,
        "projection exact TRAIN matrix",
    )
    require(
        all(
            r.partition is Partition.TRAIN
            and r.origin.timestamp_ns < spec.cutoff_ns
            and r.available_ns <= spec.cutoff_ns
            for r in rows
        ),
        "projection only admitted causal TRAIN signals",
    )
    require(
        all(complete(r) for r in rows),
        "projection missing candidate/reference; no implicit imputation",
    )
    require(
        computed_ns >= spec.cutoff_ns
        and len(rows)
        >= max(
            spec.minimum_samples,
            len(spec.references)
            + int(spec.intercept is ProjectionIntercept.WITH_INTERCEPT)
            + 1,
        ),
        "projection positive support/degrees and fit clock",
    )
    require(
        len(spec.references) <= repo.orthogonalization_bounds.references
        and len(rows) * (len(spec.references) + 1) ** 2 <= repo.orthogonalization_bounds.cells,
        "projection dimension/work bound",
    )
    x = tuple(tuple(numeric(v) for v in r.references) for r in rows)
    y = tuple(numeric(r.candidate) for r in rows)
    centers = (0.0,) * len(spec.references)
    scales = (1.0,) * len(spec.references)
    if spec.preprocessing is ProjectionPreprocessing.TRAIN_STANDARDIZE:
        centers = tuple(total([r[j] for r in x]) / len(x) for j in range(len(x[0])))
        scales = tuple(
            finite(math.sqrt(population_variance(tuple(r[j] for r in x)) or 0))
            for j in range(len(x[0]))
        )
        require(all(s > 0 for s in scales), "constant TRAIN reference cannot standardize")
    design = tuple(transform(r, centers, scales) for r in x)
    intercept, beta, rank, condition = solve(spec, design, y)
    predictions = tuple(finite(intercept + dot(r, beta)) for r in design)
    residual = tuple(finite(a - b) for a, b in zip(y, predictions, strict=True))
    return ProjectionArtifact(
        spec.fingerprint,
        tuple(r.fingerprint for r in rows),
        tuple(r.sample_id for r in rows),
        y,
        tuple(r.fingerprint for r in spec.references),
        centers,
        scales,
        beta,
        intercept,
        rank,
        condition,
        point_metrics(predictions, y),
        population_variance(residual) or 0.0,
        vif_for(design, spec),
        matrix_id,
        spec.cutoff_ns,
        computed_ns,
        computed_ns,
    )

"""Partial association through separately TRAIN-fitted matched residuals, not inversion."""

from typing import TYPE_CHECKING

from afre.orthogonalization.artifacts import OrthogonalSignalValue, ProjectionArtifact
from afre.orthogonalization.definitions import OrthogonalizationSpec
from afre.orthogonalization.evaluation_artifacts import PartialCorrelation
from afre.orthogonalization.projection import numeric
from afre.schema import require
from afre.statistical_models.metrics import correlation
from afre.statistical_models.schema import MetricName

if TYPE_CHECKING:
    from afre.orthogonalization.repository import OrthogonalizationRepository


def partial_for(
    repo: "OrthogonalizationRepository",
    left_ids: tuple[str, ...],
    right_ids: tuple[str, ...],
    available_ns: int,
) -> PartialCorrelation:
    require(
        0 < len(left_ids) == len(right_ids) <= repo.orthogonalization_bounds.rows
        and len(set(left_ids)) == len(left_ids)
        and len(set(right_ids)) == len(right_ids),
        "partial correlation bounds/intersection",
    )
    left = tuple(repo.resolve(OrthogonalSignalValue, i) for i in left_ids)
    right = tuple(repo.resolve(OrthogonalSignalValue, i) for i in right_ids)
    lp = repo.resolve(ProjectionArtifact, left[0].projection_id)
    rp = repo.resolve(ProjectionArtifact, right[0].projection_id)
    ls = repo.resolve(OrthogonalizationSpec, lp.spec_id)
    rs = repo.resolve(OrthogonalizationSpec, rp.spec_id)
    require(
        (
            ls.references,
            ls.fold_id,
            ls.target,
            ls.mode,
            ls.intercept,
            ls.preprocessing,
            ls.cutoff_ns,
        )
        == (
            rs.references,
            rs.fold_id,
            rs.target,
            rs.mode,
            rs.intercept,
            rs.preprocessing,
            rs.cutoff_ns,
        ),
        "partial exact common controls/fold/target/mode",
    )
    a = {v.sample_id: v for v in left}
    b = {v.sample_id: v for v in right}
    require(
        len(a) == len(left)
        and set(a) == set(b)
        and all(
            a[k].origin == b[k].origin
            and a[k].projection_id == lp.fingerprint
            and b[k].projection_id == rp.fingerprint
            and a[k].residual is not None
            and b[k].residual is not None
            for k in a
        ),
        "partial exact sample/origin/nonmissing frozen models",
    )
    require(
        available_ns >= max(v.available_ns for v in (*left, *right)), "partial availability"
    )
    samples = tuple(sorted(a))
    x = tuple(numeric(a[k].residual) for k in samples)
    y = tuple(numeric(b[k].residual) for k in samples)
    return PartialCorrelation(
        tuple(a[k].fingerprint for k in samples),
        tuple(b[k].fingerprint for k in samples),
        samples,
        correlation(x, y),
        correlation(x, y, MetricName.SPEARMAN_CORRELATION),
        available_ns,
    )

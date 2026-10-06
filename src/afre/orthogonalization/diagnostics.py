"""Compatible known-window summaries cannot refit, prune or promote signals."""

from typing import TYPE_CHECKING

from afre.orthogonalization.artifacts import (
    AlignedSignalRow,
    OrthogonalSignalValue,
    ProjectionArtifact,
)
from afre.orthogonalization.definitions import OrthogonalizationSpec
from afre.orthogonalization.evaluation_artifacts import (
    RedundancyEvaluation,
    RedundancyStability,
)
from afre.schema import require

if TYPE_CHECKING:
    from afre.orthogonalization.repository import OrthogonalizationRepository


def stability_for(
    repo: "OrthogonalizationRepository", ids: tuple[str, ...], available_ns: int
) -> RedundancyStability:
    require(
        2 <= len(ids) <= repo.orthogonalization_bounds.windows and len(set(ids)) == len(ids),
        "stability window count",
    )
    values = tuple(repo.resolve(RedundancyEvaluation, i) for i in ids)
    models = tuple(repo.resolve(ProjectionArtifact, e.projection_id) for e in values)
    specs = tuple(repo.resolve(OrthogonalizationSpec, m.spec_id) for m in models)
    first = specs[0]
    require(
        all(
            (s.candidate, s.references, s.target, s.mode, s.intercept)
            == (first.candidate, first.references, first.target, first.mode, first.intercept)
            for s in specs
        )
        and available_ns >= max(e.available_ns for e in values),
        "stability exact compatible supplied signals/units/target",
    )
    windows = []
    for e in values:
        rows = tuple(
            repo.resolve(AlignedSignalRow, repo.resolve(OrthogonalSignalValue, i).row_id)
            for i in e.residual_ids
        )
        windows.append(
            (min(r.origin.timestamp_ns for r in rows), max(r.origin.timestamp_ns for r in rows))
        )
    require(
        all(a[1] < b[0] for a, b in zip(windows, windows[1:], strict=False)),
        "stability ordered disjoint origin windows",
    )
    raw_coefficients = tuple(
        (
            m.intercept
            - sum(
                b * c / z for b, c, z in zip(m.coefficients, m.centers, m.scales, strict=True)
            ),
            *(b / z for b, z in zip(m.coefficients, m.scales, strict=True)),
        )
        for m in models
    )
    ranges = tuple(
        (min(r[j] for r in raw_coefficients), max(r[j] for r in raw_coefficients))
        for j in range(len(raw_coefficients[0]))
    )
    return RedundancyStability(
        ids,
        ranges,
        tuple(e.residual_variance_ratio for e in values),
        tuple(tuple(c.value for c in e.raw_reference_correlations) for e in values),
        available_ns,
    )

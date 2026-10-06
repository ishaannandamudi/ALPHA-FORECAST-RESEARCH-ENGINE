"""Common-intersection Pearson/Spearman matrices with native undefined states."""

from typing import TYPE_CHECKING

from afre.orthogonalization.alignment import complete, rows_for
from afre.orthogonalization.artifacts import RedundancyMatrix
from afre.orthogonalization.projection import numeric
from afre.schema import require
from afre.statistical_models.metrics import correlation
from afre.statistical_models.schema import MetricName

if TYPE_CHECKING:
    from afre.orthogonalization.repository import OrthogonalizationRepository


def matrix_for(
    repo: "OrthogonalizationRepository", spec_id: str, ids: tuple[str, ...], available_ns: int
) -> RedundancyMatrix:
    rows = rows_for(repo, spec_id, ids)
    require(
        all(r.partition is rows[0].partition for r in rows)
        and available_ns >= max(r.available_ns for r in rows),
        "matrix partition/availability agreement",
    )
    admitted = tuple(r for r in rows if complete(r))
    width = len(rows[0].references) + 1
    require(
        width <= repo.orthogonalization_bounds.references + 1
        and len(rows) * width * width <= repo.orthogonalization_bounds.cells,
        "correlation matrix work bound",
    )
    columns = tuple(
        tuple(numeric((r.candidate, *r.references)[j]) for r in admitted) for j in range(width)
    )
    matrices = tuple(
        tuple(tuple(correlation(a, b, name) for b in columns) for a in columns)
        for name in (MetricName.PEARSON_CORRELATION, MetricName.SPEARMAN_CORRELATION)
    )
    return RedundancyMatrix(
        spec_id,
        ids,
        tuple(r.sample_id for r in admitted),
        tuple(r.sample_id for r in rows if not complete(r)),
        rows[0].partition,
        matrices[0],
        matrices[1],
        available_ns,
    )

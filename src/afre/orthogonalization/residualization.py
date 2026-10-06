"""Feature-only application of frozen TRAIN projection; missing never means zero."""

from typing import TYPE_CHECKING

from afre.orthogonalization.alignment import complete
from afre.orthogonalization.artifacts import (
    AlignedSignalRow,
    OrthogonalSignalValue,
    ProjectionArtifact,
)
from afre.orthogonalization.definitions import OrthogonalizationSpec
from afre.orthogonalization.projection import numeric, transform
from afre.orthogonalization.schema import OrthogonalQuality
from afre.schema import require
from afre.statistical_models.linear_algebra import dot, finite

if TYPE_CHECKING:
    from afre.orthogonalization.repository import OrthogonalizationRepository


def residual_for(
    repo: "OrthogonalizationRepository", projection_id: str, row_id: str, computed_ns: int
) -> OrthogonalSignalValue:
    require(
        repo._feature_only_depth > 0, "residual application requires feature-only read guard"
    )
    model = repo.resolve(ProjectionArtifact, projection_id)
    row = repo.resolve(AlignedSignalRow, row_id)
    spec = repo.resolve(OrthogonalizationSpec, model.spec_id)
    require(
        row.spec_id == model.spec_id
        and computed_ns >= max(row.available_ns, model.available_ns),
        "residual exact spec/model/source availability",
    )
    projected = residual = raw = None
    if complete(row):
        raw = row.candidate
        assert raw is not None
        values = transform(
            tuple(numeric(v) for v in row.references), model.centers, model.scales
        )
        projected = finite(model.intercept + dot(values, model.coefficients))
        residual = finite(raw - projected)
    return OrthogonalSignalValue(
        model.fingerprint,
        row.fingerprint,
        row.sample_id,
        row.origin,
        raw,
        projected,
        residual,
        spec.candidate.unit,
        OrthogonalQuality.AVAILABLE if residual is not None else OrthogonalQuality.MISSING,
        computed_ns,
        computed_ns,
    )

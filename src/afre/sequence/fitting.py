"""Reuse AFRE-5 QR; dynamics are supplied, only the bounded readout is learned."""

import math
from typing import TYPE_CHECKING

from afre.schema import require
from afre.sequence.artifacts import (
    SequenceDataset,
    SequenceModelArtifact,
    SequenceSnapshot,
    SequenceTransformArtifact,
)
from afre.sequence.definitions import SequenceModelSpec
from afre.sequence.models import temporal_features
from afre.statistical_models.linear_algebra import dot, finite, householder_qr

if TYPE_CHECKING:
    from afre.sequence.repository import SequenceRepository


def fit_model(
    repo: "SequenceRepository",
    spec: SequenceModelSpec,
    dataset: SequenceDataset,
    started_ns: int,
    completed_ns: int,
    available_ns: int,
) -> SequenceModelArtifact:
    require(
        dataset.spec_id == spec.fingerprint and dataset.computed_ns <= started_ns,
        "sequence fit exact dataset/computation",
    )
    state = repo.resolve(SequenceTransformArtifact, dataset.transform_id)
    x = tuple(
        temporal_features(spec, repo.resolve(SequenceSnapshot, r.snapshot_id), state)[0]
        for r in dataset.rows
    )
    y = tuple(r.response for r in dataset.rows)
    width = len(spec.features)
    require(
        len(x) <= repo.sequence_bounds.training_rows
        and len(x) * width <= repo.sequence_bounds.work_cells,
        "sequence fit bounds",
    )
    design = tuple((1.0, *row) for row in x)
    response = y
    if spec.ridge_penalty > 0:
        penalty = finite(math.sqrt(spec.ridge_penalty))
        design = (
            *design,
            *(
                tuple(penalty if k == j else 0.0 for k in range(width + 1))
                for j in range(1, width + 1)
            ),
        )
        response = (*response, *((0.0,) * width))
    result = householder_qr(design, response, spec.tolerance, spec.condition_limit)
    intercept, coefficients = result.coefficients[0], result.coefficients[1:]
    residuals = tuple(
        finite(yv - intercept - dot(row, coefficients)) for row, yv in zip(x, y, strict=True)
    )
    return SequenceModelArtifact(
        spec.fingerprint,
        dataset.fingerprint,
        state.fingerprint,
        tuple(r.sample_id for r in dataset.rows),
        spec.family,
        intercept,
        coefficients,
        dot(residuals, residuals),
        result.rank,
        result.condition_proxy,
        1,
        "direct-QR-solved",
        spec.cutoff_ns,
        started_ns,
        completed_ns,
        available_ns,
    )

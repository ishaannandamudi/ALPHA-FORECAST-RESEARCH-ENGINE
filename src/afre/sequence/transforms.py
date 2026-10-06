"""TRAIN-only population normalization of unmasked tokens; no implicit zero scales."""

from statistics import pstdev
from typing import TYPE_CHECKING

from afre.schema import require
from afre.sequence.artifacts import SequenceTransformArtifact
from afre.sequence.datasets import training_bindings
from afre.sequence.definitions import SequenceModelSpec
from afre.sequence.schema import SequencePreprocessing
from afre.statistical_models.linear_algebra import finite, total

if TYPE_CHECKING:
    from afre.sequence.repository import SequenceRepository


def fit_transform(
    repo: "SequenceRepository",
    spec: SequenceModelSpec,
    bindings: tuple[tuple[str, str], ...],
    started_ns: int,
    completed_ns: int,
    available_ns: int,
) -> SequenceTransformArtifact:
    pairs = training_bindings(repo, spec, bindings)
    require(
        all(s.available_ns <= started_ns for _, s in pairs),
        "transform before actual snapshot construction",
    )
    columns = tuple(
        tuple(row[j] for _, snapshot in pairs for row in snapshot.values if row[j] is not None)
        for j in range(len(spec.features))
    )
    # The None filter is structural; masks have already been independently verified.
    numeric = tuple(tuple(v for v in c if v is not None) for c in columns)
    centers = (0.0,) * len(columns)
    scales = (1.0,) * len(columns)
    if spec.preprocessing is SequencePreprocessing.STANDARDIZE:
        centers = tuple(finite(total(c) / len(c)) for c in numeric)
        scales = tuple(finite(pstdev(c)) for c in numeric)
        require(
            all(s > 0 for s in scales), "zero TRAIN sequence scale; no implicit replacement"
        )
    return SequenceTransformArtifact(
        spec.fingerprint,
        bindings,
        centers,
        scales,
        tuple(len(c) for c in numeric),
        spec.cutoff_ns,
        started_ns,
        completed_ns,
        available_ns,
    )

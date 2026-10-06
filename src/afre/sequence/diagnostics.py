"""Descriptive compatible coefficient ranges and explicit window coverage; never refit."""

from collections import Counter
from typing import TYPE_CHECKING

from afre.schema import require
from afre.sequence.artifacts import (
    SequenceCoverage,
    SequenceModelArtifact,
    SequenceSnapshot,
    SequenceStability,
    SequenceTransformArtifact,
)
from afre.sequence.definitions import SequenceModelSpec
from afre.sequence.schema import SequenceCompleteness

if TYPE_CHECKING:
    from afre.sequence.repository import SequenceRepository


def stability_for(
    repo: "SequenceRepository", ids: tuple[str, ...], available_ns: int
) -> SequenceStability:
    require(
        2 <= len(ids) <= repo.sequence_bounds.forecasts and len(set(ids)) == len(ids),
        "sequence stability distinct model bounds",
    )
    models = tuple(repo.resolve(SequenceModelArtifact, i) for i in sorted(ids))
    specs = tuple(repo.resolve(SequenceModelSpec, m.spec_id) for m in models)
    first = specs[0]

    def signature(s: SequenceModelSpec) -> tuple[object, ...]:
        return (
            s.target,
            s.features,
            s.window,
            s.family,
            s.preprocessing,
            s.decay_rate_per_second,
            s.state_transition,
            s.state_input_gain,
        )

    require(
        all(signature(s) == signature(first) for s in specs)
        and all(m.available_ns <= available_ns for m in models),
        "compatible available sequence fits",
    )
    states = tuple(repo.resolve(SequenceTransformArtifact, m.transform_id) for m in models)
    ranges = tuple(
        (
            f.fingerprint,
            max(m.coefficients[j] / s.scales[j] for m, s in zip(models, states, strict=True))
            - min(m.coefficients[j] / s.scales[j] for m, s in zip(models, states, strict=True)),
        )
        for j, f in enumerate(first.features)
    )
    return SequenceStability(ids, ranges, available_ns)


def coverage_for(
    repo: "SequenceRepository", ids: tuple[str, ...], available_ns: int
) -> SequenceCoverage:
    require(
        0 < len(ids) <= repo.sequence_bounds.forecasts and len(set(ids)) == len(ids),
        "sequence coverage bounds/duplicates",
    )
    snapshots = tuple(repo.resolve(SequenceSnapshot, i) for i in ids)
    require(
        len({s.origin for s in snapshots}) == len(snapshots)
        and all(
            s.window_id == snapshots[0].window_id
            and s.feature_ids == snapshots[0].feature_ids
            and s.available_ns <= available_ns
            for s in snapshots
        ),
        "coverage exact unique origin grid",
    )
    counts = [("eligible_origins", len(snapshots))]
    counts.extend(
        (state.value, sum(s.completeness is state for s in snapshots))
        for state in SequenceCompleteness
    )
    excluded = Counter(reason for s in snapshots for _, reason in s.exclusions)
    return SequenceCoverage(ids, tuple(counts), tuple(sorted(excluded.items())), available_ns)

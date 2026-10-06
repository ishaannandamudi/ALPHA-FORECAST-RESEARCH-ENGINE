"""Exact complete AFRE-4 TRAIN bindings, known truth and temporal feature evidence."""

from typing import TYPE_CHECKING

from afre.nonlinear.artifacts import InteractionValue, ScalarInput
from afre.nonlinear.schema import ScalarSourceKind
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.schema import require
from afre.sequence.artifacts import (
    SequenceDataset,
    SequenceObservation,
    SequenceSnapshot,
    SequenceTrainingRow,
    SequenceTransformArtifact,
)
from afre.sequence.definitions import SequenceModelSpec
from afre.sequence.observations import source_attestors
from afre.sequence.schema import SequenceCompleteness
from afre.target_engine.models import TargetVintage
from afre.target_engine.validation import target_known_by_cutoff

if TYPE_CHECKING:
    from afre.sequence.repository import SequenceRepository


def validate_snapshot_input(
    repo: "SequenceRepository",
    spec: SequenceModelSpec,
    sample: ResearchSample,
    snapshot: SequenceSnapshot,
) -> Partition:
    require(
        not sample.dropped
        and sample.origin == snapshot.origin
        and sample.target_definition_id == spec.target.fingerprint
        and snapshot.feature_ids == tuple(f.fingerprint for f in spec.features)
        and snapshot.window_id == spec.window.fingerprint,
        "sequence exact sample/origin/features/window/target",
    )
    require(
        snapshot.completeness in (SequenceCompleteness.COMPLETE, SequenceCompleteness.PARTIAL)
        and all(n >= 1 for n in snapshot.effective_counts),
        "model needs effective history per feature",
    )
    for identity in {i for row in snapshot.observation_ids for i in row if i}:
        obs = repo.resolve(SequenceObservation, identity)
        require(
            set(source_attestors(repo, obs)) <= set(spec.approved_delivery_attestors),
            "unapproved sequence historical delivery",
        )
        source = repo.get_any(obs.source_id)
        scalars = (
            (source,)
            if isinstance(source, ScalarInput)
            else tuple(repo.resolve(ScalarInput, i) for i in source.input_ids)
            if isinstance(source, InteractionValue)
            else ()
        )
        for scalar in scalars:
            if scalar.definition.kind in (
                ScalarSourceKind.EXPERT_POINT,
                ScalarSourceKind.MIXTURE_POINT,
            ):
                require(
                    scalar.definition.source_key[-1] == spec.target.fingerprint,
                    "sequence expert target/horizon mismatch",
                )
    memberships = tuple(
        m for m in repo.fold_memberships(spec.fold_id) if m.sample_id == sample.fingerprint
    )
    require(len(memberships) == 1, "sequence exact fold membership")
    return memberships[0].partition


def training_bindings(
    repo: "SequenceRepository", spec: SequenceModelSpec, bindings: tuple[tuple[str, str], ...]
) -> tuple[tuple[ResearchSample, SequenceSnapshot], ...]:
    b = repo.sequence_bounds
    require(
        0 < len(bindings) <= b.training_rows
        and len({s for s, _ in bindings}) == len(bindings)
        and len(bindings) * len(spec.features) * spec.window.maximum_observations
        <= b.work_cells,
        "sequence TRAIN bounds/duplicates",
    )
    require(
        repo.resolve_fold(spec.fold_id).training_cutoff_ns == spec.cutoff_ns,
        "sequence exact training cutoff",
    )
    admitted = {
        s.fingerprint
        for s in repo.partition_samples(spec.fold_id, Partition.TRAIN)
        if s.target_definition_id == spec.target.fingerprint
    }
    require({s for s, _ in bindings} == admitted, "sequence requires exact complete TRAIN set")
    values = tuple(
        (repo.resolve(ResearchSample, s), repo.resolve(SequenceSnapshot, i))
        for s, i in sorted(bindings)
    )
    for sample, snapshot in values:
        require(
            validate_snapshot_input(repo, spec, sample, snapshot) is Partition.TRAIN,
            "sequence only TRAIN fits",
        )
    return values


def dataset_for(
    repo: "SequenceRepository",
    spec: SequenceModelSpec,
    state: SequenceTransformArtifact,
    computed_ns: int,
) -> SequenceDataset:
    require(
        state.spec_id == spec.fingerprint and state.available_ns <= computed_ns,
        "dataset exact fitted transform availability",
    )
    pairs = training_bindings(repo, spec, state.train_bindings)
    rows = []
    for sample, snapshot in pairs:
        require(sample.target_id is not None, "sequence TRAIN exact truth required")
        assert sample.target_id is not None
        target = repo.resolve(TargetVintage, sample.target_id)
        require(
            target_known_by_cutoff(target, spec.cutoff_ns)
            and target.origin == snapshot.origin
            and target.definition == spec.target,
            "sequence TRAIN known exact truth",
        )
        assert target.value is not None
        rows.append(
            SequenceTrainingRow(
                spec.fingerprint,
                sample.fingerprint,
                snapshot.fingerprint,
                target.fingerprint,
                target.value,
                max(snapshot.available_ns, target.clocks.final_available_ns),
            )
        )
    return SequenceDataset(
        spec.fingerprint,
        state.fingerprint,
        tuple(rows),
        spec.fold_id,
        tuple(f.fingerprint for f in spec.features),
        spec.target.fingerprint,
        spec.target.horizon.fingerprint,
        spec.cutoff_ns,
        computed_ns,
    )

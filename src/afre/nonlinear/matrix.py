"""Exact admitted AFRE-4 TRAIN-only knots and derived design matrices."""

from typing import TYPE_CHECKING

from afre.nonlinear.artifacts import (
    FittedTransformArtifact,
    InteractionMatrix,
    InteractionTrainingRow,
    InteractionValue,
    NonlinearInput,
)
from afre.nonlinear.definitions import InteractionDefinition, NonlinearModelSpec
from afre.nonlinear.interactions import interaction_for
from afre.nonlinear.schema import KnotPolicy
from afre.nonlinear.sources import validate_input
from afre.research_datasets.preprocessing import quantile
from afre.research_datasets.schema import Partition
from afre.schema import require
from afre.target_engine.models import TargetVintage
from afre.target_engine.validation import target_known_by_cutoff

if TYPE_CHECKING:
    from afre.nonlinear.repository import NonlinearRepository


def training_inputs(
    repo: "NonlinearRepository", spec: NonlinearModelSpec, ids: tuple[str, ...]
) -> tuple[NonlinearInput, ...]:
    b = repo.nonlinear_bounds
    require(
        0 < len(ids) <= b.training_rows and len(set(ids)) == len(ids),
        "TRAIN input bound/duplicates",
    )
    fold = repo.resolve_fold(spec.fold_id)
    require(fold.training_cutoff_ns == spec.cutoff_ns, "nonlinear fold cutoff mismatch")
    admitted = {
        s.fingerprint: s
        for s in repo.partition_samples(spec.fold_id, Partition.TRAIN)
        if s.target_definition_id == spec.target.fingerprint
    }
    inputs = tuple(
        sorted((repo.resolve(NonlinearInput, i) for i in ids), key=lambda x: x.sample_id)
    )
    require(
        {x.sample_id for x in inputs} == set(admitted) and len(inputs) == len(admitted),
        "nonlinear requires exact all admitted TRAIN samples",
    )
    for item in inputs:
        require(
            validate_input(repo, item, spec) is Partition.TRAIN,
            "nonlinear TRAIN partition only",
        )
    require(
        len(spec.columns) <= b.features
        and len(spec.features) <= b.features
        and len(inputs) * len(spec.columns) <= b.work_cells,
        "TRAIN matrix work/feature bound",
    )
    return inputs


def fit_transform(
    repo: "NonlinearRepository",
    spec: NonlinearModelSpec,
    definition: InteractionDefinition,
    ids: tuple[str, ...],
    started_ns: int,
    completed_ns: int,
    available_ns: int,
) -> FittedTransformArtifact:
    require(
        definition in spec.interaction_set.definitions
        and definition.parameters.knot_policy is KnotPolicy.TRAIN_QUANTILES,
        "TRAIN-fitted knot definition",
    )
    inputs = training_inputs(repo, spec, ids)
    values = tuple(
        next(s.value for s in item.scalars if s.definition == definition.inputs[0])
        for item in inputs
    )
    require(all(v is not None for v in values), "fitted knots require present TRAIN inputs")
    knots = tuple(
        quantile(tuple(v for v in values if v is not None), q)
        for q in definition.parameters.quantile_levels
    )
    return FittedTransformArtifact(
        spec.fingerprint,
        definition.fingerprint,
        spec.fold_id,
        tuple(i.fingerprint for i in inputs),
        tuple(i.sample_id for i in inputs),
        knots,
        spec.cutoff_ns,
        started_ns,
        completed_ns,
        available_ns,
    )


def matrix_for(
    repo: "NonlinearRepository",
    spec: NonlinearModelSpec,
    ids: tuple[str, ...],
    states: tuple[FittedTransformArtifact, ...],
    computed_ns: int,
) -> tuple[InteractionMatrix, tuple[InteractionValue, ...]]:
    inputs = training_inputs(repo, spec, ids)
    mapping = {s.definition_id: s for s in states}
    expected = {
        d.fingerprint
        for d in spec.interaction_set.definitions
        if d.parameters.knot_policy is KnotPolicy.TRAIN_QUANTILES
    }
    require(
        len(mapping) == len(states) and set(mapping) == expected, "exact transform state grid"
    )
    for state in states:
        require(
            state.spec_id == spec.fingerprint
            and state.fold_id == spec.fold_id
            and state.cutoff_ns == spec.cutoff_ns
            and set(state.train_input_ids) == set(ids),
            "exact transform TRAIN/fold/cutoff",
        )
    samples = {s.fingerprint: s for s in repo.partition_samples(spec.fold_id, Partition.TRAIN)}
    rows = []
    interactions: list[InteractionValue] = []
    for item in inputs:
        sample = samples[item.sample_id]
        require(sample.target_id is not None, "TRAIN target evidence")
        assert sample.target_id is not None
        target = repo.resolve(TargetVintage, sample.target_id)
        require(
            target.definition == spec.target
            and target.origin == item.origin
            and target_known_by_cutoff(target, spec.cutoff_ns),
            "TRAIN exact known truth",
        )
        assert target.value is not None
        derived = tuple(
            interaction_for(repo, d, item, computed_ns, mapping.get(d.fingerprint))
            for d in spec.interaction_set.definitions
        )
        original = {s.definition.fingerprint: s.value for s in item.scalars}
        values = (
            *tuple(original[f.fingerprint] for f in spec.original_features),
            *tuple(v.value for v in derived),
        )
        require(
            all(v is not None for v in values), "model FAIL missing derived/original feature"
        )
        row = InteractionTrainingRow(
            spec.fingerprint,
            item.sample_id,
            item.fingerprint,
            tuple(v.fingerprint for v in derived),
            tuple(v for v in values if v is not None),
            target.fingerprint,
            target.value,
            max(target.clocks.final_available_ns, computed_ns),
        )
        interactions.extend(derived)
        rows.append(row)
    matrix = InteractionMatrix(
        spec.fingerprint,
        spec.fold_id,
        tuple(rows),
        spec.columns,
        tuple(s.fingerprint for s in states),
        spec.cutoff_ns,
        computed_ns,
    )
    return matrix, tuple(interactions)

"""Explicit AFRE16 residual feature from an earlier frozen projection in a later fold."""

import math
from dataclasses import replace

from afre.nonlinear import (
    InteractionDefinition,
    InteractionSet,
    InteractionTransform,
    NonlinearEngine,
    NonlinearFamily,
    NonlinearModelSpec,
    NonlinearPreprocessing,
    TransformParameters,
)
from afre.orthogonalization import (
    AlignedSignalRow,
    OrthogonalizationEngine,
    OrthogonalizationMode,
    OrthogonalizationSpec,
)
from afre.research_datasets import DatasetEngine, Partition
from afre.research_datasets.splits import SplitDefinition
from afre.selection import (
    DiscreteDimension,
    NativeCandidateRecipe,
    SearchSpace,
    SelectionCriterion,
    SelectionRepository,
)
from afre.selection.orthogonal_features import publish_orthogonal_feature
from afre.statistical_models import ModelEngine, ModelFamily, PredictionScope, SolverIdentity
from afre.statistical_models.definitions import BaselineModelSpec
from afre.target_engine.definitions import TargetDefinition
from afre.time import TimeRange
from examples.orthogonalization_fixture import generic_reference, generic_source
from examples.selection_fixture import BUDGET


def filtered_rows(
    repo: SelectionRepository, fold_id: str, target: TargetDefinition
) -> tuple[OrthogonalizationSpec, tuple[AlignedSignalRow, ...]]:
    engine = OrthogonalizationEngine(repo)
    candidate, xref, zref = tuple(
        generic_reference("selection-" + n) for n in ("candidate", "x", "z")
    )
    for ref in (candidate, xref, zref):
        engine.register(ref)
    spec = OrthogonalizationSpec(
        candidate, (xref, zref), OrthogonalizationMode.TEMPORAL_PANEL, fold_id, 40, target
    )
    samples = tuple(
        s
        for part in (Partition.TRAIN, Partition.VALIDATION)
        for s in repo.partition_samples(fold_id, part)
        if s.target_definition_id == target.fingerprint
    )
    securities = sorted({s.security.fingerprint for s in samples})
    times = sorted({s.timestamp_ns for s in samples})
    rows = []
    for sample in samples:
        i = securities.index(sample.security.fingerprint) - 1.5
        t = times.index(sample.timestamp_ns) + 1.0
        x = i + 0.4 * t
        z = i * i + math.sin(t)
        u = i * i * i + 0.25 * math.cos(t)
        values = {candidate: 1.0 + 2.0 * x - 0.5 * z + 0.3 * u, xref: x, zref: z}
        observations = []
        for ref in (candidate, xref, zref):
            source = engine.publish_generic(generic_source(ref, sample, values[ref]))
            observations.append(
                engine.bind(ref, source.fingerprint, sample.fingerprint).fingerprint
            )
        rows.append(engine.align(spec, tuple(observations)))
    return spec, tuple(rows)


def orthogonal_space(repo: SelectionRepository, base: SearchSpace) -> SearchSpace:
    baseline = base.recipes[0].native_spec
    assert isinstance(baseline, BaselineModelSpec)
    orth = OrthogonalizationEngine(repo)
    original = repo.get(SplitDefinition, repo.resolve_fold(base.fold_id).split_definition_id)
    wide = replace(
        original,
        name="split.residual-source-wide-validation",
        validation=TimeRange(40, 70),
        fold_count=1,
    )
    source_split = DatasetEngine(repo).build_split(base.dataset_id, wide)
    spec, rows = filtered_rows(repo, source_split.fold_ids[0], baseline.target)
    projection = orth.fit(
        spec, tuple(r.fingerprint for r in rows if r.partition is Partition.TRAIN), 40
    )
    original = repo.get(SplitDefinition, repo.resolve_fold(base.fold_id).split_definition_id)
    split_spec = replace(
        original,
        name="split.later-residual-selection",
        train=TimeRange(40, 50),
        validation=TimeRange(60, 70),
        training_cutoff_ns=60,
        fold_count=1,
        test=original.test,
        embargo=replace(original.embargo, count=0),
    )
    split = DatasetEngine(repo).build_split(base.dataset_id, split_spec)
    fold = repo.resolve_fold(split.fold_ids[0])
    train = repo.partition_samples(fold.fingerprint, Partition.TRAIN)
    validation = tuple(
        s
        for s in repo.partition_samples(fold.fingerprint, Partition.VALIDATION)
        if s.timestamp_ns == 60
    )
    train = tuple(s for s in train if s.target_definition_id == base.target_id)
    validation = tuple(s for s in validation if s.target_definition_id == base.target_id)
    by_sample = {r.sample_id: r for r in rows}
    bindings = []
    packets = {}
    nonlinear = NonlinearEngine(repo)
    feature = None
    for sample in (*train, *validation):
        row = by_sample[sample.fingerprint]
        residual = orth.residual(projection.fingerprint, row.fingerprint, sample.timestamp_ns)
        binding = publish_orthogonal_feature(repo, residual.fingerprint)
        from afre.nonlinear.artifacts import ScalarInput

        scalar = repo.get(ScalarInput, binding.scalar_id)
        feature = scalar.definition
        bindings.append(binding.fingerprint)
        packets[sample.fingerprint] = nonlinear.input(
            sample.fingerprint, (scalar.fingerprint,)
        ).fingerprint
    assert feature is not None
    interaction = InteractionDefinition(
        "declared-residual",
        (feature,),
        InteractionTransform.IDENTITY,
        TransformParameters(),
        "declared-residual",
        feature.unit,
    )
    native = NonlinearModelSpec(
        InteractionSet((interaction,), baseline.target),
        NonlinearFamily.LINEAR_ON_INTERACTIONS,
        (),
        fold.fingerprint,
        60,
        0,
        preprocessing=NonlinearPreprocessing.STANDARDIZE,
        ridge_penalty=0.1,
    )
    recipes = tuple(
        NativeCandidateRecipe(
            replace(native, seed=n),
            (("seed", str(n)),),
            train_input_ids=tuple(packets[s.fingerprint] for s in train),
            validation_bindings=tuple(
                (s.fingerprint, packets[s.fingerprint]) for s in validation
            ),
            feature_ids=(feature.fingerprint,),
            orthogonal_feature_ids=tuple(bindings),
        )
        for n in (0, 1)
    )
    plain = replace(
        baseline,
        fold_id=fold.fingerprint,
        preprocessing_state_ids=(),
        family=ModelFamily.REFERENCE_VALUE,
        reference_value=0.0,
        solver=SolverIdentity.REFERENCE_STATISTIC,
        l1_penalty=0.0,
        l2_penalty=0.0,
    )
    model = ModelEngine(repo)
    anchor = model.predict_samples(
        model.fit_model(plain, 60, 60, 60).artifact_id,
        tuple(s.fingerprint for s in validation),
        PredictionScope.VALIDATION,
    )
    return SearchSpace(
        "offline-declared-residual-selection",
        base.target_id,
        base.horizon_id,
        base.dataset_id,
        fold.fingerprint,
        (DiscreteDimension("seed", ("0", "1")),),
        recipes,
        BUDGET,
        SelectionCriterion.MIN_MSE,
        tuple(s.fingerprint for s in validation),
        60,
        permit_single_valid=True,
        failure_anchor_source_ids=tuple(p.fingerprint for p in anchor),
    )

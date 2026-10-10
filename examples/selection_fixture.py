"""Offline native fixtures; all recipes are frozen before selection starts."""

from dataclasses import dataclass, replace

from afre.event_conditioned.artifacts import EventConditionedForecast, EventConditionedModel
from afre.event_conditioned.definitions import EventConditioningSpec
from afre.nonlinear.artifacts import (
    InteractionMatrix,
    NonlinearForecast,
    NonlinearModelArtifact,
)
from afre.nonlinear.definitions import NonlinearModelSpec
from afre.probabilistic.artifacts import ProbabilisticForecast, ProbabilisticModelArtifact
from afre.probabilistic.definitions import ProbabilisticModelSpec
from afre.regime_conditioned.artifacts import RegimeConditionedForecast, RegimeConditionedModel
from afre.regime_conditioned.definitions import RegimeConditioningSpec
from afre.research_datasets import DatasetEngine, Partition
from afre.selection import (
    DiscreteDimension,
    NativeCandidateRecipe,
    ResourceBudget,
    SearchSpace,
    SelectionCriterion,
    SelectionRepository,
)
from afre.sequence.artifacts import (
    SequenceForecast,
    SequenceModelArtifact,
    SequenceTransformArtifact,
)
from afre.sequence.definitions import SequenceModelSpec
from afre.statistical_models import ModelEngine, ModelFamily, PredictionScope
from afre.statistical_models.artifacts import FittedModelArtifact, PointForecast
from afre.statistical_models.definitions import BaselineModelSpec
from examples.research_dataset_demo import populate, split_definition
from examples.statistical_baselines_demo import baseline_spec
from examples.uncertainty_fixture import build_fixture

BUDGET = ResourceBudget(128, 4096, 256000, 256000, 100000000, 8388608)


@dataclass(frozen=True)
class SelectionFixture:
    space: SearchSpace
    test_sample_ids: tuple[str, ...]


def small_fixture(repo: SelectionRepository, reverse: bool = False) -> SelectionFixture:
    fixture = populate(repo, reverse=reverse)
    engine = DatasetEngine(repo)
    dataset = engine.build_dataset(
        fixture.definition,
        tuple(reversed(fixture.requests)) if reverse else fixture.requests,
        100,
        100,
    )
    split = engine.build_split(dataset.fingerprint, split_definition(fixture))
    state = engine.fit_preprocessing(split.fold_ids[0], fixture.preprocessing)
    specs = tuple(
        baseline_spec(fixture, split, state, f)
        for f in (ModelFamily.UNCONDITIONAL_MEAN, ModelFamily.REFERENCE_VALUE)
    )
    target = specs[0].target
    val = tuple(
        s.fingerprint
        for s in repo.partition_samples(split.fold_ids[0], Partition.VALIDATION)
        if s.target_definition_id == target.fingerprint
    )
    model = ModelEngine(repo)
    anchor = model.predict_samples(
        model.fit_model(specs[0], 40, 40, 40).artifact_id, val, PredictionScope.VALIDATION
    )
    recipes = tuple(
        NativeCandidateRecipe(
            spec,
            (("family", spec.family.value),),
            preprocessing_ids=spec.preprocessing_state_ids,
        )
        for spec in specs
    )
    space = SearchSpace(
        "offline-small-selection",
        target.fingerprint,
        target.horizon.fingerprint,
        dataset.fingerprint,
        split.fold_ids[0],
        (DiscreteDimension("family", tuple(s.family.value for s in specs)),),
        recipes,
        BUDGET,
        SelectionCriterion.MIN_MSE,
        val,
        40,
        permit_single_valid=True,
        failure_anchor_source_ids=tuple(p.fingerprint for p in anchor),
    )
    return SelectionFixture(
        space,
        tuple(
            s.fingerprint
            for s in repo.partition_samples(space.fold_id, Partition.TEST)
            if s.target_definition_id == target.fingerprint
        ),
    )


def family_fixture(repo: SelectionRepository, reverse: bool = False) -> SelectionFixture:
    native = build_fixture(repo, reverse)
    recipes = []
    names = ("point", "gaussian", "event", "hard-regime", "nonlinear", "sequence")
    for name in reversed(names) if reverse else names:
        forecasts = tuple(repo.get_any(i) for i in native.ids(name))
        first = forecasts[0]
        choice = (("native-family", name),)
        if isinstance(first, PointForecast):
            model = repo.get(FittedModelArtifact, first.model_artifact_id)
            spec = repo.get(BaselineModelSpec, model.spec_id)
            recipe = NativeCandidateRecipe(
                spec, choice, preprocessing_ids=spec.preprocessing_state_ids
            )
        elif isinstance(first, ProbabilisticForecast):
            prob = repo.get(ProbabilisticModelArtifact, first.model_artifact_id)
            recipe = NativeCandidateRecipe(
                repo.get(ProbabilisticModelSpec, prob.spec_id), choice
            )
        elif isinstance(first, EventConditionedForecast):
            event_model = repo.get(EventConditionedModel, first.model_id)
            recipe = NativeCandidateRecipe(
                repo.get(EventConditioningSpec, event_model.spec_id),
                choice,
                train_input_ids=event_model.observation_ids,
                validation_bindings=tuple(
                    (p.observation_id, p.base_forecast_id)
                    for p in forecasts
                    if isinstance(p, EventConditionedForecast)
                ),
            )
        elif isinstance(first, RegimeConditionedForecast):
            regime_model = repo.get(RegimeConditionedModel, first.model_id)
            recipe = NativeCandidateRecipe(
                repo.get(RegimeConditioningSpec, regime_model.spec_id),
                choice,
                train_input_ids=regime_model.observation_ids,
                validation_bindings=tuple(
                    (p.observation_id, p.base_forecast_id)
                    for p in forecasts
                    if isinstance(p, RegimeConditionedForecast)
                ),
            )
        elif isinstance(first, NonlinearForecast):
            nonlinear = repo.get(NonlinearModelArtifact, first.model_id)
            nspec = repo.get(NonlinearModelSpec, nonlinear.spec_id)
            matrix = repo.get(InteractionMatrix, nonlinear.matrix_id)
            recipe = NativeCandidateRecipe(
                nspec,
                choice,
                train_input_ids=tuple(r.input_id for r in matrix.rows),
                validation_bindings=tuple(
                    (p.sample_id, p.input_id)
                    for p in forecasts
                    if isinstance(p, NonlinearForecast)
                ),
                feature_ids=tuple(f.fingerprint for f in nspec.features),
            )
        else:
            assert isinstance(first, SequenceForecast)
            sequence = repo.get(SequenceModelArtifact, first.model_id)
            sspec = repo.get(SequenceModelSpec, sequence.spec_id)
            transform = repo.get(SequenceTransformArtifact, sequence.transform_id)
            recipe = NativeCandidateRecipe(
                sspec,
                choice,
                train_bindings=transform.train_bindings,
                validation_bindings=tuple(
                    (p.sample_id, p.snapshot_id)
                    for p in forecasts
                    if isinstance(p, SequenceForecast)
                ),
                feature_ids=tuple(f.fingerprint for f in sspec.features),
            )
        recipes.append(recipe)
    point = repo.get(PointForecast, native.ids("point")[0])
    base_model = repo.get(FittedModelArtifact, point.model_artifact_id)
    base_spec = repo.get(BaselineModelSpec, base_model.spec_id)
    fold = repo.resolve_fold(base_spec.fold_id)
    samples = tuple(repo.get(PointForecast, i).input.sample_id for i in native.ids("point"))
    assert all(i is not None for i in samples)
    space = SearchSpace(
        "offline-native-family-selection",
        base_spec.target.fingerprint,
        base_spec.target.horizon.fingerprint,
        fold.dataset_id,
        fold.fingerprint,
        (DiscreteDimension("native-family", names),),
        tuple(recipes),
        BUDGET,
        SelectionCriterion.MIN_MSE,
        tuple(i for i in samples if i is not None),
        40,
        permit_single_valid=True,
        failure_anchor_source_ids=native.ids("point"),
    )
    return SelectionFixture(
        space,
        tuple(
            s.fingerprint
            for s in repo.partition_samples(space.fold_id, Partition.TEST)
            if s.target_definition_id == space.target_id
        ),
    )


def criterion_space(space: SearchSpace, criterion: SelectionCriterion) -> SearchSpace:
    return replace(
        space, search_key=space.search_key + "-" + criterion.value, criterion=criterion
    )

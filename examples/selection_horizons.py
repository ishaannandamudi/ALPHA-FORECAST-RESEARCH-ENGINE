"""Separate native one-hour and one-day searches, without coupled selection."""

from dataclasses import replace

from afre.regime_conditioned.artifacts import RegimeConditionedSample
from afre.regime_conditioned.definitions import RegimeConditioningSpec
from afre.research_datasets.samples import ResearchSample
from afre.selection import (
    DiscreteDimension,
    NativeCandidateRecipe,
    SearchSpace,
    SelectionCriterion,
    SelectionRepository,
)
from afre.statistical_models.artifacts import FittedModelArtifact, PointForecast
from afre.statistical_models.definitions import BaselineModelSpec
from examples.regime_horizon_fixture import real_horizons
from examples.selection_fixture import BUDGET


def horizon_spaces(repo: SelectionRepository) -> tuple[tuple[SearchSpace, int], ...]:
    spaces = []
    for model, forecasts in real_horizons(repo):
        conditioned = repo.get(RegimeConditioningSpec, model.spec_id)
        base = repo.get(FittedModelArtifact, conditioned.base_model_id)
        spec = repo.get(BaselineModelSpec, base.spec_id)
        fold = repo.resolve_fold(spec.fold_id)
        samples = tuple(
            repo.get(
                ResearchSample,
                repo.get(RegimeConditionedSample, p.observation_id).sample_id,
            ).fingerprint
            for p in forecasts
        )
        anchors = tuple(
            repo.get(PointForecast, p.base_forecast_id).fingerprint for p in forecasts
        )
        recipes = tuple(
            NativeCandidateRecipe(
                replace(spec, random_seed=n),
                (("seed", str(n)),),
                preprocessing_ids=spec.preprocessing_state_ids,
            )
            for n in (0, 1)
        )
        space = SearchSpace(
            "actual-" + str(spec.target.horizon.duration_ns),
            spec.target.fingerprint,
            spec.target.horizon.fingerprint,
            fold.dataset_id,
            fold.fingerprint,
            (DiscreteDimension("seed", ("0", "1")),),
            recipes,
            BUDGET,
            SelectionCriterion.MIN_MSE,
            samples,
            fold.training_cutoff_ns,
            permit_single_valid=True,
            failure_anchor_source_ids=anchors,
        )
        cutoff = max(repo.get(ResearchSample, i).target_available_ns or 0 for i in samples)
        spaces.append((space, cutoff))
    return tuple(spaces)

"""Real native family adapters, exact probability scoring and independent hour/day grids."""

import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from afre.regime_conditioned.artifacts import RegimeConditionedSample
from afre.regime_conditioned.definitions import RegimeConditioningSpec
from afre.research_datasets.samples import ResearchSample
from afre.schema import ContractError
from afre.selection import (
    DiscreteDimension,
    NativeCandidateRecipe,
    SearchSpace,
    SelectionCriterion,
    SelectionEngine,
    SelectionRepository,
)
from afre.selection.registry import CandidateRegistrySnapshot
from afre.selection.results import CandidateValidationResult, SelectionResult
from afre.selection.schema import CandidateStatus
from afre.statistical_models.artifacts import FittedModelArtifact, PointForecast
from afre.statistical_models.definitions import BaselineModelSpec
from examples.regime_horizon_fixture import DAY, HOUR, real_horizons
from examples.selection_fixture import BUDGET, SelectionFixture
from examples.selection_orthogonal_fixture import orthogonal_space
from tests.selection.conftest import SelectionCase


def test_all_six_native_families_restart(
    tmp_path: Path,
    selection_families: tuple[
        Path, SelectionFixture, SelectionResult, CandidateRegistrySnapshot
    ],
) -> None:
    path, fixture, result, registry = selection_families
    copy = tmp_path / "families.sqlite"
    shutil.copyfile(path, copy)
    with SelectionRepository(copy) as repo, repo.read_snapshot(), repo.validation_cache():
        assert repo.resolve(SelectionResult, result.fingerprint) == result
        assert repo.resolve(CandidateRegistrySnapshot, registry.fingerprint) == registry
        assert {r.native_phase for r in fixture.space.recipes} == {5, 6, 10, 11, 13, 14}
        assert all(e.status is CandidateStatus.VALID for e in registry.entries)
        assert len({e.trial_id for e in registry.entries}) == 6


@pytest.mark.parametrize("criterion", (SelectionCriterion.MIN_CRPS, SelectionCriterion.MIN_NLL))
def test_probability_only_compatible_native_score(
    tmp_path: Path,
    selection_families: tuple[
        Path, SelectionFixture, SelectionResult, CandidateRegistrySnapshot
    ],
    criterion: SelectionCriterion,
) -> None:
    path, fixture, _, _ = selection_families
    copy = tmp_path / "probability.sqlite"
    shutil.copyfile(path, copy)
    with SelectionRepository(copy) as repo:
        result, registry = SelectionEngine(repo).select(
            replace(fixture.space, criterion=criterion), 100, 100
        )
        valid = tuple(e for e in registry.entries if e.status is CandidateStatus.VALID)
        assert len(valid) == 1 and result.selected_candidate_id == valid[0].candidate_id
        record = repo.get(CandidateValidationResult, valid[0].validation_id)
        assert record.value == pytest.approx(
            sum(p.primary_loss for p in record.pairs if p.primary_loss is not None)
            / len(record.pairs)
        )
        assert len(registry.entries) == 6


def test_causal_declared_residual_feature_in_later_fold(case: SelectionCase) -> None:
    space = orthogonal_space(case.repository, case.space)
    result, registry = SelectionEngine(case.repository).select(space, 100, 100)
    assert result.selected_candidate_id is not None
    assert all(e.status is CandidateStatus.VALID for e in registry.entries)
    assert all(r.orthogonal_feature_ids for r in space.recipes)
    # Merely naming a residual unrelated to the actual native feature is rejected.
    r = space.recipes[0]
    broken = replace(r, feature_ids=case.space.recipes[0].preprocessing_ids)
    with pytest.raises(ContractError, match="feature"):
        SelectionEngine(case.repository).select(
            replace(space, recipes=(broken, space.recipes[1])), 100, 100
        )


def test_actual_hour_day_searches_remain_independent(tmp_path: Path) -> None:
    with SelectionRepository(tmp_path / "horizons.sqlite") as repo:
        horizons = real_horizons(repo)
        results = []
        durations = []
        for model, forecasts in horizons:
            conditioned = repo.get(RegimeConditioningSpec, model.spec_id)
            base = repo.get(FittedModelArtifact, conditioned.base_model_id)
            spec = repo.get(BaselineModelSpec, base.spec_id)
            durations.append(spec.target.horizon.duration_ns)
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
            result, _ = SelectionEngine(repo).select(space, cutoff, cutoff)
            assert result.selected_candidate_id is not None
            results.append(result)
        assert set(durations) == {HOUR, DAY}
        assert results[0].search_space_id != results[1].search_space_id
        assert set(results[0].candidate_ids).isdisjoint(results[1].candidate_ids)


def test_previous_test_rows_cannot_be_reclassified_in_later_fold(case: SelectionCase) -> None:
    from afre.research_datasets import DatasetEngine, Partition
    from afre.research_datasets.splits import SplitDefinition
    from afre.time import TimeRange

    repo = case.repository
    fold = repo.resolve_fold(case.space.fold_id)
    definition = repo.get(SplitDefinition, fold.split_definition_id)
    later = replace(
        definition,
        name="split.attempt-to-reclassify-old-TEST",
        train=TimeRange(40, 50),
        validation=TimeRange(80, 90),
        test=TimeRange(90, 100),
        training_cutoff_ns=60,
        fold_count=1,
    )
    split = DatasetEngine(repo).build_split(case.space.dataset_id, later)
    new_fold = repo.resolve_fold(split.fold_ids[0])
    samples = tuple(
        s.fingerprint
        for s in repo.partition_samples(new_fold.fingerprint, Partition.VALIDATION)
        if s.target_definition_id == case.space.target_id
    )
    assert set(samples) & set(case.fixture.test_sample_ids)
    with pytest.raises(ContractError, match="reclassify.*TEST"):
        SelectionEngine(repo).select(
            replace(case.space, fold_id=new_fold.fingerprint, validation_sample_ids=samples),
            100,
            100,
        )

"""Small frozen upstream store, copied for each model test."""

import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from afre.research_datasets import (
    DatasetEngine,
    FoldPreprocessingState,
    ResearchDatasetManifest,
    ResearchSplit,
)
from afre.statistical_models import (
    BaselineModelSpec,
    InterceptPolicy,
    ModelEngine,
    ModelFamily,
    ModelRepository,
    NonconvergencePolicy,
    RankDeficiencyPolicy,
    SolverIdentity,
    TrainingMissingPolicy,
)
from examples.research_dataset_demo import ResearchFixture, populate, split_definition


@dataclass(frozen=True)
class ModelCase:
    path: Path
    repository: ModelRepository
    engine: ModelEngine
    fixture: ResearchFixture
    dataset: ResearchDatasetManifest
    split: ResearchSplit
    preprocessing: FoldPreprocessingState

    def spec(self, family: ModelFamily = ModelFamily.LINEAR_REGRESSION) -> BaselineModelSpec:
        solver = (
            SolverIdentity.REFERENCE_STATISTIC
            if family
            in (
                ModelFamily.UNCONDITIONAL_MEAN,
                ModelFamily.UNCONDITIONAL_MEDIAN,
                ModelFamily.REFERENCE_VALUE,
                ModelFamily.PERSISTENCE,
            )
            else SolverIdentity.COORDINATE_DESCENT
            if family in (ModelFamily.LASSO_REGRESSION, ModelFamily.ELASTIC_NET)
            else SolverIdentity.PIVOTED_HOUSEHOLDER_QR
        )
        target = next(
            t
            for t in self.fixture.definition.target_set.definitions
            if t.horizon.duration_ns == 5
        )
        return BaselineModelSpec(
            family,
            self.fixture.definition.feature_set,
            target,
            self.split.fold_ids[0],
            (self.preprocessing.fingerprint,),
            InterceptPolicy.GLOBAL,
            0.001 if family in (ModelFamily.LASSO_REGRESSION, ModelFamily.ELASTIC_NET) else 0.0,
            1.0 if family in (ModelFamily.RIDGE_REGRESSION, ModelFamily.ELASTIC_NET) else 0.0,
            False,
            10000,
            1e-10,
            1e12,
            RankDeficiencyPolicy.FAIL,
            NonconvergencePolicy.FAIL,
            TrainingMissingPolicy.SKIP,
            0,
            solver,
            0.0 if family is ModelFamily.REFERENCE_VALUE else None,
        )


@pytest.fixture(scope="session")
def model_baseline(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[
    Path, ResearchFixture, ResearchDatasetManifest, ResearchSplit, FoldPreprocessingState
]:
    path = tmp_path_factory.mktemp("model-baseline") / "baseline.sqlite"
    with ModelRepository(path) as repository:
        fixture = populate(repository)
        research = DatasetEngine(repository)
        dataset = research.build_dataset(fixture.definition, fixture.requests, 100, 100)
        split = research.build_split(dataset.fingerprint, split_definition(fixture))
        state = research.fit_preprocessing(split.fold_ids[0], fixture.preprocessing)
    return path, fixture, dataset, split, state


@pytest.fixture
def model_case(
    tmp_path: Path,
    model_baseline: tuple[
        Path, ResearchFixture, ResearchDatasetManifest, ResearchSplit, FoldPreprocessingState
    ],
) -> Iterator[ModelCase]:
    source, fixture, dataset, split, state = model_baseline
    path = tmp_path / "models.sqlite"
    shutil.copyfile(source, path)
    with ModelRepository(path) as repository:
        yield ModelCase(
            path, repository, ModelEngine(repository), fixture, dataset, split, state
        )

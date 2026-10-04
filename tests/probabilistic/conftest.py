"""A copied completed AFRE-5 scaffold keeps probability tests independent."""

import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from afre.probabilistic import (
    DistributionFamily,
    ObservationPolicy,
    ProbabilisticEngine,
    ProbabilisticFitRun,
    ProbabilisticModelSpec,
    ProbabilisticRepository,
    QuantileDefinition,
    ResidualCentering,
    ScalePolicy,
    ScaleSpec,
    ThresholdComparison,
    ThresholdDefinition,
    ThresholdRequest,
)
from afre.research_datasets import DatasetEngine, Partition
from afre.statistical_models import ModelEngine, ModelFamily, PredictionScope
from examples.research_dataset_demo import ResearchFixture, populate, split_definition
from examples.statistical_baselines_demo import baseline_spec


@dataclass(frozen=True)
class ProbabilityCase:
    path: Path
    repo: ProbabilisticRepository
    fixture: ResearchFixture
    residual_spec: ProbabilisticModelSpec
    unconditional_spec: ProbabilisticModelSpec
    validation_ids: tuple[str, ...]
    test_ids: tuple[str, ...]
    train_ids: tuple[str, ...]

    @property
    def engine(self) -> ProbabilisticEngine:
        return ProbabilisticEngine(self.repo)

    def fit(self, spec: ProbabilisticModelSpec | None = None) -> ProbabilisticFitRun:
        return self.engine.fit_model(spec or self.residual_spec, 40, 40, 40)

    def forecast_ids(self, run: ProbabilisticFitRun) -> tuple[str, ...]:
        return tuple(
            p.fingerprint
            for p in self.engine.predict_samples(
                run.artifact_id, self.validation_ids, PredictionScope.VALIDATION
            )
        )


@pytest.fixture(scope="session")
def probability_baseline(tmp_path_factory: pytest.TempPathFactory) -> ProbabilityCase:
    path = tmp_path_factory.mktemp("probability-baseline") / "base.sqlite"
    with ProbabilisticRepository(path) as repo:
        f = populate(repo)
        research = DatasetEngine(repo)
        dataset = research.build_dataset(f.definition, f.requests, 100, 100)
        split = research.build_split(dataset.fingerprint, split_definition(f))
        state = research.fit_preprocessing(split.fold_ids[0], f.preprocessing)
        specs = []
        for family in (ModelFamily.RIDGE_REGRESSION, ModelFamily.UNCONDITIONAL_MEAN):
            bs = baseline_spec(f, split, state, family)
            run = ModelEngine(repo).fit_model(bs, 40, 40, 40)
            specs.append(
                ProbabilisticModelSpec(
                    run.artifact_id,
                    DistributionFamily.EMPIRICAL_RESIDUAL,
                    ObservationPolicy.TRAIN_TARGETS
                    if family is ModelFamily.UNCONDITIONAL_MEAN
                    else ObservationPolicy.POINT_MODEL_RESIDUALS,
                    ResidualCentering.RAW,
                    ScaleSpec(ScalePolicy.TRAIN_RESIDUAL_STD),
                    QuantileDefinition((0.1, 0.5, 0.9)),
                    ThresholdDefinition(
                        tuple(ThresholdRequest(0.0, c) for c in ThresholdComparison)
                    ),
                    bs.fold_id,
                    bs.target,
                    40,
                    0,
                )
            )
        groups = []
        with repo.read_snapshot(), repo.validation_cache():
            for partition in (Partition.VALIDATION, Partition.TEST, Partition.TRAIN):
                groups.append(
                    tuple(
                        s.fingerprint
                        for s in repo.partition_samples(bs.fold_id, partition)
                        if s.target_definition_id == bs.target.fingerprint
                    )
                )
        return ProbabilityCase(path, repo, f, specs[0], specs[1], *groups)


@pytest.fixture
def probability_case(
    tmp_path: Path, probability_baseline: ProbabilityCase
) -> Iterator[ProbabilityCase]:
    base = probability_baseline
    path = tmp_path / "probability.sqlite"
    shutil.copyfile(base.path, path)
    with ProbabilisticRepository(path) as repo:
        yield ProbabilityCase(
            path,
            repo,
            base.fixture,
            base.residual_spec,
            base.unconditional_spec,
            base.validation_ids,
            base.test_ids,
            base.train_ids,
        )

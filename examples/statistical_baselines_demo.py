"""Offline transparent baselines, target-free prediction and frozen correction replay."""

from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TypeVar

from afre.research_datasets import (
    DatasetEngine,
    FoldPreprocessingState,
    Partition,
    ResearchDatasetManifest,
    ResearchSplit,
)
from afre.schema import Artifact, require
from afre.serialization import canonical_json
from afre.statistical_models import (
    BaselineModelSpec,
    InterceptPolicy,
    ModelEngine,
    ModelFamily,
    ModelFitRun,
    ModelRepository,
    NonconvergencePolicy,
    PointEvaluation,
    PointForecast,
    PredictionScope,
    RankDeficiencyPolicy,
    SolverIdentity,
    TrainingMissingPolicy,
)
from afre.target_engine.market_data import TargetBar
from afre.target_engine.models import TargetVintage
from examples.feature_store_demo import clocks, source_vintage
from examples.research_dataset_demo import ResearchFixture, populate, split_definition
from examples.universe_demo import SECURITIES

A = TypeVar("A", bound=Artifact)


class DemoRepository(ModelRepository):
    """Demonstration guard and synthetic held-out-price perturbation only."""

    def __init__(self, path: str | Path, heldout_scale: float = 1.0) -> None:
        self.deny_truth = False
        self.heldout_scale = heldout_scale
        super().__init__(path)

    def get(self, cls: type[A], identity: str) -> A:
        require(
            not self.deny_truth or cls is not TargetVintage,
            "demo prediction attempted to load a response",
        )
        return super().get(cls, identity)

    def put(self, value: Artifact) -> str:
        if (
            isinstance(value, TargetBar)
            and value.period.end_ns >= 35
            and value.close is not None
        ):
            value = replace(value, close=value.close * self.heldout_scale)
        return super().put(value)


def baseline_spec(
    fixture: ResearchFixture,
    split: ResearchSplit,
    state: FoldPreprocessingState,
    family: ModelFamily,
) -> BaselineModelSpec:
    target = next(
        t for t in fixture.definition.target_set.definitions if t.horizon.duration_ns == 5
    )
    constant = family in (
        ModelFamily.UNCONDITIONAL_MEAN,
        ModelFamily.UNCONDITIONAL_MEDIAN,
        ModelFamily.REFERENCE_VALUE,
    )
    elastic = family in (ModelFamily.LASSO_REGRESSION, ModelFamily.ELASTIC_NET)
    return BaselineModelSpec(
        family,
        fixture.definition.feature_set,
        target,
        split.fold_ids[0],
        (state.fingerprint,),
        InterceptPolicy.GLOBAL,
        0.001 if elastic else 0.0,
        1.0 if family in (ModelFamily.RIDGE_REGRESSION, ModelFamily.ELASTIC_NET) else 0.0,
        False,
        10000,
        1e-10,
        1e12,
        RankDeficiencyPolicy.FAIL,
        NonconvergencePolicy.FAIL,
        TrainingMissingPolicy.SKIP,
        0,
        SolverIdentity.REFERENCE_STATISTIC
        if constant
        else SolverIdentity.COORDINATE_DESCENT
        if elastic
        else SolverIdentity.PIVOTED_HOUSEHOLDER_QR,
        0.0 if family is ModelFamily.REFERENCE_VALUE else None,
    )


@dataclass(frozen=True)
class ModelFixture:
    research: ResearchFixture
    dataset: ResearchDatasetManifest
    split: ResearchSplit
    state: FoldPreprocessingState
    runs: tuple[ModelFitRun, ...]
    predictions: tuple[tuple[PointForecast, ...], ...]
    evaluations: tuple[PointEvaluation, ...]


def build_demo(
    repo: DemoRepository, reverse: bool = False, validation_outlier: float = 1000.0
) -> ModelFixture:
    fixture = populate(repo, reverse=reverse, validation_outlier=validation_outlier)
    research, models = DatasetEngine(repo), ModelEngine(repo)
    dataset = research.build_dataset(
        fixture.definition,
        tuple(reversed(fixture.requests)) if reverse else fixture.requests,
        100,
        100,
    )
    split = research.build_split(dataset.fingerprint, split_definition(fixture))
    state = research.fit_preprocessing(split.fold_ids[0], fixture.preprocessing)
    families = (
        ModelFamily.UNCONDITIONAL_MEAN,
        ModelFamily.LINEAR_REGRESSION,
        ModelFamily.RIDGE_REGRESSION,
        ModelFamily.LASSO_REGRESSION,
        ModelFamily.ELASTIC_NET,
    )
    runs = tuple(
        models.fit_model(baseline_spec(fixture, split, state, family), 40, 40, 40)
        for family in families
    )
    spec = baseline_spec(fixture, split, state, ModelFamily.LINEAR_REGRESSION)
    with repo.read_snapshot(), repo.validation_cache():
        samples = tuple(
            s.fingerprint
            for s in repo.partition_samples(split.fold_ids[0], Partition.VALIDATION)
            if s.target_definition_id == spec.target.fingerprint
        )
    repo.deny_truth = True
    try:
        predictions = tuple(
            models.predict_samples(
                run.artifact_id,
                tuple(reversed(samples)) if reverse else samples,
                PredictionScope.VALIDATION,
            )
            for run in runs
        )
    finally:
        repo.deny_truth = False
    evaluations = tuple(
        models.evaluate(tuple(p.fingerprint for p in group), 100, 100) for group in predictions
    )
    return ModelFixture(fixture, dataset, split, state, runs, predictions, evaluations)


def semantic_bytes(repo: ModelRepository, demo: ModelFixture) -> tuple[str, ...]:
    values: list[Artifact] = [
        *demo.runs,
        *demo.evaluations,
        *(p for group in demo.predictions for p in group),
    ]
    values.extend(ModelEngine(repo).model_artifact(run.artifact_id) for run in demo.runs)
    return tuple(canonical_json(value) for value in values)


def main() -> None:
    with TemporaryDirectory(prefix="afre-baselines-demo-") as directory:
        path = Path(directory) / "models.sqlite"
        with DemoRepository(path) as repo:
            demo = build_demo(repo)
            engine = ModelEngine(repo)
            frozen = semantic_bytes(repo, demo)
            for run, evaluation in zip(demo.runs, demo.evaluations, strict=True):
                model = engine.model_artifact(run.artifact_id)
                print(
                    model.solver.value,
                    "intercept",
                    model.intercept,
                    "coefficients",
                    model.coefficients,
                    "fixed penalties",
                    model.l1_penalty,
                    model.l2_penalty,
                    "VALIDATION",
                    {m.name.value: m.value for m in evaluation.metrics},
                )
                engine.model_audit(run.artifact_id)
            for evaluation in demo.evaluations[1:]:
                engine.compare_models(evaluation.fingerprint, demo.evaluations[0].fingerprint)
            engine.prediction_audit(demo.predictions[1][0].fingerprint)
            old = source_vintage(
                demo.research.preprocessing.normalization.feature,
                10,
                10,
                10.0,
                entity=SECURITIES[0].instrument,
            )
            with repo.transaction():
                repo.put(
                    replace(old, value=999.0, clocks=clocks(10), predecessor_id=old.fingerprint)
                )
            research = DatasetEngine(repo)
            corrected = research.build_dataset(
                demo.research.definition, demo.research.requests, 100, 100
            )
            corrected_split = research.build_split(
                corrected.fingerprint, split_definition(demo.research)
            )
            corrected_state = research.fit_preprocessing(
                corrected_split.fold_ids[0], demo.research.preprocessing
            )
            new_run = engine.fit_model(
                baseline_spec(
                    demo.research,
                    corrected_split,
                    corrected_state,
                    ModelFamily.LINEAR_REGRESSION,
                ),
                40,
                40,
                40,
            )
            assert new_run.artifact_id != demo.runs[1].artifact_id
            assert semantic_bytes(repo, demo) == frozen
            print("Corrected data produces new fit identity", new_run.artifact_id)
        with DemoRepository(
            Path(directory) / "perturbed.sqlite", heldout_scale=100.0
        ) as changed_repo:
            changed = build_demo(changed_repo, validation_outlier=1e8)
            original_parameters = []
            with ModelRepository(path) as reopened:
                for run in demo.runs:
                    model = ModelEngine(reopened).model_artifact(run.artifact_id)
                    original_parameters.append(
                        (model.intercept, model.coefficients, model.reference_value)
                    )
            changed_parameters = []
            for run in changed.runs:
                model = ModelEngine(changed_repo).model_artifact(run.artifact_id)
                changed_parameters.append(
                    (model.intercept, model.coefficients, model.reference_value)
                )
            assert changed_parameters == original_parameters
        with ModelRepository(path) as reopened:
            assert semantic_bytes(reopened, demo) == frozen
            reopened.audit()
        print(
            "PASS: TRAIN-only fits, target-free prediction, exact-sample OOS comparison, "
            "held-out perturbation, correction, lineage audits and byte-identical restart"
        )


if __name__ == "__main__":
    main()

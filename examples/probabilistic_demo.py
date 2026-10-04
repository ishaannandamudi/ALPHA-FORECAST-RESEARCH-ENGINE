"""Offline causal distributions, proper OOS scores and immutable correction replay."""

from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TypeVar

from afre.probabilistic import (
    DistributionFamily,
    ObservationPolicy,
    ProbabilisticEngine,
    ProbabilisticEvaluation,
    ProbabilisticEvaluationProtocol,
    ProbabilisticFitRun,
    ProbabilisticForecast,
    ProbabilisticModelSpec,
    ProbabilisticRepository,
    QuantileDefinition,
    QuantileInterval,
    ResidualCentering,
    ScalePolicy,
    ScaleSpec,
    ThresholdComparison,
    ThresholdDefinition,
    ThresholdRequest,
    TrainingDistribution,
    TrainingObservations,
)
from afre.research_datasets import DatasetEngine, Partition
from afre.schema import Artifact, require
from afre.serialization import canonical_json
from afre.statistical_models import DesignMatrix, ModelEngine, ModelFamily, PredictionScope
from afre.target_engine.market_data import TargetBar
from afre.target_engine.models import TargetVintage
from examples.feature_store_demo import clocks, source_vintage
from examples.research_dataset_demo import ResearchFixture, populate, split_definition
from examples.statistical_baselines_demo import baseline_spec
from examples.universe_demo import SECURITIES

A = TypeVar("A", bound=Artifact)


class ProbabilityDemoRepository(ProbabilisticRepository):
    """Synthetic held-out perturbation and comprehensive response-read guard."""

    def __init__(self, path: str | Path, heldout_scale: float = 1.0) -> None:
        self.deny_truth = False
        self.heldout_scale = heldout_scale
        super().__init__(path)

    def get(self, cls: type[A], identity: str) -> A:
        require(
            not self.deny_truth
            or cls not in (TargetVintage, TrainingObservations, DesignMatrix),
            "probabilistic forecast attempted response access",
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


@dataclass(frozen=True)
class ProbabilityDemo:
    fixture: ResearchFixture
    runs: tuple[ProbabilisticFitRun, ...]
    forecasts: tuple[tuple[ProbabilisticForecast, ...], ...]
    evaluations: tuple[ProbabilisticEvaluation, ...]


def probability_spec(
    point_id: str,
    fold_id: str,
    fixture: ResearchFixture,
    family: DistributionFamily,
    policy: ObservationPolicy = ObservationPolicy.POINT_MODEL_RESIDUALS,
) -> ProbabilisticModelSpec:
    target = next(
        t for t in fixture.definition.target_set.definitions if t.horizon.duration_ns == 5
    )
    return ProbabilisticModelSpec(
        point_id,
        family,
        policy,
        ResidualCentering.RAW,
        ScaleSpec(ScalePolicy.TRAIN_RESIDUAL_STD),
        QuantileDefinition((0.1, 0.5, 0.9)),
        ThresholdDefinition(())
        if family is DistributionFamily.QUANTILE_SET
        else ThresholdDefinition((ThresholdRequest(0.0, ThresholdComparison.GT),)),
        fold_id,
        target,
        40,
        0,
    )


def build_probability_demo(
    repo: ProbabilityDemoRepository, reverse: bool = False, validation_outlier: float = 1000.0
) -> ProbabilityDemo:
    fixture = populate(repo, reverse=reverse, validation_outlier=validation_outlier)
    research = DatasetEngine(repo)
    dataset = research.build_dataset(
        fixture.definition,
        tuple(reversed(fixture.requests)) if reverse else fixture.requests,
        100,
        100,
    )
    split = research.build_split(dataset.fingerprint, split_definition(fixture))
    state = research.fit_preprocessing(split.fold_ids[0], fixture.preprocessing)
    models = ModelEngine(repo)
    point = models.fit_model(
        baseline_spec(fixture, split, state, ModelFamily.RIDGE_REGRESSION), 40, 40, 40
    )
    unconditional = models.fit_model(
        baseline_spec(fixture, split, state, ModelFamily.UNCONDITIONAL_MEAN), 40, 40, 40
    )
    engine = ProbabilisticEngine(repo)
    specs = tuple(
        probability_spec(point.artifact_id, split.fold_ids[0], fixture, f)
        for f in DistributionFamily
    )
    specs = (
        *specs,
        probability_spec(
            unconditional.artifact_id,
            split.fold_ids[0],
            fixture,
            DistributionFamily.EMPIRICAL_RESIDUAL,
            ObservationPolicy.TRAIN_TARGETS,
        ),
    )
    runs = tuple(engine.fit_model(s, 40, 40, 40) for s in specs)
    with repo.read_snapshot(), repo.validation_cache():
        ids = tuple(
            s.fingerprint
            for s in repo.partition_samples(split.fold_ids[0], Partition.VALIDATION)
            if s.target_definition_id == specs[0].target.fingerprint
        )
    repo.deny_truth = True
    try:
        forecasts = tuple(
            engine.predict_samples(
                r.artifact_id,
                tuple(reversed(ids)) if reverse else ids,
                PredictionScope.VALIDATION,
            )
            for r in runs
        )
    finally:
        repo.deny_truth = False
    protocol = ProbabilisticEvaluationProtocol((QuantileInterval(0.1, 0.9),))
    evaluations = tuple(
        engine.evaluate(tuple(p.fingerprint for p in group), 100, 100, protocol)
        for group in forecasts
    )
    engine.compare_models(evaluations[0].fingerprint, evaluations[-1].fingerprint)
    return ProbabilityDemo(fixture, runs, forecasts, evaluations)


def probability_bytes(repo: ProbabilisticRepository, demo: ProbabilityDemo) -> tuple[str, ...]:
    values: list[Artifact] = [
        *demo.runs,
        *demo.evaluations,
        *(p for group in demo.forecasts for p in group),
    ]
    for run in demo.runs:
        values.extend(
            (
                repo.get_any(run.artifact_id),
                repo.get_any(run.distribution_id),
                repo.get_any(run.inputs.observations_id),
            )
        )
    return tuple(canonical_json(v) for v in values)


def main() -> None:
    with TemporaryDirectory(prefix="afre-probability-demo-") as directory:
        path = Path(directory) / "probability.sqlite"
        with ProbabilityDemoRepository(path) as repo:
            demo = build_probability_demo(repo)
            frozen = probability_bytes(repo, demo)
            engine = ProbabilisticEngine(repo)
            for run, group, evaluation in zip(
                demo.runs, demo.forecasts, demo.evaluations, strict=True
            ):
                spec = repo.get(ProbabilisticModelSpec, run.inputs.spec_id)
                print(
                    spec.family.value,
                    spec.observation_policy.value,
                    "TRAIN",
                    len(run.inputs.train_sample_ids),
                    "quantiles",
                    [(q.level, q.value) for q in group[0].quantiles],
                    "events",
                    [
                        (p.request.comparison.value, p.probability)
                        for p in group[0].threshold_probabilities
                    ],
                    "VALIDATION",
                    [
                        (s.name.value, s.value, s.state.value)
                        for s in evaluation.scores
                        if s.level is None and s.threshold is None
                    ],
                )
            audit = engine.forecast_audit(demo.forecasts[0][0].fingerprint)
            print("Bounded forecast lineage evidence", len(audit.evidence_ids))
            engine.model_audit(demo.evaluations[0].fingerprint)
            old = source_vintage(
                demo.fixture.preprocessing.normalization.feature,
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
                demo.fixture.definition, demo.fixture.requests, 100, 100
            )
            split = research.build_split(corrected.fingerprint, split_definition(demo.fixture))
            state = research.fit_preprocessing(split.fold_ids[0], demo.fixture.preprocessing)
            point = ModelEngine(repo).fit_model(
                baseline_spec(demo.fixture, split, state, ModelFamily.RIDGE_REGRESSION),
                40,
                40,
                40,
            )
            new = engine.fit_model(
                probability_spec(
                    point.artifact_id,
                    split.fold_ids[0],
                    demo.fixture,
                    DistributionFamily.EMPIRICAL_RESIDUAL,
                ),
                40,
                40,
                40,
            )
            assert new.artifact_id != demo.runs[0].artifact_id
            assert probability_bytes(repo, demo) == frozen
            original_states = [
                repo.get(TrainingDistribution, r.distribution_id) for r in demo.runs
            ]
            print(
                "Corrected upstream evidence gives new probabilistic identity", new.artifact_id
            )
        with ProbabilityDemoRepository(
            Path(directory) / "perturbed.sqlite", heldout_scale=100.0
        ) as changed:
            perturbed = build_probability_demo(changed, validation_outlier=1e8)
            for original, run in zip(original_states, perturbed.runs, strict=True):
                changed_state = changed.get(TrainingDistribution, run.distribution_id)
                assert (changed_state.values, changed_state.diagnostics) == (
                    original.values,
                    original.diagnostics,
                )
        with ProbabilisticRepository(path) as restarted:
            assert probability_bytes(restarted, demo) == frozen
            restarted.audit()
        print(
            "PASS: TRAIN-only uncertainty, response-free forecasts, proper scores, "
            "exact-sample comparison, "
            "held-out perturbation, corrected identity, bounded lineage "
            "and byte-identical restart; "
            "no calibration transformation or profitability claim"
        )


if __name__ == "__main__":
    main()

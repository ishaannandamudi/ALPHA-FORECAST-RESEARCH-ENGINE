"""Offline causal calibration: reserved samples, truth-free application and replay."""

from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TypeVar

from afre.calibration import (
    CalibratedForecast,
    CalibrationDriftSpec,
    CalibrationEngine,
    CalibrationFitRun,
    CalibrationMethod,
    CalibrationObservationSet,
    CalibrationPartition,
    CalibrationPartitionPolicy,
    CalibrationRepository,
    CalibrationRequest,
    CalibrationSpec,
    CalibrationState,
    DriftMetric,
)
from afre.probabilistic import (
    DistributionFamily,
    ProbabilisticEngine,
    ProbabilisticFitRun,
    ProbabilisticForecast,
    QuantileInterval,
    TrainingObservations,
)
from afre.research_datasets import DatasetEngine, Partition, SplitStrategy
from afre.research_datasets.samples import ResearchSample
from afre.schema import Artifact, ContractError, require
from afre.serialization import canonical_json
from afre.statistical_models import DesignMatrix, ModelEngine, ModelFamily, PredictionScope
from afre.target_engine.models import TargetVintage
from afre.time import TimeRange
from examples.probabilistic_demo import probability_spec
from examples.research_dataset_demo import populate, split_definition
from examples.statistical_baselines_demo import baseline_spec

A = TypeVar("A", bound=Artifact)


class CalibrationDemoRepository(CalibrationRepository):
    def __init__(self, path: str | Path) -> None:
        self.deny_truth = False
        super().__init__(path)

    def get(self, cls: type[A], identity: str) -> A:
        require(
            not self.deny_truth
            or cls
            not in (
                TargetVintage,
                TrainingObservations,
                DesignMatrix,
                CalibrationObservationSet,
            ),
            "calibration application attempted truth access",
        )
        return super().get(cls, identity)


@dataclass(frozen=True)
class CalibrationFixture:
    raw_run: ProbabilisticFitRun
    spec: CalibrationSpec
    requests: tuple[CalibrationRequest, ...]
    calibration_raw: tuple[ProbabilisticForecast, ...]
    deployment_raw: tuple[ProbabilisticForecast, ...]
    test_raw: tuple[ProbabilisticForecast, ...]


def build_calibration_fixture(
    repo: CalibrationRepository, reverse: bool = False, security_count: int = 8
) -> CalibrationFixture:
    f = populate(
        repo,
        reverse=reverse,
        missing=False,
        security_count=security_count,
        validation_outlier=40.0,
    )
    research = DatasetEngine(repo)
    dataset = research.build_dataset(
        f.definition, tuple(reversed(f.requests)) if reverse else f.requests, 100, 100
    )
    split_spec = replace(
        split_definition(f),
        strategy=SplitStrategy.FIXED_HOLDOUT,
        step_ns=0,
        fold_count=1,
        validation=TimeRange(40, 70),
        test=TimeRange(80, 90),
    )
    split = research.build_split(dataset.fingerprint, split_spec)
    preprocessing = research.fit_preprocessing(split.fold_ids[0], f.preprocessing)
    point = ModelEngine(repo).fit_model(
        baseline_spec(f, split, preprocessing, ModelFamily.UNCONDITIONAL_MEAN), 40, 40, 40
    )
    from afre.probabilistic.schema import ObservationPolicy

    raw_spec = probability_spec(
        point.artifact_id,
        split.fold_ids[0],
        f,
        DistributionFamily.EMPIRICAL_RESIDUAL,
        ObservationPolicy.TRAIN_TARGETS,
    )
    engine = ProbabilisticEngine(repo)
    raw_run = engine.fit_model(raw_spec, 40, 40, 40)
    with repo.read_snapshot(), repo.validation_cache():
        validation = tuple(
            s
            for s in repo.partition_samples(split.fold_ids[0], Partition.VALIDATION)
            if s.target_definition_id == raw_spec.target.fingerprint
        )
        test = tuple(
            s
            for s in repo.partition_samples(split.fold_ids[0], Partition.TEST)
            if s.target_definition_id == raw_spec.target.fingerprint
        )
    raw = engine.predict_samples(
        raw_run.artifact_id,
        tuple(s.fingerprint for s in validation),
        PredictionScope.VALIDATION,
    )
    calibration = tuple(p for p in raw if p.input.origin.timestamp_ns == 40)
    deployment = tuple(p for p in raw if p.input.origin.timestamp_ns >= 60)
    test_raw = engine.predict_samples(
        raw_run.artifact_id, tuple(s.fingerprint for s in test), PredictionScope.TEST
    )
    with repo.read_snapshot():
        requests = tuple(
            CalibrationRequest(
                p.fingerprint,
                repo.resolve(ResearchSample, p.input.sample_id or "").target_id or "",
            )
            for p in calibration
        )
    partition = CalibrationPartition(
        CalibrationPartitionPolicy.DEDICATED_CALIBRATION,
        split.fold_ids[0],
        tuple(p.input.sample_id or "" for p in calibration),
        TimeRange(40, 50),
    )
    spec = CalibrationSpec(
        raw_run.artifact_id,
        raw_spec.fingerprint,
        raw_spec.target,
        CalibrationMethod.IDENTITY,
        partition,
        55,
        3,
        raw_spec.thresholds,
        raw_spec.quantiles,
        interval=QuantileInterval(0.1, 0.9),
    )
    return CalibrationFixture(raw_run, spec, requests, calibration, deployment, test_raw)


def method_spec(fixture: CalibrationFixture, method: CalibrationMethod) -> CalibrationSpec:
    spec = fixture.spec
    if method in (
        CalibrationMethod.CONFORMAL_ABSOLUTE_RESIDUAL,
        CalibrationMethod.ROLLING_CONFORMAL,
    ):
        spec = replace(
            spec,
            miscoverage_alpha=0.2,
            method=method,
            partition=replace(
                spec.partition, policy=CalibrationPartitionPolicy.ROLLING_PAST, rolling_count=8
            )
            if method is CalibrationMethod.ROLLING_CONFORMAL
            else spec.partition,
        )
        return spec
    return replace(spec, method=method)


def corrected_calibration_truth(
    repo: CalibrationRepository, target_id: str, available_ns: int = 100, factor: float = 1.1
) -> str:
    """Recompute a real later source-price correction with later AFRE clocks."""
    from afre.target_engine import TargetEngine
    from afre.target_engine.builders import build_vintage
    from afre.target_engine.market_data import TargetBar, TargetSourceBuild
    from examples.feature_store_demo import clocks

    original = repo.get(TargetVintage, target_id)
    build = repo.get(TargetSourceBuild, original.source_build_id)
    endpoint = repo.get(TargetBar, original.endpoint_bar_id or "")
    assert endpoint.close is not None
    correction = replace(
        endpoint,
        close=endpoint.close * factor,
        clocks=clocks(available_ns),
        predecessor_id=endpoint.fingerprint,
    )
    with repo.transaction():
        repo.put(correction)
    source = TargetEngine(repo).freeze_source(build.source, build.calendar, available_ns)
    truth = build_vintage(
        repo, original.definition, original.origin, source, clocks(available_ns), True
    )
    with repo.transaction():
        repo.put(truth)
    assert truth.value != original.value
    return truth.fingerprint


def main() -> None:
    with TemporaryDirectory(prefix="afre-calibration-demo-") as directory:
        path = Path(directory) / "calibration.sqlite"
        with CalibrationDemoRepository(path) as repo:
            fixture = build_calibration_fixture(repo)
            engine = CalibrationEngine(repo)
            raw_bytes = tuple(
                canonical_json(p)
                for p in (*fixture.calibration_raw, *fixture.deployment_raw, *fixture.test_raw)
            )
            runs: list[CalibrationFitRun] = []
            calibrated: list[CalibratedForecast] = []
            evaluations = []
            for method in CalibrationMethod:
                run = engine.fit(method_spec(fixture, method), fixture.requests, 55, 55, 55)
                runs.append(run)
                repo.deny_truth = True
                forecasts = engine.apply_batch(
                    run.state_id, tuple(p.fingerprint for p in fixture.deployment_raw)
                )
                repo.deny_truth = False
                calibrated.extend(forecasts)
                evaluation = engine.evaluate(tuple(p.fingerprint for p in forecasts), 75, 75)
                evaluations.append(evaluation)
                comparison = engine.compare(
                    evaluation.raw_evaluation_id, evaluation.fingerprint
                )
                from afre.probabilistic import ScoreName

                aggregate_deltas = {
                    d.raw.name.value: d.delta
                    for d in comparison.deltas
                    if d.raw.name in (ScoreName.BRIER, ScoreName.PINBALL)
                    and d.raw.level is None
                    and d.raw.threshold is None
                }
                print(
                    method.value,
                    "samples",
                    len(run.inputs.sample_ids),
                    "Brier/pinball deltas",
                    aggregate_deltas,
                    "coverage-error delta",
                    comparison.coverage_error_delta,
                    "width delta",
                    comparison.interval_width_delta,
                )
            # TEST scope cannot fit, even with an explicit reservation attempt.
            test = fixture.test_raw[0]
            with repo.read_snapshot():
                sample = repo.resolve(ResearchSample, test.input.sample_id or "")
            try:
                bad = replace(
                    fixture.spec,
                    partition=replace(
                        fixture.spec.partition,
                        reserved_sample_ids=(sample.fingerprint,),
                        origin_range=TimeRange(80, 90),
                    ),
                    cutoff_ns=100,
                    minimum_samples=1,
                )
                engine.fit(
                    bad,
                    (CalibrationRequest(test.fingerprint, sample.target_id or ""),),
                    100,
                    100,
                    100,
                )
                raise AssertionError("TEST calibration was admitted")
            except ContractError:
                print("TEST fitting rejected")
            corrected_calibration_truth(repo, sample.target_id or "", 110, 10.0)
            assert engine.fit(fixture.spec, fixture.requests, 55, 55, 55) == runs[0]
            print("Changed TEST outcomes leave calibration state unchanged")
            try:
                engine.apply(runs[0].state_id, fixture.calibration_raw[0].fingerprint, 55)
                raise AssertionError("late calibration availability was admitted")
            except ContractError:
                print("Calibration availability enforced")
            drift = engine.diagnose_drift(
                CalibrationDriftSpec(1, 3, DriftMetric.ECE, 0.25), (evaluations[1].fingerprint,)
            )
            print("Drift diagnostic", drift.windows[-1].state.value)
            first = fixture.requests[0]
            corrected_id = corrected_calibration_truth(repo, first.target_id)
            old_state = canonical_json(repo.get(CalibrationState, runs[0].state_id))
            corrected_requests = tuple(
                replace(r, target_id=corrected_id) if r == first else r
                for r in fixture.requests
            )
            corrected_spec = replace(fixture.spec, cutoff_ns=100)
            new_run = engine.fit(corrected_spec, corrected_requests, 100, 100, 100)
            assert new_run.state_id != runs[0].state_id
            assert canonical_json(repo.get(CalibrationState, runs[0].state_id)) == old_state
            assert (
                tuple(
                    canonical_json(repo.get(ProbabilisticForecast, p.fingerprint))
                    for p in (
                        *fixture.calibration_raw,
                        *fixture.deployment_raw,
                        *fixture.test_raw,
                    )
                )
                == raw_bytes
            )
            audit = engine.calibration_audit(calibrated[0].fingerprint)
            engine.calibration_audit(evaluations[0].fingerprint)
            frozen = tuple(
                canonical_json(repo.get_any(i))
                for i in (
                    runs[0].state_id,
                    calibrated[0].fingerprint,
                    evaluations[0].fingerprint,
                )
            )
            print(
                "Corrected truth gives new state; old state/raw bytes preserved; lineage nodes",
                len(audit.evidence_ids),
            )
        with CalibrationRepository(path) as restarted:
            assert (
                tuple(
                    canonical_json(restarted.get_any(i))
                    for i in (
                        runs[0].state_id,
                        calibrated[0].fingerprint,
                        evaluations[0].fingerprint,
                    )
                )
                == frozen
            )
            restarted.audit()
        print(
            "PASS: causal reserved calibration, independent evaluation, "
            "immutable raw forecasts, target-free application and "
            "byte-identical restart; no selection or profitability claim"
        )


if __name__ == "__main__":
    main()

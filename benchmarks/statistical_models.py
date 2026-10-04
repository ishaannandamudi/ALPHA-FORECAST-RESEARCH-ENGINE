"""Offline bounded model pipeline and separate known-coefficient dense solver profile."""

import cProfile
import io
import json
import math
import pstats
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from afre.research_datasets import DatasetBounds, DatasetEngine, Partition
from afre.statistical_models import (
    ModelBounds,
    ModelEngine,
    ModelFamily,
    ModelRepository,
    PredictionScope,
)
from afre.statistical_models.elastic import coordinate_descent
from afre.statistical_models.linear_algebra import dot, householder_qr
from examples.research_dataset_demo import populate, split_definition
from examples.statistical_baselines_demo import baseline_spec


def numerical_workload(rows: int = 4000, features: int = 16) -> dict[str, object]:
    require_bounds = ModelBounds()
    assert rows <= require_bounds.samples and features <= require_bounds.features
    assert rows * features <= require_bounds.dense_cells
    x = tuple(
        (1.0, *(math.sin((i + 1) * (j + 1) * 0.013) for j in range(features)))
        for i in range(rows)
    )
    expected = (0.3, *(0.02 * (j + 1) * (-1 if j % 2 else 1) for j in range(features)))
    y = tuple(dot(row, expected) for row in x)
    timings = {}
    started = perf_counter()
    ols = householder_qr(x, y, 1e-12, 1e12)
    timings["ols"] = perf_counter() - started
    penalty = 2.0
    augmented = tuple(
        tuple(math.sqrt(penalty) if k == j else 0.0 for k in range(features + 1))
        for j in range(1, features + 1)
    )
    started = perf_counter()
    ridge = householder_qr((*x, *augmented), (*y, *((0.0,) * features)), 1e-12, 1e12)
    timings["ridge"] = perf_counter() - started
    started = perf_counter()
    elastic = coordinate_descent(x, y, 0.1, penalty, 1000, 1e-10, True)
    timings["elastic_net"] = perf_counter() - started
    error = max(abs(a - b) for a, b in zip(ols.coefficients, expected, strict=True))
    assert error < 1e-11 and elastic.converged
    # Independently check augmented ridge stationarity, not a timing-only claim.
    residual = tuple(
        truth - dot(row, ridge.coefficients) for row, truth in zip(x, y, strict=True)
    )
    stationarity = max(
        abs(
            sum(row[j] * r for row, r in zip(x, residual, strict=True))
            - (0.0 if j == 0 else penalty * ridge.coefficients[j])
        )
        for j in range(features + 1)
    )
    assert stationarity < 1e-8
    return {
        "rows": rows,
        "features": features,
        "known_coefficient_max_abs_error": error,
        "ridge_max_stationarity_residual": stationarity,
        "qr_rank": ols.rank,
        "qr_diagonal_condition_proxy": ols.condition_proxy,
        "elastic_iterations": elastic.iterations,
        "elastic_kkt_residual": elastic.kkt_residual,
        "seconds": {name: round(value, 6) for name, value in timings.items()},
        "scope": "Separate dense numerical workload; no registry throughput claim",
    }


def run() -> dict[str, object]:
    timings: dict[str, float] = {}
    with TemporaryDirectory(prefix="afre-model-profile-") as directory:
        path = Path(directory) / "models.sqlite"
        with ModelRepository(
            path,
            ModelBounds(serialized_bytes=16 * 1024 * 1024),
            DatasetBounds(serialized_bytes=16 * 1024 * 1024),
        ) as repo:
            started = perf_counter()
            fixture = populate(repo, security_count=16)
            research = DatasetEngine(repo)
            dataset = research.build_dataset(fixture.definition, fixture.requests, 100, 100)
            split = research.build_split(dataset.fingerprint, split_definition(fixture))
            timings["synthetic_upstream_and_dataset"] = perf_counter() - started
            engine = ModelEngine(repo)
            rows = []
            artifacts: list[str] = []
            predictions: list[str] = []
            evaluations: list[str] = []
            for fold_id in split.fold_ids[:2]:
                fold = repo.resolve_fold(fold_id)
                state = research.fit_preprocessing(fold_id, fixture.preprocessing)
                with repo.read_snapshot(), repo.validation_cache():
                    target_id = next(
                        t.fingerprint
                        for t in fixture.definition.target_set.definitions
                        if t.horizon.duration_ns == 5
                    )
                    samples = tuple(
                        s.fingerprint
                        for s in repo.partition_samples(fold_id, Partition.VALIDATION)
                        if s.target_definition_id == target_id
                    )
                for family in (
                    ModelFamily.UNCONDITIONAL_MEAN,
                    ModelFamily.LINEAR_REGRESSION,
                    ModelFamily.RIDGE_REGRESSION,
                ):
                    spec = replace(
                        baseline_spec(fixture, split, state, family), fold_id=fold_id
                    )
                    run = engine.fit_model(
                        spec,
                        fold.training_cutoff_ns,
                        fold.training_cutoff_ns,
                        fold.training_cutoff_ns,
                    )
                    rows.append(
                        {
                            "family": family.value,
                            "fold": fold.ordinal,
                            "train_rows": len(run.inputs.train_sample_ids),
                            "seconds": {
                                k: round(v, 6) for k, v in engine.last_fit_timings.items()
                            },
                        }
                    )
                    artifacts.append(run.artifact_id)
                    started = perf_counter()
                    group = engine.predict_samples(
                        run.artifact_id, samples, PredictionScope.VALIDATION
                    )
                    timings["prediction"] = (
                        timings.get("prediction", 0.0) + perf_counter() - started
                    )
                    predictions.extend(p.fingerprint for p in group)
                    started = perf_counter()
                    evaluation = engine.evaluate(tuple(p.fingerprint for p in group), 100, 100)
                    timings["evaluation_and_persistence"] = (
                        timings.get("evaluation_and_persistence", 0.0)
                        + perf_counter()
                        - started
                    )
                    evaluations.append(evaluation.fingerprint)
            started = perf_counter()
            engine.model_audit(artifacts[0])
            engine.prediction_audit(predictions[0])
            timings["lineage_audits_and_persistence"] = perf_counter() - started
        started = perf_counter()
        with ModelRepository(
            path,
            ModelBounds(serialized_bytes=16 * 1024 * 1024),
            DatasetBounds(serialized_bytes=16 * 1024 * 1024),
        ) as reopened:
            for identity in (*artifacts, *predictions, *evaluations):
                assert reopened.get_any(identity).fingerprint == identity
        timings["restart"] = perf_counter() - started
        storage = path.stat().st_size
    return {
        "pipeline": {
            "securities": 16,
            "origins": 8,
            "dataset_samples": len(dataset.sample_ids),
            "features": 1,
            "folds": 2,
            "fit_runs": rows,
            "predictions": len(predictions),
            "evaluations": len(evaluations),
            "storage_bytes": storage,
            "serialized_byte_budget": 16 * 1024 * 1024,
            "seconds": {k: round(v, 6) for k, v in timings.items()},
        },
        "numerical": numerical_workload(),
        "scope": "Synthetic local measurements; no production SLA",
    }


def main() -> None:
    profile = cProfile.Profile()
    profile.enable()
    result = run()
    profile.disable()
    output = io.StringIO()
    pstats.Stats(profile, stream=output).sort_stats("cumulative").print_stats(20)
    print(json.dumps(result, sort_keys=True, indent=2))
    print(output.getvalue())


if __name__ == "__main__":
    main()

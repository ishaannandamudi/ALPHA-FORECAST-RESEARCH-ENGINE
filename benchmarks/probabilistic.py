"""Offline multi-horizon store profile and separate 4,000-residual numerical workload."""

import cProfile
import hashlib
import io
import json
import math
import pstats
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from afre.probabilistic import (
    DistributionFamily as F,
)
from afre.probabilistic import (
    DistributionParameters,
    ProbabilisticEngine,
    ProbabilisticEvaluationProtocol,
    ProbabilisticModelSpec,
    ProbabilisticRepository,
    QuantileInterval,
    ThresholdComparison,
    ThresholdRequest,
    TrainingObservation,
    TrainingObservations,
    quantile,
    threshold_probability,
)
from afre.probabilistic.distributions import normal_cdf
from afre.probabilistic.fitting import distribution_for
from afre.probabilistic.quantiles import empirical_quantile, normal_quantile
from afre.probabilistic.scoring import (
    empirical_crps,
    gaussian_crps,
    negative_log_likelihood,
    pinball_loss,
)
from afre.research_datasets import DatasetEngine, Partition
from afre.statistical_models import ModelEngine, ModelFamily, PredictionScope
from examples.probabilistic_demo import probability_spec
from examples.research_dataset_demo import populate, split_definition
from examples.statistical_baselines_demo import baseline_spec


def numerical_validation() -> dict[str, float]:
    normal = DistributionParameters(F.GAUSSIAN_LOCATION_SCALE, 0.0, 1.0)
    cdf_refs = (
        (0.0, 0.5),
        (1.0, 0.8413447460685429),
        (-1.0, 0.15865525393145707),
        (-8.0, 6.220960574271784e-16),
    )
    inverse_refs = (
        (0.1, -1.2815515655446004),
        (0.975, 1.959963984540054),
        (1e-12, -7.034483825301131),
    )
    samples = (-2.0, -1.0, 0.0, 1.0, 2.0)
    empirical = DistributionParameters(F.EMPIRICAL_RESIDUAL, 0.0, math.sqrt(2), samples)
    truth = 0.7
    pairwise = (
        sum(abs(a - truth) for a in samples) / 5
        - sum(abs(a - b) for a in samples for b in samples) / 50
    )

    def integral(low: float, high: float, left: bool) -> float:
        n = 4000
        step = (high - low) / n
        values = [
            (normal_cdf(low + i * step) if left else normal_cdf(-low - i * step)) ** 2
            for i in range(n + 1)
        ]
        return (
            step
            / 3
            * (
                values[0]
                + values[-1]
                + 4 * math.fsum(values[1:-1:2])
                + 2 * math.fsum(values[2:-1:2])
            )
        )

    quadrature = integral(-12.0, truth, True) + integral(truth, 12.0, False)
    return {
        "normal_cdf_max_abs_error": max(abs(normal_cdf(z) - ref) for z, ref in cdf_refs),
        "inverse_normal_max_abs_error": max(
            abs(normal_quantile(q) - ref) for q, ref in inverse_refs
        ),
        "gaussian_crps_fixture_abs_error": abs(
            gaussian_crps(normal, 0.0) - 0.23369497725510913
        ),
        "gaussian_crps_quadrature_abs_error": abs(gaussian_crps(normal, truth) - quadrature),
        "empirical_crps_pairwise_abs_error": abs(empirical_crps(empirical, truth) - pairwise),
        "type7_quantile_max_abs_error": max(
            abs(empirical_quantile(samples, q) - ref)
            for q, ref in ((0.1, -1.6), (0.5, 0.0), (0.9, 1.6))
        ),
        "threshold_probability_max_abs_error": max(
            abs(threshold_probability(empirical, ThresholdRequest(0.0, c)) - ref)
            for c, ref in (
                (ThresholdComparison.GT, 0.4),
                (ThresholdComparison.GE, 0.6),
                (ThresholdComparison.LT, 0.4),
                (ThresholdComparison.LE, 0.6),
            )
        ),
        "gaussian_threshold_abs_error": abs(
            threshold_probability(normal, ThresholdRequest(1.0, ThresholdComparison.GT))
            - 0.15865525393145707
        ),
    }


def residual_workload(
    spec: ProbabilisticModelSpec, matrix_id: str, rows: int = 4000
) -> dict[str, object]:
    def identity(domain: str, i: int) -> str:
        return f"afre.{domain}:1.0:" + hashlib.sha256(str(i).encode()).hexdigest()

    observations = TrainingObservations(
        spec.fingerprint,
        matrix_id,
        tuple(
            TrainingObservation(
                identity("r_sample", i),
                identity("target_vintage", i),
                10,
                identity("instrument", i),
                math.sin(i * 0.17) * 0.03 + 0.001,
                0.0,
                math.sin(i * 0.17) * 0.03 + 0.001,
                40,
            )
            for i in range(rows)
        ),
    )
    started = perf_counter()
    state = distribution_for(spec, observations, 40)
    fit = perf_counter() - started
    empirical = DistributionParameters(
        F.EMPIRICAL_RESIDUAL, 0.01, state.diagnostics.estimated_scale, state.values
    )
    gaussian = DistributionParameters(
        F.GAUSSIAN_LOCATION_SCALE,
        0.01 + state.diagnostics.distribution_mean,
        state.diagnostics.population_stddev,
    )
    levels = (0.01, 0.1, 0.25, 0.5, 0.75, 0.9, 0.99)
    started = perf_counter()
    for _ in range(1000):
        for distribution in (empirical, gaussian):
            for q in levels:
                quantile(distribution, q)
    quantiles = perf_counter() - started
    started = perf_counter()
    for _ in range(1000):
        for distribution in (empirical, gaussian):
            for c in (-0.05, 0.0, 0.05):
                threshold_probability(distribution, ThresholdRequest(c, ThresholdComparison.GT))
    probabilities = perf_counter() - started
    started = perf_counter()
    scores = []
    for i in range(200):
        truth = math.sin(i * 0.23) * 0.03
        scores.append(
            (
                empirical_crps(empirical, truth),
                gaussian_crps(gaussian, truth),
                negative_log_likelihood(gaussian, truth),
                pinball_loss(0.5, quantile(empirical, 0.5), truth),
            )
        )
    scoring = perf_counter() - started
    assert all(math.isfinite(v) for score in scores for v in score)
    return {
        "TRAIN_residuals": rows,
        "distribution_families": 2,
        "quantile_queries": 14000,
        "threshold_queries": 6000,
        "paired_truths": 200,
        "seconds": {
            "residual_fit": fit,
            "quantile_queries": quantiles,
            "probability_queries": probabilities,
            "proper_scoring": scoring,
        },
        "scope": (
            "Separate synthetic numerical kernels; "
            "not equivalent end-to-end registry throughput"
        ),
    }


def run() -> dict[str, object]:
    timings: dict[str, float] = {}
    fits = []
    saved: list[str] = []
    with TemporaryDirectory(prefix="afre-probability-profile-") as directory:
        path = Path(directory) / "probability.sqlite"
        with ProbabilisticRepository(path) as repo:
            started = perf_counter()
            fixture = populate(repo, security_count=8)
            research = DatasetEngine(repo)
            dataset = research.build_dataset(fixture.definition, fixture.requests, 100, 100)
            split = research.build_split(dataset.fingerprint, split_definition(fixture))
            state = research.fit_preprocessing(split.fold_ids[0], fixture.preprocessing)
            timings["upstream_and_research"] = perf_counter() - started
            for target in fixture.definition.target_set.definitions:
                bs = replace(
                    baseline_spec(fixture, split, state, ModelFamily.RIDGE_REGRESSION),
                    target=target,
                )
                point = ModelEngine(repo).fit_model(bs, 40, 40, 40)
                with repo.read_snapshot(), repo.validation_cache():
                    ids = tuple(
                        s.fingerprint
                        for s in repo.partition_samples(bs.fold_id, Partition.VALIDATION)
                        if s.target_definition_id == target.fingerprint
                    )
                for family in (F.EMPIRICAL_RESIDUAL, F.GAUSSIAN_LOCATION_SCALE):
                    engine = ProbabilisticEngine(repo)
                    spec = replace(
                        probability_spec(point.artifact_id, bs.fold_id, fixture, family),
                        target=target,
                    )
                    fit = engine.fit_model(spec, 40, 40, 40)
                    fits.append(
                        {
                            "family": family.value,
                            "horizon_ns": target.horizon.duration_ns,
                            "TRAIN": len(fit.inputs.train_sample_ids),
                            "seconds": engine.last_fit_timings,
                        }
                    )
                    started = perf_counter()
                    forecasts = engine.predict_samples(
                        fit.artifact_id, ids, PredictionScope.VALIDATION
                    )
                    timings["forecast_and_persistence"] = (
                        timings.get("forecast_and_persistence", 0) + perf_counter() - started
                    )
                    started = perf_counter()
                    evaluation = engine.evaluate(
                        tuple(p.fingerprint for p in forecasts),
                        100,
                        100,
                        ProbabilisticEvaluationProtocol((QuantileInterval(0.1, 0.9),)),
                    )
                    timings["evaluation_and_persistence"] = (
                        timings.get("evaluation_and_persistence", 0) + perf_counter() - started
                    )
                    saved.extend(
                        (
                            fit.artifact_id,
                            evaluation.fingerprint,
                            *(p.fingerprint for p in forecasts),
                        )
                    )
            started = perf_counter()
            engine.forecast_audit(forecasts[0].fingerprint)
            timings["lineage_audit_and_persistence"] = perf_counter() - started
            numerical = residual_workload(spec, fit.inputs.matrix_id)
            frozen = tuple(repo.get_any(i).fingerprint for i in saved)
        started = perf_counter()
        with ProbabilisticRepository(path) as reopened:
            assert tuple(reopened.get_any(i).fingerprint for i in saved) == frozen
        timings["restart"] = perf_counter() - started
        size = path.stat().st_size
    return {
        "pipeline": {
            "securities": 8,
            "dataset_samples": len(dataset.sample_ids),
            "horizons": 2,
            "fits": fits,
            "stored_forecasts": len(saved) - 8,
            "storage_bytes": size,
            "seconds": timings,
        },
        "residual_numerical_workload": numerical,
        "numerical_validation": numerical_validation(),
        "scope": "Synthetic local reference measurements; no production SLA",
    }


def main() -> None:
    profile = cProfile.Profile()
    profile.enable()
    result = run()
    profile.disable()
    print(json.dumps(result, sort_keys=True, indent=2))
    output = io.StringIO()
    pstats.Stats(profile, stream=output).sort_stats("cumulative").print_stats(20)
    print(output.getvalue())


if __name__ == "__main__":
    main()

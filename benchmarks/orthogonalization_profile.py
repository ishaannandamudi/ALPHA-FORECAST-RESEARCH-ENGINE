"""Bounded offline repository workflow and separately identified arithmetic kernel workload."""

import json
import math
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import TypeVar

from afre.orthogonalization import OrthogonalizationEngine, OrthogonalizationRepository
from afre.orthogonalization.projection import numeric, solve
from afre.research_datasets.schema import Partition
from afre.serialization import canonical_json
from afre.statistical_models.metrics import correlation
from afre.statistical_models.schema import MetricName
from examples.orthogonalization_fixture import build_fixture
from examples.orthogonalization_oracles import (
    metrics,
    ols,
    pearson,
    predict,
    spearman,
    variance,
)

T = TypeVar("T")


def timed(call: Callable[[], T]) -> tuple[T, float]:
    start = perf_counter()
    result = call()
    return result, perf_counter() - start


def profile() -> dict[str, object]:
    with TemporaryDirectory(prefix="afre-orthogonal-profile-") as directory:
        path = Path(directory) / "profile.sqlite"
        with OrthogonalizationRepository(path) as repo:
            f, build_seconds = timed(lambda: build_fixture(repo))
            e = OrthogonalizationEngine(repo)
            train = f.partition(Partition.TRAIN)
            rows, alignment_seconds = timed(
                lambda: tuple(e.align(f.spec, r.observation_ids) for r in f.rows)
            )
            model, projection_seconds = timed(
                lambda: e.fit(f.spec, tuple(r.fingerprint for r in train), 40)
            )
            vals, application_seconds = timed(
                lambda: tuple(
                    e.residual(model.fingerprint, r.fingerprint, r.origin.timestamp_ns)
                    for r in rows
                    if r.partition is Partition.VALIDATION
                )
            )
            _, matrix_seconds = timed(
                lambda: e.matrix(f.spec.fingerprint, tuple(r.fingerprint for r in train), 40)
            )
            _, partial_seconds = timed(
                lambda: e.partial(
                    tuple(v.fingerprint for v in vals), tuple(v.fingerprint for v in vals), 100
                )
            )
            pair, target_fit_seconds = timed(lambda: e.fit_target_models(model.fingerprint, 40))
            evaluation, evaluation_seconds = timed(
                lambda: e.evaluate(
                    tuple(v.fingerprint for v in vals), 100, 100, pair.fingerprint, True
                )
            )
            audit, audit_seconds = timed(lambda: e.audit_lineage(evaluation.fingerprint))
            _, persistence_seconds = timed(lambda: e._publish((evaluation,)))
            identities = tuple(
                i[0]
                for i in repo._connection.execute(
                    "SELECT fingerprint FROM ort_artifacts ORDER BY fingerprint"
                )
            )
            before = tuple(canonical_json(repo.get_any(i)) for i in identities)
            bytes_payload = repo._connection.execute(
                "SELECT sum(length(payload)) FROM ort_artifacts"
            ).fetchone()[0]
            x = tuple(tuple(numeric(a) for a in r.references) for r in train)
            y = tuple(numeric(r.candidate) for r in train)
            oracle = ols(x, y)
            coefficient_error = max(
                abs(a - b)
                for a, b in zip((model.intercept, *model.coefficients), oracle, strict=True)
            )
            residual_error = max(
                abs(numeric(v.residual) - (numeric(v.raw_candidate) - numeric(v.projected)))
                for v in vals
            )
            raw = tuple(numeric(v.raw_candidate) for v in vals)
            residual = tuple(numeric(v.residual) for v in vals)
            ratio_error = abs(
                numeric(evaluation.residual_variance_ratio) - variance(residual) / variance(raw)
            )
            corr_error = abs(
                numeric(evaluation.raw_reference_correlations[0].value)
                - pearson(
                    raw,
                    tuple(
                        numeric(r.references[0])
                        for r in rows
                        if r.partition is Partition.VALIDATION
                    ),
                )
            )
            raw_by_sample = {v.sample_id: v for v in vals}
            ordered_raw = tuple(
                numeric(raw_by_sample[k].raw_candidate) for k in evaluation.sample_ids
            )
            ordered_residual = tuple(
                numeric(raw_by_sample[k].residual) for k in evaluation.sample_ids
            )
            ordered_prediction = tuple(
                numeric(raw_by_sample[k].projected) for k in evaluation.sample_ids
            )
            row_by_sample = {r.sample_id: r for r in rows}
            xheld = tuple(
                tuple(numeric(a) for a in row_by_sample[k].references)
                for k in evaluation.sample_ids
            )
            train_residual = tuple(
                numeric(r.candidate)
                - model.intercept
                - sum(a * b for a, b in zip(v, model.coefficients, strict=True))
                for r, v in zip(train, x, strict=True)
            )
            bcoef = ols(x, pair.truths)
            acoef = ols(
                tuple((*v, u) for v, u in zip(x, train_residual, strict=True)), pair.truths
            )
            bp = predict(xheld, bcoef)
            ap = predict(
                tuple((*v, u) for v, u in zip(xheld, ordered_residual, strict=True)), acoef
            )
            deltas = tuple(
                a - b
                for a, b in zip(
                    metrics(ap, evaluation.truths), metrics(bp, evaluation.truths), strict=True
                )
            )
            incremental_error = max(
                abs(numeric(m.value) - d)
                for m, d in zip(evaluation.incremental_metrics[:4], deltas, strict=True)
            )
            partial_error = abs(
                numeric(evaluation.partial_target_correlations[0].value)
                - pearson(
                    ordered_residual,
                    tuple(a - b for a, b in zip(evaluation.truths, bp, strict=True)),
                )
            )
            spearman_error = abs(
                numeric(evaluation.raw_target_correlations[1].value)
                - spearman(ordered_raw, evaluation.truths)
            )
            r_squared_error = abs(
                numeric(
                    next(
                        m.value
                        for m in evaluation.projection_metrics
                        if m.name is MetricName.R_SQUARED
                    )
                )
                - metrics(ordered_prediction, ordered_raw)[3]
            )
            expected_vif = 1 / (
                1 - pearson(tuple(v[0] for v in x), tuple(v[1] for v in x)) ** 2
            )
            vif_error = max(abs(numeric(v) - expected_vif) for v in model.vif)
            windows = tuple(
                e.evaluate(
                    tuple(v.fingerprint for v in vals if v.origin.timestamp_ns == at), 100, 100
                ).fingerprint
                for at in (50, 60)
            )
            stability = e.stability(windows, 100)
            stability_error = max(abs(a - b) for a, b in stability.coefficient_ranges)
            width, count, candidates = 12, 2000, 8
            design = tuple(
                tuple(math.cos((i + 0.5) * (j + 1) * math.pi / count) for j in range(width))
                for i in range(count)
            )
            responses = tuple(
                tuple(
                    1.0
                    + sum((j + 1) * v / 10 for j, v in enumerate(r))
                    + 0.1 * math.sin((i + 1) * (k + 1))
                    for i, r in enumerate(design)
                )
                for k in range(candidates)
            )
            fits, kernel_fit = timed(lambda: tuple(solve(f.spec, design, y) for y in responses))
            _, kernel_correlation = timed(
                lambda: tuple(
                    tuple(correlation(y, tuple(r[j] for r in design)) for j in range(width))
                    for y in responses
                )
            )
            _, kernel_residual = timed(
                lambda: tuple(
                    tuple(
                        yv - a - sum(v * b for v, b in zip(r, coef, strict=True))
                        for r, yv in zip(design, y, strict=True)
                    )
                    for y, (a, coef, _, _) in zip(responses, fits, strict=True)
                )
            )

        def restart() -> None:
            with OrthogonalizationRepository(path) as reopened:
                assert tuple(canonical_json(reopened.get_any(i)) for i in identities) == before

        _, restart_seconds = timed(restart)
        return {
            "engine_version": "0.17.0",
            "orthogonalization_schema": "1.0",
            "store_schema": "1.16",
            "sqlite_user_version": 17,
            "offline": True,
            "production_sla": False,
            "causal_workflow": {
                "train_rows": len(train),
                "validation_rows": len(vals),
                "test_rows": len(f.partition(Partition.TEST)),
                "references": len(f.spec.references),
                "artifacts": len(identities),
                "audit_nodes": len(audit.node_ids),
                "timings_seconds": {
                    "upstream_fixture_and_build": build_seconds,
                    "alignment": alignment_seconds,
                    "projection": projection_seconds,
                    "residual_application": application_seconds,
                    "correlation_matrix": matrix_seconds,
                    "partial_correlation": partial_seconds,
                    "target_model_fit": target_fit_seconds,
                    "evaluation": evaluation_seconds,
                    "audit": audit_seconds,
                    "idempotent_persistence": persistence_seconds,
                    "restart_replay": restart_seconds,
                },
            },
            "kernel_only_workload": {
                "causal_repository_admission": False,
                "rows": count,
                "references": width,
                "supplied_candidates": candidates,
                "timings_seconds": {
                    "qr_projection": kernel_fit,
                    "candidate_reference_correlations": kernel_correlation,
                    "residual_application": kernel_residual,
                },
            },
            "storage": {
                "orthogonalization_payload_bytes": bytes_payload,
                "whole_registry_bytes": path.stat().st_size,
            },
            "maximum_numerical_errors": {
                "coefficient": coefficient_error,
                "residual": residual_error,
                "variance_ratio": ratio_error,
                "pearson": corr_error,
                "spearman": spearman_error,
                "partial_target_correlation": partial_error,
                "r_squared": r_squared_error,
                "vif": vif_error,
                "incremental_metric": incremental_error,
                "stability_coefficient_range": stability_error,
            },
            "limitations": [
                "synthetic offline workload",
                "kernel rows are arithmetic fixtures, not admitted causal TRAIN rows",
                "hardware-specific timings",
                "no production SLA",
                "no profitability inference",
            ],
        }


def main() -> None:
    result = profile()
    destination = Path(__file__).resolve().parents[1] / "docs/orthogonalization-profile.json"
    destination.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

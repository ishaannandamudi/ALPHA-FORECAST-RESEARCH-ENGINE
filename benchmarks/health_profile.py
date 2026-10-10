"""Bounded offline wall-clock profile; synthetic measurements are not a production SLA."""

import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from afre.fusion import FusionEngine
from afre.health import HealthDiagnostic as D
from afre.health import HealthEngine, HealthObservation, HealthRepository
from afre.health.evaluation import admitted, metric_for, snapshot_for
from afre.health.rules import classify
from examples.health_fixture import build_health_fixture, health_spec
from examples.health_native import parameter_monitor
from examples.health_oracles import numerical_errors


def profile(directory: Path) -> dict[str, object]:
    path = directory / "profile.sqlite"
    timings: dict[str, float] = {}
    started = perf_counter()
    with HealthRepository(path) as repo:
        f = build_health_fixture(repo)
        e = HealthEngine(repo)
        timings["fixture_seconds"] = perf_counter() - started
        started = perf_counter()
        refs = tuple(e.monitor(i) for i in (f.artifact_id, f.probability_reference.artifact_id))
        timings["source_resolution_seconds"] = perf_counter() - started
        column = repo.get(HealthObservation, f.input_ids[0]).values[0][0]
        specs = []
        for kinds, probability, input_column in (
            ((D.INPUT_MEAN, D.INPUT_STD, D.INPUT_KS), False, column),
            ((D.MAE, D.MSE, D.RMSE), False, None),
            ((D.PREDICTION_MEAN, D.PREDICTIVE_VARIANCE), True, None),
        ):
            s, rules = health_spec(repo, f, kinds, probability, input_column)
            e.declare(s, rules)
            specs.append((s, rules))
        started = perf_counter()
        with repo.feature_only(), repo.read_snapshot(), repo.validation_cache():
            for s, _ in specs:
                admitted(repo, s, s.reference_window, s.reference_observation_ids, True)
                admitted(repo, s, s.current_window, s.current_observation_ids, True)
        timings["window_admission_seconds"] = perf_counter() - started
        started = perf_counter()
        with repo.read_snapshot(), repo.validation_cache():
            metrics = tuple(
                tuple(metric_for(repo, s, q, 120) for q in s.requests) for s, _ in specs
            )
        timings["metric_calculation_seconds"] = perf_counter() - started
        started = perf_counter()
        for group, (_, rules) in zip(metrics, specs, strict=True):
            by = {r.kind: r for r in rules}
            for metric in group:
                if metric.score is not None:
                    classify(by[metric.kind], metric.score)
        timings["classification_seconds"] = perf_counter() - started
        snapshots = tuple(
            snapshot_for(s, group, 120) for (s, _), group in zip(specs, metrics, strict=True)
        )
        started = perf_counter()
        e._publish(tuple(m for group in metrics for m in group) + snapshots)
        timings["persistence_seconds"] = perf_counter() - started
        fusion = FusionEngine(repo)
        a = fusion.fit(f.upstream.spec, 0, 0, 0)
        ids = sorted(f.upstream.spec.source_ids)
        b = fusion.fit(
            replace(
                f.upstream.spec,
                name="profile-weights",
                weights=((ids[0], 0.25), (ids[1], 0.75)),
            ),
            0,
            0,
            0,
        )
        started = perf_counter()
        parameters = parameter_monitor(
            repo,
            a.fingerprint,
            b.fingerprint,
            (
                D.PARAMETER_L1,
                D.PARAMETER_L2,
                D.FUSION_DOMINANCE,
                D.EFFECTIVE_SOURCE_COUNT,
                D.WEIGHT_ENTROPY,
            ),
            "weight",
        )
        timings["parameter_weight_seconds"] = perf_counter() - started
        refs += (e.monitor(a.fingerprint), e.monitor(b.fingerprint))
        started = perf_counter()
        history = tuple(e.history(r.fingerprint) for r in refs)
        timings["history_seconds"] = perf_counter() - started
        started = perf_counter()
        audit = e.audit(snapshots[0].fingerprint)
        timings["audit_seconds"] = perf_counter() - started
    started = perf_counter()
    with HealthRepository(path) as reopened:
        assert all(reopened.resolve(type(s), s.fingerprint) == s for s in snapshots)
    timings["restart_seconds"] = perf_counter() - started
    errors = numerical_errors()
    return {
        "boundary": "AFRE22 descriptive offline research; no production SLA",
        "timings": timings,
        "monitored_artifacts": len(refs),
        "window_pairs": len(specs) + 1,
        "metrics": sum(map(len, metrics)) + len(parameters.metric_ids),
        "history_records": sum(map(len, history)),
        "audit_nodes": len(audit.node_ids),
        "audit_bytes": audit.serialized_bytes,
        "sqlite_bytes": path.stat().st_size,
        "maximum_numerical_error": max(v for _, v in errors),
        "numerical_errors": dict(errors),
    }


if __name__ == "__main__":
    with TemporaryDirectory() as directory:
        result = profile(Path(directory))
    print(json.dumps(result, sort_keys=True, indent=2))

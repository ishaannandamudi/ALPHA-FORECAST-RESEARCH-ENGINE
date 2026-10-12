"""Measured bounded offline release call profile; cumulative categories overlap."""

import cProfile
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from types import CodeType

from examples.release_demo import demo

OPERATIONS = {
    "feature_reconstruction": (("feature_store/engine.py", "point_in_time_join"),),
    "dataset_admission": (("research_datasets/engine.py", "build_dataset"),),
    "baseline_fitting": (("statistical_models/engine.py", "fit_model"),),
    "probabilistic_prediction": (("probabilistic/engine.py", "predict_batch"),),
    "calibration": (("calibration/engine.py", "fit"), ("calibration/engine.py", "apply_batch")),
    "multi_horizon_assembly": (("service/facade.py", "get_multi_horizon_snapshot"),),
    "signal_ranking": (("cross_sectional/engine.py", "build_ranking"),),
    "event_regime_conditioning": (
        ("event_conditioned/engine.py", "forecast"),
        ("regime_conditioned/engine.py", "forecast"),
    ),
    "fusion": (("fusion/engine.py", "apply"),),
    "selection": (("selection/engine.py", "select"),),
    "health_monitoring": (("health/engine.py", "evaluate"),),
    "challenge_evaluation": (("challenger/engine.py", "evaluate"),),
    "snapshot_publication": (("service/publisher.py", "publish"),),
    "registry_lookup": (("service/facade.py", "get_registry_entry"),),
    "service_replay": (("service/facade.py", "get_snapshot"),),
}


def main() -> None:
    profiler = cProfile.Profile()
    start = perf_counter()
    with TemporaryDirectory(prefix="afre-release-profile-") as work:
        steps, timings = profiler.runcall(demo, Path(work))
    elapsed = perf_counter() - start
    operations: dict[str, dict[str, float]] = {
        k: {"calls": 0.0, "self_seconds": 0.0, "cumulative_seconds": 0.0} for k in OPERATIONS
    }
    exclusive = {
        k: 0.0
        for k in (
            "algorithm",
            "input_validation",
            "persistence",
            "audit",
            "fixture_construction",
        )
    }
    for entry in profiler.getstats():
        if not isinstance(entry.code, CodeType):
            continue
        path, name = entry.code.co_filename.replace("\\", "/"), entry.code.co_name
        for operation, bindings in OPERATIONS.items():
            if any(path.endswith(file) and name == function for file, function in bindings):
                record = operations[operation]
                record["calls"] += entry.callcount
                record["self_seconds"] += entry.inlinetime
                record["cumulative_seconds"] += entry.totaltime
        if "/src/afre/" in path:
            category = (
                "audit"
                if "audit" in path or "audit" in name or "lineage" in path
                else "input_validation"
                if "validation" in path
                or "_validate" in name
                or name in ("require", "__post_init__")
                else "persistence"
                if path.endswith(("repository.py", "persistence.py", "storage.py"))
                else "algorithm"
            )
            exclusive[category] += entry.inlinetime
        elif "/examples/" in path and (
            "fixture" in path or name.startswith("build_") or name == "populate"
        ):
            exclusive["fixture_construction"] += entry.inlinetime
    assert all(v["calls"] > 0 for v in operations.values()), operations
    report = {
        "engine": "1.0.0",
        "api": "1.0",
        "store": "1.24",
        "sqlite_user_version": 25,
        "actual_native_workflows": True,
        "asserted_demo_checks": len(steps),
        "wall_seconds": elapsed,
        "operation_profile": operations,
        "exclusive_python_self_seconds": exclusive,
        "explicit_stage_measurements": timings,
        "profile_rules": (
            "Operation cumulative times include nested validation/persistence and may "
            "overlap. Exclusive Python self-time classifications use the exact "
            "path/name rules in benchmarks/release_profile.py; builtin/SQLite C work "
            "and other Python frames are outside those five buckets. Explicit "
            "fixture-construction wall times are separately recorded; native calls "
            "within fixture construction are profiled, not omitted or misreported as "
            "isolated throughput."
        ),
        "units": "seconds, except calls/storage_bytes/max_numerical_error",
        "limitations": (
            "One bounded synthetic offline run, under instrumentation; no production "
            "throughput/latency SLA or scalability extrapolation. Timing is excluded "
            "from semantic identities."
        ),
    }
    Path("docs/release-profile.json").write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n"
    )
    Path("docs/release-demo-evidence.json").write_text(
        json.dumps({"engine": "1.0.0", "checks": steps}, sort_keys=True, indent=2) + "\n"
    )
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

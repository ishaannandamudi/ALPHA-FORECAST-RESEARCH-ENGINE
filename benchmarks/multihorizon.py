"""Local four-horizon numerical kernels and two-horizon persisted causal workload."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from afre.multihorizon import (
    Denominator,
    HorizonSet,
    MultiHorizonEngine,
    MultiHorizonRepository,
    surfaces,
)
from afre.multihorizon.covariance import empirical_covariance, validate_psd
from afre.serialization import canonical_json
from examples.multihorizon_demo import backbone_spec, build_fixture


def main() -> None:
    timings: dict[str, float] = {}
    started = perf_counter()
    # These are numerical/alignment kernel inputs, not asserted historical artifacts.
    rows = tuple((x, 2 * x, -x, x / 2) for i in range(3000) for x in (float(i % 3 - 1),))
    keys = tuple(
        {(i, f"synthetic-{i % 100}") for i in range(offset, 3000)} for offset in (0, 1, 2, 3)
    )
    matched = set.intersection(*keys)
    timings["synthetic_intersection_3000"] = perf_counter() - started
    assert len(matched) == 2997
    started = perf_counter()
    mean, covariance = empirical_covariance(rows, Denominator.POPULATION)
    validate_psd(covariance, 1e-12)
    timings["covariance_3000_by_4_and_psd"] = perf_counter() - started
    slopes = (1.0, 2.0, -1.0, 0.5)
    reference = tuple(tuple(a * b * 2 / 3 for b in slopes) for a in slopes)
    max_error = max(
        abs(a - b)
        for r, s in zip(covariance, reference, strict=True)
        for a, b in zip(r, s, strict=True)
    )
    assert max_error < 1e-12 and mean == (0.0, 0.0, 0.0, 0.0)
    with TemporaryDirectory(prefix="afre-multihorizon-profile-") as directory:
        path = Path(directory) / "research.sqlite"
        started = perf_counter()
        with MultiHorizonRepository(path) as repo:
            f = build_fixture(repo)
            timings["causal_upstream_fixture"] = perf_counter() - started
            started = perf_counter()
            for _ in range(100):
                assert (
                    HorizonSet(tuple(reversed(f.spec.horizon_set.targets)))
                    == f.spec.horizon_set
                )
            timings["horizon_set_100"] = perf_counter() - started
            engine = MultiHorizonEngine(repo)
            started = perf_counter()
            shared = engine.fit(backbone_spec(f), 55, 55, 55)
            timings["aligned_shared_fit_and_persistence"] = perf_counter() - started
            started = perf_counter()
            state = engine.fit_dependence(f.run.fingerprint, 40, 55)
            timings["causal_covariance_and_persistence"] = perf_counter() - started
            started = perf_counter()
            bundles = tuple(
                engine.build_bundle(
                    f.run.fingerprint, b.origin, b.entries, at, state.fingerprint
                )
                for at in range(60, 85)
                for b in f.bundles
            )
            timings["bundles_and_persistence"] = perf_counter() - started
            started = perf_counter()
            for b in bundles:
                surfaces(repo, b)
                surfaces(repo, b, True)
            timings["raw_and_calibrated_surfaces"] = perf_counter() - started
            started = perf_counter()
            evaluated = engine.evaluate(tuple(b.fingerprint for b in f.bundles), 75, 75)
            timings["evaluation_and_persistence"] = perf_counter() - started
            from afre.statistical_models.schema import MetricName

            mses = tuple(
                next(m.value for m in h.point_metrics if m.name is MetricName.MSE)
                for h in evaluated.horizons
            )
            aggregate_reference = ((mses[0] or 0.0) + 2 * (mses[1] or 0.0)) / 3
            aggregate_error = abs((evaluated.weighted_mse or 0.0) - aggregate_reference)
            assert aggregate_error < 1e-12
            started = perf_counter()
            audit = engine.lineage_audit(bundles[0].fingerprint)
            timings["bounded_lineage_and_persistence"] = perf_counter() - started
            frozen = canonical_json(bundles[0])
            started = perf_counter()
            with repo.transaction():
                for b in bundles:
                    repo.put(b)
            timings["idempotent_persistence"] = perf_counter() - started
            count = repo._connection.execute("SELECT count(*) FROM mh_artifacts").fetchone()[0]
        started = perf_counter()
        with MultiHorizonRepository(path) as restarted:
            assert canonical_json(restarted.get_any(bundles[0].fingerprint)) == frozen
            restarted.audit()
        timings["restart_and_full_audit"] = perf_counter() - started
        print(
            json.dumps(
                {
                    "timings_seconds": timings,
                    "kernel_rows": len(rows),
                    "kernel_horizons": 4,
                    "persisted_horizons": 2,
                    "matched_TRAIN_rows": len(shared.intersection),
                    "bundles": len(bundles),
                    "lineage_nodes": len(audit.evidence_ids),
                    "multi_horizon_artifacts": count,
                    "sqlite_bytes": path.stat().st_size,
                    "max_covariance_reference_error": max_error,
                    "aggregate_reference_error": aggregate_error,
                    "correlation_matrix": "not exposed",
                    "SLA": "none",
                },
                sort_keys=True,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()

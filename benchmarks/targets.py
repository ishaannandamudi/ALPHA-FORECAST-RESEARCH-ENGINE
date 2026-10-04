"""Offline target profile: 20,000 observations and 12,000 labels; no SLA."""

import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from afre.datasets import UniverseMembership
from afre.ids import InstrumentId
from afre.serialization import canonical_json
from afre.target_engine import (
    TargetDatasetManifest,
    TargetEngine,
    TargetRepository,
    TargetSetManifest,
)
from afre.target_engine.schema import TargetBounds
from afre.targets import TargetType
from afre.time import DAY_NS, TimeRange
from examples.feature_store_demo import UNIVERSE, clocks, origin
from examples.target_demo import (
    CALENDAR_TARGET,
    SOURCE_MARKET,
    bar,
    definition,
    register_sources,
)


def main() -> None:
    securities = tuple(
        InstrumentId("synthetic-security", f"profile-{i:04d}") for i in range(20)
    )
    universe = replace(
        UNIVERSE,
        memberships=tuple(
            UniverseMembership(item, TimeRange(0, DAY_NS), 0, "synthetic")
            for item in securities
        ),
    )
    origins = tuple(
        replace(origin(n, security), universe_id=universe.fingerprint)
        for security in securities
        for n in range(1, 201)
    )
    targets = TargetSetManifest(
        (
            definition(horizon_ns=2),
            definition(TargetType.LOG_RETURN),
            definition(TargetType.MAX_ADVERSE_EXCURSION),
        )
    )
    bounds = TargetBounds(origins=5000)
    results: dict[str, int | float | str] = {
        "source_observations": 20_000,
        "target_rows": 12_000,
        "securities": 20,
        "origins": len(origins),
        "target_types": 3,
        "horizons_ns": "2,4",
        "path_interval_ns": 1,
    }
    start = perf_counter()
    observations = tuple(
        replace(bar(n, 100.0 + n / 100), instrument=security)
        for security in securities
        for n in range(1, 1001)
    )
    results["source_construction_seconds"] = perf_counter() - start
    with TemporaryDirectory(prefix="afre-target-profile-") as directory:
        path = Path(directory) / "targets.sqlite"
        start = perf_counter()
        repository = TargetRepository(path, bounds)
        register_sources(repository)
        engine = TargetEngine(repository)
        results["initialization_migration_seconds"] = perf_counter() - start
        start = perf_counter()
        with repository.transaction():
            for observation in observations:
                repository.put(observation)
        results["source_validation_persistence_seconds"] = perf_counter() - start
        print("Persisted 20,000 immutable source observations", flush=True)
        start = perf_counter()
        source = engine.freeze_source(SOURCE_MARKET, CALENDAR_TARGET, 1001)
        results["freeze_source_seconds"] = perf_counter() - start
        start = perf_counter()
        dataset = engine.build_dataset(
            "target-profile", origins, targets, source.fingerprint, universe, clocks(1001)
        )
        results["target_construction_validation_persistence_seconds"] = perf_counter() - start
        assert len(dataset.row_ids) == 12_000
        print("Persisted 12,000 labels with exact frozen source identities", flush=True)
        start = perf_counter()
        sample = engine.targets_known_by(
            1001, targets, instruments=(securities[0],), dataset_id=dataset.fingerprint
        )
        results["indexed_cutoff_query_seconds"] = perf_counter() - start
        results["queried_rows"] = len(sample)
        assert len(sample) == 600 and not engine.targets_known_by(
            1000, targets, instruments=(securities[0],)
        )
        start = perf_counter()
        with repository.transaction():
            for row in sample:
                repository.put(row)
        results["idempotent_persistence_600_rows_seconds"] = perf_counter() - start
        start = perf_counter()
        audit = engine.audit_target(sample[0].fingerprint)
        results["one_lineage_audit_seconds"] = perf_counter() - start
        results["one_lineage_nodes"] = len(audit.lineage_ids)
        start = perf_counter()
        results["validated_artifacts"] = engine.audit()
        results["deep_store_validation_seconds"] = perf_counter() - start
        results["query_plan"] = str(
            repository._connection.execute(
                "EXPLAIN QUERY PLAN SELECT fingerprint FROM target_vintages "
                "WHERE definition_id=? AND available_ns<=?",
                (targets.definitions[0].fingerprint, 1001),
            ).fetchall()
        )
        frozen = tuple(canonical_json(row) for row in sample)
        manifest_bytes = canonical_json(dataset)
        repository.close()
        results["storage_bytes"] = path.stat().st_size
        start = perf_counter()
        with TargetRepository(path, bounds) as restarted:
            replay = TargetEngine(restarted)
            assert (
                canonical_json(restarted.get(TargetDatasetManifest, dataset.fingerprint))
                == manifest_bytes
            )
            results["restart_manifest_validation_seconds"] = perf_counter() - start
            start = perf_counter()
            same = replay.targets_known_by(
                1001, targets, instruments=(securities[0],), dataset_id=dataset.fingerprint
            )
            assert tuple(canonical_json(row) for row in same) == frozen
            results["restart_query_retrieval_seconds"] = perf_counter() - start
        results["dataset_id"] = dataset.fingerprint
    print(json.dumps(results, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

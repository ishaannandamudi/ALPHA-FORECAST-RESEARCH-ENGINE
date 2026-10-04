"""Offline 20,000-vintage feature-store profile; local evidence, no SLA."""

import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from afre.datasets import UniverseManifest, UniverseMembership, UniversePolicy
from afre.feature_store import FeatureSetManifest, FeatureStore, FeatureStoreRepository
from afre.ids import InstrumentId
from afre.serialization import canonical_json
from afre.time import DAY_NS, TimeRange
from examples.feature_store_demo import SOURCE, dataset, definition, origin, source_vintage


def main() -> None:
    securities = tuple(InstrumentId("synthetic-security", f"{i:04d}") for i in range(20))
    features = FeatureSetManifest(tuple(definition(f"market.input_{i}") for i in range(5)))
    universe = UniverseManifest(
        "benchmark-universe",
        "synthetic-v1",
        "eligibility-v1",
        UniversePolicy.POINT_IN_TIME,
        tuple(
            UniverseMembership(item, TimeRange(0, DAY_NS), 0, "synthetic")
            for item in securities
        ),
    )
    manifest = replace(dataset(features), universe=universe)
    origins = tuple(
        replace(origin(timestamp, security), universe_id=universe.fingerprint)
        for timestamp in (100, 201)
        for security in securities
    )
    results: dict[str, int | float | str] = {
        "vintages": 20_000,
        "features": 5,
        "securities": 20,
        "observations_per_feature_security": 200,
        "batch_origins": len(origins),
    }
    with TemporaryDirectory(prefix="afre-feature-profile-") as directory:
        path = Path(directory) / "profile.sqlite"
        start = perf_counter()
        repository = FeatureStoreRepository(path)
        results["initialization_migration_seconds"] = perf_counter() - start
        store = FeatureStore(repository)
        start = perf_counter()
        with repository.transaction():
            repository.put(SOURCE)
            for feature in features.definitions:
                store.registry.register_definition(feature)
            for security in securities:
                for feature in features.definitions:
                    for number in range(1, 201):
                        store.append_vintage(
                            source_vintage(
                                feature, number, number + 1, float(number), entity=security
                            )
                        )
        results["construction_validation_insertion_commit_seconds"] = perf_counter() - start
        print("Inserted 20,000 immutable vintages", flush=True)
        start = perf_counter()
        for index in range(200):
            selected = store.feature_as_of(
                features.definitions[index % 5], origins[index % len(origins)]
            )
        assert selected.selected is not None
        results["single_lookup_count"] = 200
        results["single_lookup_seconds"] = perf_counter() - start
        start = perf_counter()
        joined = store.point_in_time_join(origins, manifest, features)
        results["batch_join_cells"] = len(origins) * len(features.definitions)
        results["batch_join_seconds"] = perf_counter() - start
        start = perf_counter()
        materialized = store.materialize(origins, manifest, features, 202)
        results["join_and_persist_materialization_seconds"] = perf_counter() - start
        start = perf_counter()
        lineage = store.lineage(selected.selected.fingerprint)
        results["lineage_seconds"] = perf_counter() - start
        results["lineage_nodes"] = len(lineage)
        plan = repository._connection.execute(
            "EXPLAIN QUERY PLAN SELECT fingerprint FROM fs_vintages WHERE definition_id = ? "
            "AND entity_id = ? AND available_ns <= ? AND effective_ns <= ? "
            "ORDER BY available_ns DESC, fingerprint",
            (features.definitions[0].fingerprint, securities[0].fingerprint, 201, 201),
        ).fetchall()
        assert any("fs_pit_idx" in row[3] for row in plan)
        results["lookup_query_plan"] = " | ".join(row[3] for row in plan)
        start = perf_counter()
        results["validated_records"] = store.audit()
        results["full_validation_seconds"] = perf_counter() - start
        print("Completed indexed retrieval and full validation", flush=True)
        payload = canonical_json(materialized)
        repository.close()
        results["sqlite_bytes_after_checkpoint_close"] = path.stat().st_size
        start = perf_counter()
        with FeatureStoreRepository(path) as restarted:
            reloaded = restarted.get(type(materialized), materialized.fingerprint)
            assert canonical_json(reloaded) == payload
            results["restart_and_materialization_replay_seconds"] = perf_counter() - start
            replay = FeatureStore(restarted).point_in_time_join(origins, manifest, features)
            assert canonical_json(replay[0]) == canonical_json(joined[0])
        results["materialization_fingerprint"] = materialized.fingerprint
    print(json.dumps(results, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

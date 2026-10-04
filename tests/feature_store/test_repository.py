import os
import sqlite3
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from afre.feature_store import (
    FeatureStore,
    FeatureStoreRepository,
    FeatureVintage,
    SourceReference,
)
from afre.feature_store.repository import feature_store_schema
from afre.feature_store.schema import QueryBounds
from afre.persistence import ArtifactStore
from afre.schema import ContractError
from afre.serialization import canonical_json
from examples.feature_store_demo import (
    SOURCE,
    clocks,
    dataset,
    definition,
    origin,
    populate,
    source_vintage,
)
from examples.foundation_demo import build_demo
from tests.feature_store.test_queries import append


def corrupt(path: Path, table: str, column: str, value: object) -> None:
    with sqlite3.connect(path) as connection:
        name = f"immutable_{table}_update"
        ddl = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = ?", (name,)
        ).fetchone()[0]
        connection.execute(f"DROP TRIGGER {name}")
        connection.execute(f"UPDATE {table} SET {column} = ?", (value,))
        connection.execute(ddl)


def test_additive_migration_preserves_foundation_bytes(tmp_path: Path) -> None:
    path = tmp_path / "upgrade.sqlite"
    original = replace(build_demo().row.dataset, engine_version="0.1.0")
    payload = canonical_json(original)
    with ArtifactStore(path) as legacy, legacy.transaction():
        legacy.put(original)
    with FeatureStoreRepository(path) as upgraded:
        assert canonical_json(upgraded.get(type(original), original.fingerprint)) == payload
        assert upgraded.audit() == 1
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        meta = dict(connection.execute("SELECT key, value FROM metadata"))
        assert meta["store_schema_version"] == "1.1"
        assert meta["schema_version"] == "1.0"
    with pytest.raises(ContractError):
        ArtifactStore(path)  # Explicit legacy store fails closed on a future schema.


def test_failed_migration_rolls_back_to_legacy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import afre.feature_store.repository as module

    path = tmp_path / "failed.sqlite"
    ArtifactStore(path).close()
    statements = feature_store_schema()
    monkeypatch.setattr(module, "feature_store_schema", lambda: (*statements, "INVALID SQL"))
    with pytest.raises(sqlite3.OperationalError):
        FeatureStoreRepository(path)
    with ArtifactStore(path) as legacy:
        assert legacy.audit() == 0
    with sqlite3.connect(path) as connection:
        assert not connection.execute(
            "SELECT name FROM sqlite_master WHERE name LIKE 'fs_%'"
        ).fetchall()
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1


@pytest.mark.parametrize("version", [3, 99, -1])
def test_unknown_store_version(tmp_path: Path, version: int) -> None:
    path = tmp_path / "future.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute(f"PRAGMA user_version = {version}")
    with pytest.raises(ContractError):
        FeatureStoreRepository(path)


def test_restart_receipts_normalization_and_materialization(tmp_path: Path) -> None:
    path = tmp_path / "replay.sqlite"
    with FeatureStoreRepository(path) as repository:
        store, features = populate(repository)
        at = origin(181_000_000_000)
        materialization = store.materialize((at,), dataset(features), features, at.timestamp_ns)
        before = canonical_json(materialization)
        count = store.audit()
    with FeatureStoreRepository(path) as restarted:
        assert (
            canonical_json(restarted.get(type(materialization), materialization.fingerprint))
            == before
        )
        assert restarted.audit() == count
        replay = FeatureStore(restarted).point_in_time_join((at,), dataset(features), features)
        assert canonical_json(replay[0]) == canonical_json(materialization.results[0])


def test_read_snapshot_isolation_with_concurrent_later_and_backdated_insert(
    store: FeatureStore, tmp_path: Path
) -> None:
    path = tmp_path / "features.sqlite"
    feature = definition()
    first = source_vintage(feature, 1, 2)
    append(store, first)
    with FeatureStoreRepository(path) as writer:
        with store.repository.read_snapshot():
            from afre.feature_store.queries import select_as_of

            assert (
                select_as_of(store.repository, feature, origin(3), store.policy).selected
                == first
            )
            later = replace(
                first, clocks=clocks(4), value=101.0, predecessor_id=first.fingerprint
            )
            backdated = source_vintage(feature, 2, 3, 102.0)
            with writer.transaction():
                writer.put(later)
                writer.put(backdated)
            assert (
                select_as_of(store.repository, feature, origin(3), store.policy).selected
                == first
            )
            with pytest.raises(ContractError):
                store.repository.close()
            with pytest.raises(ContractError), store.repository.transaction():
                pass
            with pytest.raises(ContractError), store.repository.read_snapshot():
                pass
        assert store.feature_as_of(feature, origin(3)).selected == backdated
        assert store.feature_as_of(feature, origin(4)).selected == later
    with pytest.raises(RuntimeError), store.repository.read_snapshot():
        raise RuntimeError("abort read")
    assert store.feature_as_of(feature, origin(3)).selected == backdated


@pytest.mark.parametrize(
    "table,column,bad",
    [
        ("fs_artifacts", "payload", "{}"),
        ("fs_artifacts", "type_name", "Unknown"),
        ("fs_artifacts", "schema_version", "2.0"),
        ("fs_vintages", "available_ns", 999),
        ("fs_definitions", "name", "market.corrupted"),
    ],
)
def test_payload_and_index_corruption_fail_closed(
    tmp_path: Path, table: str, column: str, bad: object
) -> None:
    path = tmp_path / "corrupt.sqlite"
    feature = definition()
    with FeatureStoreRepository(path) as repository, repository.transaction():
        repository.put(SOURCE)
        repository.put(feature)
        repository.put(source_vintage(feature, 1, 2))
    corrupt(path, table, column, bad)
    with FeatureStoreRepository(path) as restarted, pytest.raises(ContractError):
        restarted.audit()


def test_unknown_layout_metadata_and_removed_protections(tmp_path: Path) -> None:
    for kind in ("index", "metadata", "orphan"):
        path = tmp_path / f"{kind}.sqlite"
        FeatureStoreRepository(path).close()
        if kind == "metadata":
            corrupt(path, "metadata", "value", "wrong")
        else:
            with sqlite3.connect(path) as connection:
                if kind == "index":
                    connection.execute("DROP INDEX fs_pit_idx")
                else:
                    connection.execute(
                        "INSERT INTO fs_definitions VALUES (?, ?, ?, ?)",
                        ("orphan", "x", "1", "fake"),
                    )
        if kind == "orphan":
            with (
                FeatureStoreRepository(path) as repository,
                pytest.raises(ContractError, match="orphan"),
            ):
                repository.audit()
        else:
            with pytest.raises(ContractError):
                FeatureStoreRepository(path)


def test_immutable_vintages_registry_conflicts_and_idempotence(
    store: FeatureStore, tmp_path: Path
) -> None:
    feature = definition()
    value = source_vintage(feature, 1, 2)
    with store.repository.transaction():
        assert store.repository.put(feature) == feature.fingerprint
        assert store.repository.put(value) == value.fingerprint
        assert store.repository.put(value) == value.fingerprint
    with pytest.raises(ContractError):
        store.repository.put(SOURCE)
    changed_logic = replace(feature, parameters=())
    assert changed_logic == feature
    different = replace(feature, definition=replace(feature.definition, unit="shares"))
    with pytest.raises(sqlite3.IntegrityError), store.repository.transaction():
        store.repository.put(different)
    with sqlite3.connect(tmp_path / "features.sqlite") as connection:
        for table in ("fs_artifacts", "fs_definitions", "fs_vintages"):
            for operation in (
                f"DELETE FROM {table}",
                f"UPDATE {table} SET fingerprint = fingerprint",
            ):
                with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                    connection.execute(operation)
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute("INSERT OR REPLACE INTO fs_vintages SELECT * FROM fs_vintages")
    with pytest.raises(KeyError):
        store.repository.get(FeatureVintage, "afre.fs_vintage:1.0:" + "0" * 64)
    with pytest.raises(ContractError):
        store.repository.get_any("afre.fs_source:1.0:" + "0" * 64)
    with pytest.raises(ContractError):
        store.repository.get(SourceReference, feature.fingerprint)
    store.repository.bounds = QueryBounds(serialized_bytes=1)
    with pytest.raises(ContractError):
        store.repository.get(FeatureVintage, value.fingerprint)
    with pytest.raises(ContractError), store.repository.transaction():
        store.repository.put(SOURCE)


def test_lineage_bounds_and_transitive_target_provenance(store: FeatureStore) -> None:
    source2 = replace(
        SOURCE,
        provenance=replace(SOURCE.provenance, artifact_id="child"),
        parent_source_ids=(SOURCE.fingerprint,),
    )
    append(store, source2)
    value = source_vintage(definition(), 1, 2, source=source2)
    append(store, value)
    assert SOURCE in store.lineage(value.fingerprint)
    for bounds in (
        QueryBounds(lineage_depth=1),
        QueryBounds(lineage_nodes=1),
        QueryBounds(serialized_bytes=1),
    ):
        store.repository.bounds = bounds
        with pytest.raises(ContractError):
            store.lineage(value.fingerprint)
    store.repository.bounds = QueryBounds()
    for prohibited in (
        "afre.target_row:1.0:" + "a" * 64,
        "afre.experiment_result:1.0:" + "a" * 64,
        "evaluation.crps",
        "future_return.label",
    ):
        with pytest.raises(ContractError):
            replace(SOURCE, provenance=replace(SOURCE.provenance, artifact_id=prohibited))
        with pytest.raises(ContractError):
            replace(SOURCE, parent_source_ids=(prohibited,))
    # Storage corruption of an ancestor fails closed in a recursive lineage audit.
    tampered = source2
    object.__setattr__(tampered, "parent_source_ids", (value.fingerprint,))
    with pytest.raises(ContractError), store.repository.transaction():
        store.repository.put(tampered)


def test_detect_lineage_cycle_even_if_external_index_lies(
    store: FeatureStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = "afre.fs_source:1.0:" + "a" * 64
    cycle = replace(SOURCE, parent_source_ids=(parent,))
    monkeypatch.setattr(store.repository, "get_any", lambda identity: cycle)
    with pytest.raises(ContractError, match="cycle"):
        store.repository.lineage(parent)


@pytest.mark.parametrize("seed", ["0", "1", "42", "random"])
def test_materialization_hash_seed_and_offline_example(seed: str) -> None:
    script = """
import socket

def denied(*args, **kwargs):
    raise AssertionError('network forbidden')

socket.socket = denied
socket.getaddrinfo = denied
from examples.feature_store_demo import main
main()
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=dict(os.environ, PYTHONHASHSEED=seed, PYTHONPATH="src:."),
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    assert "Byte-identical restart replay" in result.stdout
    assert (
        "afre.fs_materialization:1.0:32b103ffea1fd5ae763e6f62e3c5385d7ee8ca4df4e91b6ebd8f6fe2cb5317bc"
        in result.stdout
    )

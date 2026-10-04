import sqlite3
from pathlib import Path

import pytest

from afre.datasets import DatasetManifest
from afre.persistence import TABLES, ArtifactStore
from afre.schema import ContractError
from afre.serialization import canonical_json
from examples.foundation_demo import Demo
from tests.test_lifecycle import artifact, result


def test_restart_replay_and_all_families(demo: Demo, tmp_path: Path) -> None:
    path = tmp_path / "research.sqlite"
    artifacts = (
        demo.row.dataset,
        demo.row.dataset.universe,
        *demo.row.dataset.feature_set.definitions,
        demo.experiment,
        demo.experiment.model,
        artifact(demo),
        result(demo),
    )
    with ArtifactStore(path) as store:
        with store.transaction():
            for value in artifacts:
                assert store.put(value) == value.fingerprint
                assert store.put(value) == value.fingerprint
        assert store.audit() == len(artifacts)
    with ArtifactStore(path) as restarted:
        for value in artifacts:
            assert restarted.get(type(value), value.fingerprint) == value
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert (
            connection.execute(
                "SELECT value FROM metadata WHERE key = ?", ("schema_version",)
            ).fetchone()[0]
            == "1.0"
        )


def test_transaction_rollback_and_invalid_operations(demo: Demo, tmp_path: Path) -> None:
    with ArtifactStore(tmp_path / "rollback.sqlite") as store:
        with pytest.raises(ContractError, match="explicit transaction"):
            store.put(demo.row.dataset)
        with pytest.raises(RuntimeError), store.transaction():
            store.put(demo.row.dataset)
            raise RuntimeError("abort")
        with pytest.raises(KeyError):
            store.get(DatasetManifest, demo.row.dataset.fingerprint)
        with store.transaction():
            with pytest.raises(ContractError), store.transaction():
                pass
            with pytest.raises(ContractError):
                store.close()
            with pytest.raises(ContractError):
                store.put(demo.origin)
        with pytest.raises(ContractError):
            store.get(type(demo.origin), demo.origin.fingerprint)
        with pytest.raises(ContractError):
            store.get(DatasetManifest, demo.origin.fingerprint)
        assert store.audit() == 0


@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_immutability_triggers(demo: Demo, tmp_path: Path, operation: str) -> None:
    path = tmp_path / "immutable.sqlite"
    with ArtifactStore(path) as store, store.transaction():
        store.put(demo.row.dataset)
    with sqlite3.connect(path) as connection:
        for table in ("metadata", *TABLES.values()):
            if operation == "UPDATE":
                column = "value" if table == "metadata" else "payload"
                sql = f"UPDATE {table} SET {column} = {column}"
            else:
                sql = f"DELETE FROM {table}"
            # Triggers fire per row; populate each empty artifact table with an invalid probe.
            if table != "metadata" and table != "dataset_manifests":
                connection.execute(
                    f"INSERT INTO {table} VALUES (?, ?, ?, ?)", ("probe", "1", "x", "{}")
                )
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                connection.execute(sql)


@pytest.mark.parametrize("version", [2, 999, -1])
def test_unknown_version_fails_closed(tmp_path: Path, version: int) -> None:
    path = tmp_path / "future.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute(f"PRAGMA user_version = {version}")
    with pytest.raises(ContractError, match="future store version"):
        ArtifactStore(path)


def test_migration_nonempty_zero_and_unknown_layout(tmp_path: Path) -> None:
    path = tmp_path / "unknown.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE other (x TEXT)")
    with pytest.raises(ContractError, match="must be empty"):
        ArtifactStore(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
        connection.execute("PRAGMA user_version = 1")
    with pytest.raises(ContractError, match="schema"):
        ArtifactStore(path)


@pytest.mark.parametrize("tamper", ["trigger", "metadata", "extra_table"])
def test_altered_protections_fail_closed(tmp_path: Path, tamper: str) -> None:
    path = tmp_path / "altered.sqlite"
    ArtifactStore(path).close()
    with sqlite3.connect(path) as connection:
        if tamper == "trigger":
            connection.execute("DROP TRIGGER immutable_dataset_manifests_update")
        elif tamper == "metadata":
            connection.execute("DROP TRIGGER immutable_metadata_update")
            connection.execute("UPDATE metadata SET value = '2.0' WHERE key = 'schema_version'")
            connection.execute(
                "CREATE TRIGGER immutable_metadata_update BEFORE UPDATE ON metadata "
                "BEGIN SELECT RAISE(ABORT, 'immutable AFRE artifact'); END"
            )
        else:
            connection.execute("CREATE TABLE unexpected (x TEXT)")
    with pytest.raises(ContractError):
        ArtifactStore(path)


@pytest.mark.parametrize(
    "field,bad",
    [
        ("payload", "{}"),
        ("schema_version", "2.0"),
        ("type_name", "Other"),
        ("fingerprint", "afre.dataset_manifest:1.0:" + "0" * 64),
    ],
)
def test_payload_index_corruption(demo: Demo, tmp_path: Path, field: str, bad: str) -> None:
    path = tmp_path / "corrupt.sqlite"
    with ArtifactStore(path) as store, store.transaction():
        store.put(demo.row.dataset)
    # Deliberate administrator-level corruption bypasses a trigger, then restores it.
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TRIGGER immutable_dataset_manifests_update")
        connection.execute(f"UPDATE dataset_manifests SET {field} = ?", (bad,))
        connection.execute(
            "CREATE TRIGGER immutable_dataset_manifests_update "
            "BEFORE UPDATE ON dataset_manifests BEGIN "
            "SELECT RAISE(ABORT, 'immutable AFRE artifact'); END"
        )
    with ArtifactStore(path) as restarted, pytest.raises(ContractError):
        restarted.audit()


def test_wrong_payload_family_and_idempotent_corruption(demo: Demo, tmp_path: Path) -> None:
    path = tmp_path / "index.sqlite"
    with ArtifactStore(path) as store:
        with sqlite3.connect(path) as connection:
            connection.execute(
                "INSERT INTO dataset_manifests VALUES (?, ?, ?, ?)",
                (
                    demo.row.dataset.fingerprint,
                    "1.0",
                    "DatasetManifest",
                    canonical_json(demo.experiment.model),
                ),
            )
        with pytest.raises(ContractError, match="payload/index"):
            store.get(DatasetManifest, demo.row.dataset.fingerprint)
        with pytest.raises(ContractError), store.transaction():
            store.put(demo.row.dataset)


def test_invalid_artifact_revalidated_on_write(demo: Demo, tmp_path: Path) -> None:
    from dataclasses import replace

    bad = replace(demo.row.dataset)
    object.__setattr__(bad, "source_dataset_ids", ())
    with ArtifactStore(tmp_path / "invalid.sqlite") as store:
        with pytest.raises(ContractError), store.transaction():
            store.put(bad)
        assert store.audit() == 0


def test_migration_is_atomic_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import afre.persistence as persistence

    path = tmp_path / "migration.sqlite"
    statements = persistence._schema_statements()
    monkeypatch.setattr(persistence, "_schema_statements", lambda: (*statements, "INVALID SQL"))
    with pytest.raises(sqlite3.OperationalError):
        ArtifactStore(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
        assert connection.execute("SELECT name FROM sqlite_master").fetchall() == []
    monkeypatch.setattr(persistence, "_schema_statements", lambda: statements)
    with ArtifactStore(path) as store:
        assert store.audit() == 0


def test_replace_cannot_bypass_immutability(demo: Demo, tmp_path: Path) -> None:
    path = tmp_path / "replace.sqlite"
    with ArtifactStore(path) as store, store.transaction():
        store.put(demo.row.dataset)
    with sqlite3.connect(path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "INSERT OR REPLACE INTO dataset_manifests VALUES (?, ?, ?, ?)",
                (demo.row.dataset.fingerprint, "1.0", "DatasetManifest", "{}"),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "INSERT OR REPLACE INTO metadata VALUES (?, ?)", ("schema_version", "2.0")
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO dataset_manifests VALUES (NULL, ?, ?, ?)",
                ("1.0", "DatasetManifest", "{}"),
            )
    with ArtifactStore(path) as store:
        assert store.audit() == 1

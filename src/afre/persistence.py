"""Transactional, immutable SQLite artifact registry with fail-closed replay."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TypeVar, cast

from afre.datasets import DatasetManifest, UniverseManifest
from afre.experiments import ExperimentResult, ExperimentSpec
from afre.features import FeatureDefinition
from afre.ids import validate_fingerprint
from afre.models import ModelArtifact, ModelSpec
from afre.schema import Artifact, require
from afre.serialization import canonical_json, deserialize
from afre.version import ENGINE_VERSION, STORE_SCHEMA_VERSION, STORE_USER_VERSION

TABLES: dict[type[Artifact], str] = {
    DatasetManifest: "dataset_manifests",
    UniverseManifest: "universe_manifests",
    FeatureDefinition: "feature_definitions",
    ExperimentSpec: "experiment_specs",
    ExperimentResult: "experiment_results",
    ModelSpec: "model_specs",
    ModelArtifact: "model_artifacts",
}
A = TypeVar("A", bound=Artifact)


def _schema_statements() -> tuple[str, ...]:
    statements = ["CREATE TABLE metadata (key TEXT PRIMARY KEY NOT NULL, value TEXT NOT NULL)"]
    for table in TABLES.values():
        statements.append(
            f"CREATE TABLE {table} (fingerprint TEXT PRIMARY KEY NOT NULL, "
            "schema_version TEXT NOT NULL, type_name TEXT NOT NULL, payload TEXT NOT NULL)"
        )
    for table in ("metadata", *TABLES.values()):
        key = "key" if table == "metadata" else "fingerprint"
        statements.append(
            f"CREATE TRIGGER immutable_{table}_insert BEFORE INSERT ON {table} "
            f"WHEN EXISTS (SELECT 1 FROM {table} WHERE {key} = NEW.{key}) BEGIN "
            "SELECT RAISE(ABORT, 'immutable AFRE artifact'); END"
        )
        for operation in ("UPDATE", "DELETE"):
            statements.append(
                f"CREATE TRIGGER immutable_{table}_{operation.lower()} "
                f"BEFORE {operation} ON {table} BEGIN "
                "SELECT RAISE(ABORT, 'immutable AFRE artifact'); END"
            )
    return tuple(statements)


class ArtifactStore:
    def __init__(self, path: str | Path) -> None:
        self._connection = sqlite3.connect(path, isolation_level=None)
        self._in_transaction = False
        try:
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute("PRAGMA trusted_schema = OFF")
            self._migrate()
            self._validate_layout()
        except BaseException:
            self._connection.close()
            raise

    def __enter__(self) -> "ArtifactStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        require(not self._in_transaction, "cannot close inside transaction")
        self._connection.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        require(not self._in_transaction, "nested transactions are forbidden")
        self._connection.execute("BEGIN IMMEDIATE")
        self._in_transaction = True
        try:
            yield
            self._connection.execute("COMMIT")
        except BaseException:
            self._connection.execute("ROLLBACK")
            raise
        finally:
            self._in_transaction = False

    def _migrate(self) -> None:
        version = self._connection.execute("PRAGMA user_version").fetchone()[0]
        require(version in (0, STORE_USER_VERSION), "unknown future store version")
        if version == STORE_USER_VERSION:
            return
        with self.transaction():
            # Recheck after acquiring the writer lock; another initializer may have migrated.
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            if version == STORE_USER_VERSION:
                return
            require(version == 0, "unknown store version during migration")
            existing = self._connection.execute(
                "SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            ).fetchall()
            require(not existing, "version-zero database must be empty")
            for statement in _schema_statements():
                self._connection.execute(statement)
            self._connection.executemany(
                "INSERT INTO metadata VALUES (?, ?)",
                (("schema_version", STORE_SCHEMA_VERSION), ("engine_version", ENGINE_VERSION)),
            )
            self._connection.execute(f"PRAGMA user_version = {STORE_USER_VERSION}")

    def _validate_layout(self) -> None:
        # SQLite preserves the SQL used to create objects; compare the full fixed schema.
        actual = {
            row[1]: row[0]
            for row in self._connection.execute(
                "SELECT sql, name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        }
        expected: dict[str, str] = {}
        for statement in _schema_statements():
            name = statement.split()[2]
            expected[name] = statement
        require(actual == expected, "store schema or immutability protections altered")
        metadata = dict(self._connection.execute("SELECT key, value FROM metadata"))
        require(
            metadata
            == {"schema_version": STORE_SCHEMA_VERSION, "engine_version": ENGINE_VERSION},
            "store metadata corrupted or incompatible",
        )

    def put(self, artifact: Artifact) -> str:
        require(self._in_transaction, "writes require an explicit transaction")
        table = TABLES.get(type(artifact))
        require(table is not None, "artifact family is not persistable in AFRE-0")
        identity = artifact.fingerprint
        payload = canonical_json(artifact)
        # Revalidate through the closed decoder before accepting tampered objects.
        require(deserialize(payload) == artifact, "artifact validation mismatch")
        existing = self._connection.execute(
            f"SELECT fingerprint FROM {table} WHERE fingerprint = ?", (identity,)
        ).fetchone()
        if existing is not None:
            self.get(type(artifact), identity)
            return identity
        self._connection.execute(
            f"INSERT INTO {table} VALUES (?, ?, ?, ?)",
            (identity, STORE_SCHEMA_VERSION, type(artifact).__name__, payload),
        )
        return identity

    def get(self, cls: type[A], identity: str) -> A:
        table = TABLES.get(cls)
        require(table is not None, "unsupported artifact family")
        validate_fingerprint(identity, cls.domain)
        row = self._connection.execute(
            f"SELECT schema_version, type_name, payload FROM {table} WHERE fingerprint = ?",
            (identity,),
        ).fetchone()
        if row is None:
            raise KeyError(identity)
        require(
            row[0] == STORE_SCHEMA_VERSION and row[1] == cls.__name__,
            "artifact index corruption",
        )
        artifact = deserialize(row[2])
        require(
            type(artifact) is cls and artifact.fingerprint == identity, "payload/index mismatch"
        )
        return cast(A, artifact)

    def audit(self) -> int:
        """Validate all stored payloads and their index identities after restart."""
        self._validate_layout()
        count = 0
        for cls, table in TABLES.items():
            for (identity,) in self._connection.execute(f"SELECT fingerprint FROM {table}"):
                self.get(cls, identity)
                count += 1
        return count

"""Immutable additive SQLite23 repository with semantic replay before reuse."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import ClassVar, TypeVar, cast

from afre.fusion.repository import FusionRepository
from afre.health.artifacts import (
    HealthDecayTrend,
    HealthMetric,
    HealthObservation,
    ModelHealthSnapshot,
)
from afre.health.definitions import (
    HealthDiagnosticRequest,
    HealthRule,
    HealthSpec,
    MonitoredArtifactReference,
)
from afre.health.guards import guard
from afre.health.lineage import HealthAudit, health_edges
from afre.health.schema import HealthBounds
from afre.health.storage import METADATA, all_statements, health_schema, record_index
from afre.health.windows import MonitoringWindow
from afre.ids import validate_fingerprint
from afre.schema import Artifact, require
from afre.serialization import canonical_json, deserialize

HEALTH_TYPES: tuple[type[Artifact], ...] = (
    HealthBounds,
    MonitoringWindow,
    MonitoredArtifactReference,
    HealthDiagnosticRequest,
    HealthRule,
    HealthSpec,
    HealthObservation,
    HealthMetric,
    ModelHealthSnapshot,
    HealthDecayTrend,
    HealthAudit,
)
A = TypeVar("A", bound=Artifact)


class HealthRepository(FusionRepository):
    _snapshot_engine_version: ClassVar[str] = "0.23.0"

    def __init__(self, path: str | Path, bounds: HealthBounds | None = None) -> None:
        self.health_bounds = bounds or HealthBounds()
        self._health_active: set[str] = set()
        self._health_validated: set[tuple[str, bool]] = set()
        super().__init__(path)

    @contextmanager
    def validation_cache(self) -> Iterator[None]:
        outer = self._validation_cache is None
        with super().validation_cache():
            try:
                yield
            finally:
                if outer:
                    self._health_validated.clear()

    @contextmanager
    def read_snapshot(self) -> Iterator[None]:
        with super().read_snapshot():
            pages = self._connection.execute("PRAGMA page_count").fetchone()[0]
            page_size = self._connection.execute("PRAGMA page_size").fetchone()[0]
            require(
                pages * page_size <= self.health_bounds.snapshot_bytes,
                "health frozen snapshot byte bound",
            )
            yield

    def _migrate(self) -> None:
        version = self._connection.execute("PRAGMA user_version").fetchone()[0]
        require(version in range(24), "unknown future health store version")
        if version == 23:
            return
        if version < 22:
            FusionRepository._migrate(self)
        with self.transaction():
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 23:
                return
            require(version == 22, "unexpected health migration version")
            FusionRepository._validate_layout(self)
            for sql in health_schema():
                self._connection.execute(sql)
            self._connection.executemany(
                "INSERT INTO metadata VALUES (?,?)",
                (
                    ("health_store_schema_version", "1.22"),
                    ("health_schema", "1.0"),
                    ("health_engine_version", "0.23.0"),
                ),
            )
            self._connection.execute("PRAGMA user_version=23")

    def _validate_layout(self) -> None:
        require(
            {
                s.split()[3] if s.startswith("CREATE UNIQUE INDEX") else s.split()[2]: s
                for s in all_statements()
            }
            == dict(
                self._connection.execute(
                    "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
                )
            ),
            "health layout corruption",
        )
        require(
            dict(self._connection.execute("SELECT key,value FROM metadata")) == METADATA
            and self._connection.execute("PRAGMA user_version").fetchone()[0] == 23,
            "health metadata/version corruption",
        )

    def _check_health_bounds(self, value: Artifact) -> None:
        b = self.health_bounds
        if isinstance(value, HealthSpec):
            require(
                b.windows >= 2 and len(value.comparison_reference_ids) + 1 <= b.sources,
                "configured health window/source bound",
            )
        for name, maximum in (
            ("requests", b.metrics),
            ("metric_ids", b.metrics),
            ("values", b.features),
            ("reference_observation_ids", b.samples),
            ("current_observation_ids", b.samples),
            ("comparison_reference_ids", b.sources),
            ("node_ids", b.lineage_nodes),
        ):
            require(
                len(getattr(value, name, ())) <= maximum, "configured health artifact bound"
            )
        require(
            len(canonical_json(value).encode()) <= b.payload_bytes, "health payload byte bound"
        )

    def get(self, cls: type[A], identity: str) -> A:
        guard(self, cls, identity)
        if cls not in HEALTH_TYPES:
            return super().get(cls, identity)
        validate_fingerprint(identity, cls.domain)
        row = self._connection.execute(
            "SELECT type_name,schema_version,CASE WHEN length(CAST(payload AS BLOB))<=? "
            "THEN payload ELSE NULL END FROM hlt_artifacts WHERE fingerprint=?",
            (self.health_bounds.payload_bytes, identity),
        ).fetchone()
        if row is None:
            raise KeyError(identity)
        require(
            row[:2] == (cls.__name__, "1.0") and type(row[2]) is str,
            "health type/schema/payload bound or corruption",
        )
        value = deserialize(row[2])
        require(type(value) is cls and value.fingerprint == identity, "health hash corruption")
        self._check_health_bounds(value)
        require(
            self._connection.execute(
                "SELECT * FROM hlt_records WHERE fingerprint=?", (identity,)
            ).fetchone()
            == record_index(value),
            "health index corruption",
        )
        require(
            tuple(
                r[0]
                for r in self._connection.execute(
                    "SELECT reference_id FROM hlt_links WHERE fingerprint=? "
                    "ORDER BY reference_id",
                    (identity,),
                )
            )
            == tuple(sorted(set(health_edges(value)))),
            "health link corruption",
        )
        return cast(A, value)

    def resolve(self, cls: type[A], identity: str) -> A:
        guard(self, cls, identity)
        if cls not in HEALTH_TYPES:
            return super().resolve(cls, identity)
        if self._validation_cache is None:
            if not self._reading and not self._in_transaction:
                with self.read_snapshot(), self.validation_cache():
                    return self.resolve(cls, identity)
            with self.validation_cache():
                return self.resolve(cls, identity)
        value = self.get(cls, identity)
        self._validate_links(value)
        return value

    def get_any(self, identity: str) -> Artifact:
        validate_fingerprint(identity)
        from afre.target_engine.models import TargetVintage

        if identity.startswith("afre.target_vintage:"):
            guard(self, TargetVintage, identity)
        if not identity.startswith("afre.hlt_"):
            if self._validation_cache is not None and identity in self._validation_cache:
                guard(self, type(self._validation_cache[identity]), identity)
            value = super().get_any(identity)
            guard(self, type(value), identity)
            return value
        row = self._connection.execute(
            "SELECT type_name FROM hlt_artifacts WHERE fingerprint=?", (identity,)
        ).fetchone()
        classes = {c.__name__: c for c in HEALTH_TYPES}
        require(row is not None and row[0] in classes, "unresolved health reference")
        assert row is not None
        return self.resolve(classes[row[0]], identity)

    def put(self, value: Artifact) -> str:
        if type(value) not in HEALTH_TYPES:
            return super().put(value)
        require(self._in_transaction, "health write requires transaction")
        self._check_health_bounds(value)
        payload = canonical_json(value)
        require(deserialize(payload) == value, "health canonical mismatch")
        self._validate_links(value)
        if self._connection.execute(
            "SELECT 1 FROM hlt_artifacts WHERE fingerprint=?", (value.fingerprint,)
        ).fetchone():
            require(
                self.get(type(value), value.fingerprint) == value, "conflicting health payload"
            )
            return value.fingerprint
        require(
            self._connection.execute("SELECT count(*) FROM hlt_artifacts").fetchone()[0]
            < self.health_bounds.artifacts,
            "stored health artifact bound",
        )
        self._connection.execute(
            "INSERT INTO hlt_artifacts VALUES (?,?,?,?)",
            (value.fingerprint, type(value).__name__, "1.0", payload),
        )
        self._connection.execute(
            "INSERT INTO hlt_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            record_index(value),
        )
        self._connection.executemany(
            "INSERT INTO hlt_links VALUES (?,?)",
            tuple((value.fingerprint, i) for i in sorted(set(health_edges(value)))),
        )
        return value.fingerprint

    def _validate_links(self, value: Artifact) -> None:
        if type(value) not in HEALTH_TYPES:
            super()._validate_links(value)
            return
        key = value.fingerprint, bool(self._feature_only_depth)
        if self._validation_cache is not None and key in self._health_validated:
            return
        require(value.fingerprint not in self._health_active, "health reference cycle")
        self._health_active.add(value.fingerprint)
        try:
            from afre.health.validation import validate_health

            validate_health(self, value)
            if self._validation_cache is not None:
                self._health_validated.add(key)
        finally:
            self._health_active.remove(value.fingerprint)

    def audit(self) -> int:
        if not self._reading and not self._in_transaction:
            with self.read_snapshot():
                return self.audit()
        count = super().audit()
        with self.validation_cache():
            for (identity,) in self._connection.execute(
                "SELECT fingerprint FROM hlt_artifacts ORDER BY fingerprint"
            ):
                self.get_any(identity)
                count += 1
        for table in ("hlt_records", "hlt_links"):
            require(
                self._connection.execute(
                    f"SELECT count(*) FROM {table} r LEFT JOIN hlt_artifacts a "
                    "ON r.fingerprint=a.fingerprint WHERE a.fingerprint IS NULL"
                ).fetchone()[0]
                == 0,
                "orphan health projection",
            )
        return count

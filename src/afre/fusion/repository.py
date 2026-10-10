"""Immutable additive SQLite22 repository with guards before inherited caches."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import ClassVar, TypeVar, cast

from afre.fusion.accounting import FusionTrialPool
from afre.fusion.artifacts import (
    FrozenFusionTestChoice,
    FusedForecast,
    FusionArtifact,
    FusionContribution,
    FusionObservation,
    FusionTrainingRow,
)
from afre.fusion.definitions import FusionSourceReference, FusionSpec
from afre.fusion.diagnostics import (
    DiversityMatrix,
    FusionComparison,
    FusionEvaluationPair,
    FusionPairDiversity,
    FusionWeightStability,
)
from afre.fusion.external import ExternalFusionDefinition, ExternalFusionOutput
from afre.fusion.guards import guard
from afre.fusion.lineage import FusionAudit, fusion_edges
from afre.fusion.metadata import FusionMetadata
from afre.fusion.probabilistic import FusionDistribution, FusionLawComponent
from afre.fusion.schema import FusionBounds
from afre.fusion.storage import METADATA, all_statements, fusion_schema, record_index
from afre.ids import validate_fingerprint
from afre.schema import Artifact, require
from afre.selection.repository import SelectionRepository
from afre.serialization import canonical_json, deserialize

FUSION_TYPES: tuple[type[Artifact], ...] = (
    FusionMetadata,
    FusionBounds,
    FusionSourceReference,
    FusionSpec,
    FusionObservation,
    FusionTrainingRow,
    FusionArtifact,
    FusedForecast,
    FusionContribution,
    FrozenFusionTestChoice,
    ExternalFusionDefinition,
    ExternalFusionOutput,
    FusionDistribution,
    FusionLawComponent,
    DiversityMatrix,
    FusionComparison,
    FusionEvaluationPair,
    FusionPairDiversity,
    FusionWeightStability,
    FusionAudit,
    FusionTrialPool,
)
A = TypeVar("A", bound=Artifact)


class FusionRepository(SelectionRepository):
    _snapshot_engine_version: ClassVar[str] = "0.22.0"

    def __init__(self, path: str | Path, bounds: FusionBounds | None = None) -> None:
        self.fusion_bounds = bounds or FusionBounds()
        self._fusion_train_targets: set[str] | None = None
        self._fusion_active: set[str] = set()
        self._fusion_validated: set[tuple[str, bool]] = set()
        super().__init__(path)

    @contextmanager
    def validation_cache(self) -> Iterator[None]:
        outer = self._validation_cache is None
        with super().validation_cache():
            try:
                yield
            finally:
                if outer:
                    self._fusion_validated.clear()

    @contextmanager
    def read_snapshot(self) -> Iterator[None]:
        with super().read_snapshot():
            pages = self._connection.execute("PRAGMA page_count").fetchone()[0]
            page_size = self._connection.execute("PRAGMA page_size").fetchone()[0]
            require(
                pages * page_size <= self.fusion_bounds.snapshot_bytes,
                "fusion frozen snapshot byte bound",
            )
            yield

    def _migrate(self) -> None:
        version = self._connection.execute("PRAGMA user_version").fetchone()[0]
        require(version in range(23), "unknown future fusion store version")
        if version == 22:
            return
        if version < 21:
            SelectionRepository._migrate(self)
        with self.transaction():
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 22:
                return
            require(version == 21, "unexpected fusion migration version")
            SelectionRepository._validate_layout(self)
            for sql in fusion_schema():
                self._connection.execute(sql)
            self._connection.executemany(
                "INSERT INTO metadata VALUES (?,?)",
                (
                    ("fusion_store_schema_version", "1.21"),
                    ("fusion_schema", "1.0"),
                    ("fusion_engine_version", "0.22.0"),
                ),
            )
            self._connection.execute("PRAGMA user_version=22")

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
            "fusion layout corruption",
        )
        require(
            dict(self._connection.execute("SELECT key,value FROM metadata")) == METADATA
            and self._connection.execute("PRAGMA user_version").fetchone()[0] == 22,
            "fusion metadata/version corruption",
        )

    def _check_fusion_bounds(self, value: Artifact) -> None:
        b = self.fusion_bounds
        for name, maximum in (
            ("source_ids", b.sources),
            ("rows", b.train_rows),
            ("forecast_ids", b.prediction_rows),
            (
                "pairs",
                b.diversity_cells if isinstance(value, DiversityMatrix) else b.prediction_rows,
            ),
            ("components", b.probability_components),
            ("sample_ids", b.prediction_rows),
            ("observation_ids", b.prediction_rows * b.sources),
        ):
            require(
                len(getattr(value, name, ())) <= maximum, "configured fusion artifact bound"
            )
        require(
            len(canonical_json(value).encode()) <= b.payload_bytes, "fusion payload byte bound"
        )

    def get(self, cls: type[A], identity: str) -> A:
        guard(self, cls, identity)
        if cls not in FUSION_TYPES:
            return super().get(cls, identity)
        validate_fingerprint(identity, cls.domain)
        row = self._connection.execute(
            "SELECT type_name,schema_version,CASE WHEN length(CAST(payload AS BLOB))<=? "
            "THEN payload ELSE NULL END FROM fus_artifacts WHERE fingerprint=?",
            (self.fusion_bounds.payload_bytes, identity),
        ).fetchone()
        if row is None:
            raise KeyError(identity)
        require(
            row[:2] == (cls.__name__, "1.0") and type(row[2]) is str,
            "fusion type/schema/payload bound or corruption",
        )
        value = deserialize(row[2])
        require(type(value) is cls and value.fingerprint == identity, "fusion hash corruption")
        self._check_fusion_bounds(value)
        require(
            self._connection.execute(
                "SELECT * FROM fus_records WHERE fingerprint=?", (identity,)
            ).fetchone()
            == record_index(value),
            "fusion index corruption",
        )
        require(
            tuple(
                r[0]
                for r in self._connection.execute(
                    "SELECT reference_id FROM fus_links WHERE fingerprint=? "
                    "ORDER BY reference_id",
                    (identity,),
                )
            )
            == tuple(sorted(set(fusion_edges(value)))),
            "fusion link corruption",
        )
        return cast(A, value)

    def resolve(self, cls: type[A], identity: str) -> A:
        guard(self, cls, identity)
        if cls not in FUSION_TYPES:
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
        if not identity.startswith("afre.fus_"):
            if self._validation_cache is not None and identity in self._validation_cache:
                guard(self, type(self._validation_cache[identity]), identity)
            value = super().get_any(identity)
            guard(self, type(value), identity)
            return value
        row = self._connection.execute(
            "SELECT type_name FROM fus_artifacts WHERE fingerprint=?", (identity,)
        ).fetchone()
        classes = {c.__name__: c for c in FUSION_TYPES}
        require(row is not None and row[0] in classes, "unresolved fusion reference")
        assert row is not None
        return self.resolve(classes[row[0]], identity)

    def put(self, value: Artifact) -> str:
        if type(value) not in FUSION_TYPES:
            return super().put(value)
        require(self._in_transaction, "fusion write requires transaction")
        self._check_fusion_bounds(value)
        payload = canonical_json(value)
        require(deserialize(payload) == value, "fusion canonical mismatch")
        self._validate_links(value)
        if self._connection.execute(
            "SELECT 1 FROM fus_artifacts WHERE fingerprint=?", (value.fingerprint,)
        ).fetchone():
            require(
                self.get(type(value), value.fingerprint) == value, "conflicting fusion payload"
            )
            return value.fingerprint
        require(
            self._connection.execute("SELECT count(*) FROM fus_artifacts").fetchone()[0]
            < self.fusion_bounds.artifacts,
            "stored fusion artifact bound",
        )
        if isinstance(value, FusionComparison):
            require(
                self._connection.execute(
                    "SELECT count(*) FROM fus_artifacts WHERE type_name='FusionComparison'"
                ).fetchone()[0]
                < self.fusion_bounds.comparisons,
                "fusion comparisons bound",
            )
        self._connection.execute(
            "INSERT INTO fus_artifacts VALUES (?,?,?,?)",
            (value.fingerprint, type(value).__name__, "1.0", payload),
        )
        self._connection.execute(
            "INSERT INTO fus_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            record_index(value),
        )
        self._connection.executemany(
            "INSERT INTO fus_links VALUES (?,?)",
            tuple((value.fingerprint, i) for i in sorted(set(fusion_edges(value)))),
        )
        return value.fingerprint

    def _validate_links(self, value: Artifact) -> None:
        if type(value) not in FUSION_TYPES:
            super()._validate_links(value)
            return
        key = value.fingerprint, bool(self._feature_only_depth)
        if self._validation_cache is not None and key in self._fusion_validated:
            return
        require(value.fingerprint not in self._fusion_active, "fusion reference cycle")
        self._fusion_active.add(value.fingerprint)
        try:
            from afre.fusion.validation import validate_fusion

            validate_fusion(self, value)
            if self._validation_cache is not None:
                self._fusion_validated.add(key)
        finally:
            self._fusion_active.remove(value.fingerprint)

    def audit(self) -> int:
        if not self._reading and not self._in_transaction:
            with self.read_snapshot():
                return self.audit()
        count = super().audit()
        with self.validation_cache():
            for (identity,) in self._connection.execute(
                "SELECT fingerprint FROM fus_artifacts ORDER BY fingerprint"
            ):
                self.get_any(identity)
                count += 1
        for table in ("fus_records", "fus_links"):
            require(
                self._connection.execute(
                    f"SELECT count(*) FROM {table} r LEFT JOIN fus_artifacts a "
                    "ON r.fingerprint=a.fingerprint WHERE a.fingerprint IS NULL"
                ).fetchone()[0]
                == 0,
                "orphan fusion projection",
            )
        return count

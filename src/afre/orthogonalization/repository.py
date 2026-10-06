"""Strict immutable additive SQLite17 family with inherited causal response guards."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import ClassVar, TypeVar, cast

from afre.ids import validate_fingerprint
from afre.orthogonalization.artifacts import (
    AlignedSignalRow,
    OrthogonalizationAudit,
    OrthogonalSignalValue,
    ProjectionArtifact,
    RedundancyMatrix,
)
from afre.orthogonalization.definitions import OrthogonalizationSpec, SignalReference
from afre.orthogonalization.evaluation_artifacts import (
    PartialCorrelation,
    PredictiveModelPair,
    RedundancyEvaluation,
    RedundancyStability,
)
from afre.orthogonalization.schema import OrthogonalizationBounds
from afre.orthogonalization.signals import GenericSignalSource, SignalObservation
from afre.orthogonalization.storage import (
    METADATA,
    all_statements,
    orthogonalization_index,
    orthogonalization_schema,
)
from afre.schema import Artifact, require
from afre.serialization import canonical_json, deserialize
from afre.uncertainty.repository import UncertaintyRepository

ORTHOGONALIZATION_TYPES: tuple[type[Artifact], ...] = (
    AlignedSignalRow,
    ProjectionArtifact,
    OrthogonalSignalValue,
    RedundancyMatrix,
    OrthogonalizationAudit,
    OrthogonalizationSpec,
    SignalReference,
    GenericSignalSource,
    SignalObservation,
    OrthogonalizationBounds,
    PredictiveModelPair,
    RedundancyEvaluation,
    PartialCorrelation,
    RedundancyStability,
)
A = TypeVar("A", bound=Artifact)


class OrthogonalizationRepository(UncertaintyRepository):
    _snapshot_engine_version: ClassVar[str] = "0.17.0"

    def __init__(self, path: str | Path, bounds: OrthogonalizationBounds | None = None) -> None:
        self.orthogonalization_bounds = bounds or OrthogonalizationBounds()
        self._orthogonalization_validated: set[str] = set()
        super().__init__(path)

    @contextmanager
    def validation_cache(self) -> Iterator[None]:
        with super().validation_cache():
            try:
                yield
            finally:
                self._orthogonalization_validated.clear()

    def _migrate(self) -> None:
        version = self._connection.execute("PRAGMA user_version").fetchone()[0]
        require(version in range(18), "unknown future orthogonalization store version")
        if version == 17:
            return
        if version < 16:
            UncertaintyRepository._migrate(self)
        with self.transaction():
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 17:
                return
            require(version == 16, "unexpected orthogonalization migration version")
            UncertaintyRepository._validate_layout(self)
            for statement in orthogonalization_schema():
                self._connection.execute(statement)
            self._connection.executemany(
                "INSERT INTO metadata VALUES (?,?)",
                (
                    ("orthogonalization_store_schema_version", "1.16"),
                    ("orthogonalization_schema", "1.0"),
                    ("orthogonalization_engine_version", "0.17.0"),
                ),
            )
            self._connection.execute("PRAGMA user_version=17")

    def _validate_layout(self) -> None:
        require(
            {s.split()[2]: s for s in all_statements()}
            == dict(
                self._connection.execute(
                    "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
                )
            ),
            "orthogonalization schema/index/trigger corruption",
        )
        require(
            dict(self._connection.execute("SELECT key,value FROM metadata")) == METADATA,
            "orthogonalization metadata corruption",
        )
        require(
            self._connection.execute("PRAGMA user_version").fetchone()[0] == 17,
            "orthogonalization integer version corruption",
        )

    def _orthogonalization_check_bounds(self, value: Artifact) -> None:
        bounds = self.orthogonalization_bounds
        require(
            len(canonical_json(value).encode()) <= bounds.serialized_bytes,
            "orthogonal payload bound",
        )
        if isinstance(value, OrthogonalizationSpec):
            require(len(value.references) <= bounds.references, "orthogonal reference bound")
        if isinstance(value, (ProjectionArtifact, RedundancyMatrix, PredictiveModelPair)):
            require(len(value.row_ids) <= bounds.rows, "orthogonal TRAIN/matrix row bound")
        if isinstance(value, ProjectionArtifact):
            require(len(value.coefficients) <= bounds.references, "orthogonal dimension bound")
        if isinstance(value, RedundancyMatrix):
            require(
                len(value.pearson) <= bounds.references + 1
                and len(value.row_ids) * len(value.pearson) ** 2 <= bounds.cells,
                "orthogonal matrix dimension/work bound",
            )
        if isinstance(value, ProjectionArtifact):
            require(
                len(value.row_ids) * (len(value.coefficients) + 1) ** 2 <= bounds.cells,
                "orthogonal projection work bound",
            )
        if isinstance(value, OrthogonalizationAudit):
            require(len(value.node_ids) <= bounds.audit_nodes, "orthogonal audit node bound")
        if isinstance(value, RedundancyEvaluation):
            require(len(value.residual_ids) <= bounds.rows, "orthogonal evaluation row bound")
        if isinstance(value, RedundancyStability):
            require(len(value.evaluation_ids) <= bounds.windows, "orthogonal stability bound")

    def _guard(self, cls: type[Artifact]) -> None:
        super()._guard(cls)
        require(
            not self._feature_only_depth or cls is not PredictiveModelPair,
            "residual application cannot read target model TRAIN truth",
        )

    def resolve(self, cls: type[A], identity: str) -> A:
        self._guard(cls)
        return super().resolve(cls, identity)

    def put(self, value: Artifact) -> str:
        if type(value) not in ORTHOGONALIZATION_TYPES:
            return super().put(value)
        require(self._in_transaction, "orthogonalization write requires transaction")
        self._orthogonalization_check_bounds(value)
        identity, payload = value.fingerprint, canonical_json(value)
        require(deserialize(payload) == value, "orthogonalization canonical mismatch")
        if self._connection.execute(
            "SELECT 1 FROM ort_artifacts WHERE fingerprint=?", (identity,)
        ).fetchone():
            require(
                self.get(type(value), identity) == value,
                "conflicting orthogonalization payload",
            )
            return identity
        require(
            self._connection.execute(
                "SELECT count(*) FROM ort_artifacts WHERE type_name=?", (type(value).__name__,)
            ).fetchone()[0]
            < self.orthogonalization_bounds.artifacts,
            "stored orthogonalization artifact bound",
        )
        self._validate_links(value)
        self._connection.execute(
            "INSERT INTO ort_artifacts VALUES (?,?,?,?)",
            (identity, type(value).__name__, "1.0", payload),
        )
        self._connection.execute(
            "INSERT INTO ort_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            orthogonalization_index(value),
        )
        from afre.orthogonalization.lineage import orthogonalization_edges

        self._connection.executemany(
            "INSERT INTO ort_links VALUES (?,?)",
            tuple((identity, i) for i in sorted(set(orthogonalization_edges(value)))),
        )
        return identity

    def get(self, cls: type[A], identity: str) -> A:
        self._guard(cls)
        if cls not in ORTHOGONALIZATION_TYPES:
            return super().get(cls, identity)
        validate_fingerprint(identity, cls.domain)
        row = self._connection.execute(
            "SELECT type_name,schema_version,payload FROM ort_artifacts WHERE fingerprint=?",
            (identity,),
        ).fetchone()
        if row is None:
            raise KeyError(identity)
        require(row[:2] == (cls.__name__, "1.0"), "orthogonalization family/schema corruption")
        value = deserialize(row[2])
        require(
            type(value) is cls and value.fingerprint == identity,
            "orthogonalization hash corruption",
        )
        self._orthogonalization_check_bounds(value)
        require(
            self._connection.execute(
                "SELECT * FROM ort_records WHERE fingerprint=?", (identity,)
            ).fetchone()
            == orthogonalization_index(value),
            "orthogonalization relational index corruption",
        )
        from afre.orthogonalization.lineage import orthogonalization_edges

        require(
            tuple(
                r[0]
                for r in self._connection.execute(
                    (
                        "SELECT reference_id FROM ort_links WHERE fingerprint=? "
                        "ORDER BY reference_id"
                    ),
                    (identity,),
                )
            )
            == tuple(sorted(set(orthogonalization_edges(value)))),
            "orthogonalization link index corruption",
        )
        return cast(A, value)

    def get_any(self, identity: str) -> Artifact:
        if not identity.startswith("afre.ort_"):
            return super().get_any(identity)
        row = self._connection.execute(
            "SELECT type_name FROM ort_artifacts WHERE fingerprint=?", (identity,)
        ).fetchone()
        classes = {c.__name__: c for c in ORTHOGONALIZATION_TYPES}
        require(row is not None and row[0] in classes, "unresolved orthogonalization reference")
        assert row is not None
        return self.resolve(classes[row[0]], identity)

    def _validate_links(self, value: Artifact) -> None:
        if type(value) not in ORTHOGONALIZATION_TYPES:
            super()._validate_links(value)
            return
        if value.fingerprint not in self._orthogonalization_validated:
            from afre.orthogonalization.validation import validate_orthogonalization

            validate_orthogonalization(self, value)
            self._orthogonalization_validated.add(value.fingerprint)

    def audit(self) -> int:
        if not self._reading and not self._in_transaction:
            with self.read_snapshot():
                return self.audit()
        count = super().audit()
        with self.validation_cache():
            for identity, name in self._connection.execute(
                "SELECT fingerprint,type_name FROM ort_artifacts"
            ):
                require(
                    name in {c.__name__ for c in ORTHOGONALIZATION_TYPES},
                    "unknown orthogonalization family",
                )
                self._validate_links(self.get_any(identity))
                count += 1
            for table in ("ort_links", "ort_records"):
                require(
                    self._connection.execute(
                        f"SELECT count(*) FROM {table} r LEFT JOIN ort_artifacts a "
                        "ON r.fingerprint=a.fingerprint WHERE a.fingerprint IS NULL"
                    ).fetchone()[0]
                    == 0,
                    "orphan orthogonalization projection",
                )
        return count

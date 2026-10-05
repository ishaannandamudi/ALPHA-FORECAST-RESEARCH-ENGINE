"""Store 1.8 / SQLite 9, preserving the exact AFRE-0 through AFRE-7 registry."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import ClassVar, TypeVar, cast

from afre.calibration.repository import CalibrationRepository
from afre.calibration.storage import calibration_schema
from afre.feature_store.repository import feature_store_schema
from afre.ids import validate_fingerprint
from afre.multihorizon.artifacts import (
    AlignedTrainRow,
    ConsistencyAudit,
    CovarianceArtifact,
    HorizonEvaluation,
    HorizonForecastEntry,
    HorizonTrainEvidence,
    MultiHorizonEvaluation,
    MultiHorizonFitRun,
    MultiHorizonForecast,
    MultiHorizonLineageAudit,
    SharedParameters,
    SharedPointForecast,
    SurfaceRow,
    SurfaceValue,
)
from afre.multihorizon.bounds import check_bounds
from afre.multihorizon.definitions import (
    HorizonModelBinding,
    MultiHorizonModelSpec,
    ParameterSharing,
)
from afre.multihorizon.horizon_sets import HorizonSet
from afre.multihorizon.schema import MultiHorizonBounds
from afre.multihorizon.storage import multihorizon_indexes, multihorizon_schema
from afre.persistence import _schema_statements
from afre.probabilistic.storage import probabilistic_schema
from afre.research_datasets.storage import dataset_schema
from afre.schema import Artifact, require
from afre.serialization import canonical_json, deserialize
from afre.statistical_models.storage import model_schema
from afre.target_engine.repository import target_schema
from afre.universe.repository import universe_schema

MULTIHORIZON_TYPES: tuple[type[Artifact], ...] = (
    MultiHorizonBounds,
    HorizonSet,
    HorizonModelBinding,
    ParameterSharing,
    MultiHorizonModelSpec,
    AlignedTrainRow,
    HorizonTrainEvidence,
    SharedParameters,
    MultiHorizonFitRun,
    CovarianceArtifact,
    SharedPointForecast,
    HorizonForecastEntry,
    MultiHorizonForecast,
    SurfaceValue,
    SurfaceRow,
    ConsistencyAudit,
    HorizonEvaluation,
    MultiHorizonEvaluation,
    MultiHorizonLineageAudit,
)
M = TypeVar("M", bound=Artifact)


class MultiHorizonRepository(CalibrationRepository):
    _snapshot_engine_version: ClassVar[str] = "0.9.0"

    def __init__(self, path: str | Path, bounds: MultiHorizonBounds | None = None) -> None:
        self.multihorizon_bounds = bounds or MultiHorizonBounds()
        self._multihorizon_validated: set[str] = set()
        super().__init__(path)

    @contextmanager
    def validation_cache(self) -> Iterator[None]:
        with super().validation_cache():
            try:
                yield
            finally:
                self._multihorizon_validated.clear()

    def _migrate(self) -> None:
        version = self._connection.execute("PRAGMA user_version").fetchone()[0]
        require(version in range(10), "unknown future multi-horizon store version")
        if version == 9:
            return
        if version < 8:
            CalibrationRepository._migrate(self)
        with self.transaction():
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 9:
                return
            require(version == 8, "unexpected multi-horizon migration version")
            CalibrationRepository._validate_layout(self)
            for statement in multihorizon_schema():
                self._connection.execute(statement)
            self._connection.executemany(
                "INSERT INTO metadata VALUES (?, ?)",
                (
                    ("multihorizon_store_schema_version", "1.8"),
                    ("multihorizon_schema", "1.0"),
                    ("multihorizon_engine_version", "0.9.0"),
                ),
            )
            self._connection.execute("PRAGMA user_version = 9")

    def _validate_layout(self) -> None:
        statements = (
            *_schema_statements(),
            *feature_store_schema(),
            *target_schema(),
            *universe_schema(),
            *dataset_schema(),
            *model_schema(),
            *probabilistic_schema(),
            *calibration_schema(),
            *multihorizon_schema(),
        )
        expected = {s.split()[2]: s for s in statements}
        actual = dict(
            self._connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        )
        require(expected == actual, "multi-horizon schema/index/trigger corruption")
        metadata = {
            "schema_version": "1.0",
            "engine_version": "0.1.0",
            "store_schema_version": "1.1",
            "feature_store_schema": "1.0",
            "feature_store_engine_version": "0.2.0",
            "target_store_schema_version": "1.2",
            "target_schema": "1.0",
            "target_engine_version": "0.3.0",
            "universe_store_schema_version": "1.3",
            "universe_schema": "1.0",
            "universe_engine_version": "0.4.0",
            "research_store_schema_version": "1.4",
            "dataset_schema": "1.0",
            "research_engine_version": "0.5.0",
            "model_store_schema_version": "1.5",
            "model_schema": "1.0",
            "model_engine_version": "0.6.0",
            "probabilistic_store_schema_version": "1.6",
            "probabilistic_schema": "1.0",
            "probabilistic_engine_version": "0.7.0",
            "calibration_store_schema_version": "1.7",
            "calibration_schema": "1.0",
            "calibration_engine_version": "0.8.0",
            "multihorizon_store_schema_version": "1.8",
            "multihorizon_schema": "1.0",
            "multihorizon_engine_version": "0.9.0",
        }
        require(
            dict(self._connection.execute("SELECT key,value FROM metadata")) == metadata,
            "multi-horizon metadata corruption",
        )
        require(
            self._connection.execute("PRAGMA user_version").fetchone()[0] == 9,
            "multi-horizon integer version corruption",
        )

    def check_multihorizon_bounds(self, value: Artifact) -> None:
        check_bounds(value, self.multihorizon_bounds)

    def put(self, value: Artifact) -> str:
        if type(value) not in MULTIHORIZON_TYPES:
            return super().put(value)
        require(self._in_transaction, "multi-horizon write requires transaction")
        self.check_multihorizon_bounds(value)
        identity, payload = value.fingerprint, canonical_json(value)
        require(deserialize(payload) == value, "multi-horizon canonical mismatch")
        if self._connection.execute(
            "SELECT 1 FROM mh_artifacts WHERE fingerprint=?", (identity,)
        ).fetchone():
            require(
                self.get(type(value), identity) == value, "conflicting multi-horizon payload"
            )
            return identity
        for cls, bound in (
            (MultiHorizonForecast, self.multihorizon_bounds.forecasts),
            (MultiHorizonEvaluation, self.multihorizon_bounds.evaluations),
        ):
            if isinstance(value, cls):
                require(
                    self._connection.execute(
                        "SELECT count(*) FROM mh_artifacts WHERE type_name=?", (cls.__name__,)
                    ).fetchone()[0]
                    < bound,
                    "stored multi-horizon result bound",
                )
        self._validate_links(value)
        self._connection.execute(
            "INSERT INTO mh_artifacts VALUES (?, ?, ?, ?)",
            (identity, type(value).__name__, "1.0", payload),
        )
        for table, values in multihorizon_indexes(value, identity):
            self._connection.execute(
                f"INSERT INTO {table} VALUES ({','.join('?' for _ in values)})", values
            )
        return identity

    def get(self, cls: type[M], identity: str) -> M:
        if cls not in MULTIHORIZON_TYPES:
            return super().get(cls, identity)
        validate_fingerprint(identity, cls.domain)
        row = self._connection.execute(
            "SELECT type_name,schema_version,payload FROM mh_artifacts WHERE fingerprint=?",
            (identity,),
        ).fetchone()
        if row is None:
            raise KeyError(identity)
        require(row[:2] == (cls.__name__, "1.0"), "multi-horizon family/schema corruption")
        value = deserialize(row[2])
        require(
            type(value) is cls and value.fingerprint == identity,
            "multi-horizon hash corruption",
        )
        self.check_multihorizon_bounds(value)
        expected = multihorizon_indexes(value, identity)
        actual = (
            (
                "mh_records",
                self._connection.execute(
                    "SELECT * FROM mh_records WHERE fingerprint=?", (identity,)
                ).fetchone(),
            ),
            *(
                ("mh_targets", r)
                for r in self._connection.execute(
                    "SELECT * FROM mh_targets WHERE fingerprint=? ORDER BY target_id",
                    (identity,),
                )
            ),
        )
        require(expected == actual, "multi-horizon relational index corruption")
        return cast(M, value)

    def get_any(self, identity: str) -> Artifact:
        if not identity.startswith("afre.mh_"):
            return super().get_any(identity)
        row = self._connection.execute(
            "SELECT type_name FROM mh_artifacts WHERE fingerprint=?", (identity,)
        ).fetchone()
        classes = {c.__name__: c for c in MULTIHORIZON_TYPES}
        require(row is not None and row[0] in classes, "unresolved multi-horizon reference")
        assert row is not None
        return self.resolve(classes[row[0]], identity)

    def _validate_links(self, value: Artifact) -> None:
        if type(value) not in MULTIHORIZON_TYPES:
            super()._validate_links(value)
            return
        from afre.multihorizon.validation import validate_links

        identity = self.identity(value)
        if identity not in self._multihorizon_validated:
            validate_links(self, value)
            self._multihorizon_validated.add(identity)

    def audit(self) -> int:
        if not self._reading and not self._in_transaction:
            with self.read_snapshot():
                return self.audit()
        count = super().audit()
        with self.validation_cache():
            classes = {c.__name__: c for c in MULTIHORIZON_TYPES}
            for identity, name in self._connection.execute(
                "SELECT fingerprint,type_name FROM mh_artifacts"
            ):
                require(name in classes, "unknown multi-horizon family")
                self._validate_links(self.resolve(classes[name], identity))
                count += 1
            for table in ("mh_records", "mh_targets"):
                require(
                    self._connection.execute(
                        f"SELECT count(*) FROM {table} LEFT JOIN mh_artifacts a ON "
                        f"{table}.fingerprint=a.fingerprint WHERE a.fingerprint IS NULL"
                    ).fetchone()[0]
                    == 0,
                    "orphan multi-horizon index",
                )
        return count

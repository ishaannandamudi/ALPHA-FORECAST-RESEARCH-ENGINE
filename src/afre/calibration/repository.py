"""Shared store 1.7 / SQLite 8: additive calibration, frozen earlier stores."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import ClassVar, TypeVar, cast

from afre.calibration.artifacts import (
    CalibratedForecast,
    CalibrationComparison,
    CalibrationDiagnostics,
    CalibrationDriftDiagnostics,
    CalibrationEvaluation,
    CalibrationFitInputs,
    CalibrationFitRun,
    CalibrationLineageAudit,
    CalibrationObservationSet,
    CalibrationState,
    ConformalScoreSet,
    ProbabilityMapping,
    QuantileOffset,
)
from afre.calibration.bounds import check_bounds
from afre.calibration.definitions import (
    CalibrationBinDefinition,
    CalibrationDriftSpec,
    CalibrationPartition,
    CalibrationRequest,
    CalibrationSpec,
)
from afre.calibration.fitting import FitBundle
from afre.calibration.schema import CalibrationBounds
from afre.calibration.storage import TABLE_FAMILIES, calibration_indexes, calibration_schema
from afre.feature_store.repository import feature_store_schema
from afre.ids import validate_fingerprint
from afre.persistence import _schema_statements
from afre.probabilistic.repository import ProbabilisticRepository
from afre.probabilistic.schema import ProbabilisticBounds
from afre.probabilistic.storage import probabilistic_schema
from afre.research_datasets.schema import DatasetBounds
from afre.research_datasets.storage import dataset_schema
from afre.schema import Artifact, require
from afre.serialization import canonical_json, deserialize
from afre.statistical_models.schema import ModelBounds
from afre.statistical_models.storage import model_schema
from afre.target_engine.repository import target_schema
from afre.universe.repository import universe_schema

CALIBRATION_TYPES: tuple[type[Artifact], ...] = (
    CalibrationBounds,
    CalibrationSpec,
    CalibrationPartition,
    CalibrationRequest,
    CalibrationBinDefinition,
    CalibrationDriftSpec,
    CalibrationObservationSet,
    ProbabilityMapping,
    QuantileOffset,
    ConformalScoreSet,
    CalibrationDiagnostics,
    CalibrationFitInputs,
    CalibrationState,
    CalibrationFitRun,
    CalibratedForecast,
    CalibrationEvaluation,
    CalibrationComparison,
    CalibrationDriftDiagnostics,
    CalibrationLineageAudit,
)
C = TypeVar("C", bound=Artifact)


class CalibrationRepository(ProbabilisticRepository):
    _snapshot_engine_version: ClassVar[str] = "0.8.0"

    def __init__(
        self,
        path: str | Path,
        bounds: CalibrationBounds | None = None,
        probabilistic_bounds: ProbabilisticBounds | None = None,
        model_bounds: ModelBounds | None = None,
        dataset_bounds: DatasetBounds | None = None,
    ) -> None:
        self.calibration_bounds = bounds or CalibrationBounds()
        self._calibration_validated: set[str] = set()
        self._calibration_bundles: dict[str, FitBundle] = {}
        super().__init__(path, probabilistic_bounds, model_bounds, dataset_bounds)

    @contextmanager
    def validation_cache(self) -> Iterator[None]:
        with super().validation_cache():
            try:
                yield
            finally:
                self._calibration_validated.clear()
                self._calibration_bundles.clear()

    def _migrate(self) -> None:
        version = self._connection.execute("PRAGMA user_version").fetchone()[0]
        require(version in range(9), "unknown future calibration store version")
        if version == 8:
            return
        if version < 7:
            ProbabilisticRepository._migrate(self)
        with self.transaction():
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 8:
                return
            require(version == 7, "unexpected calibration migration version")
            ProbabilisticRepository._validate_layout(self)
            for statement in calibration_schema():
                self._connection.execute(statement)
            self._connection.executemany(
                "INSERT INTO metadata VALUES (?, ?)",
                (
                    ("calibration_store_schema_version", "1.7"),
                    ("calibration_schema", "1.0"),
                    ("calibration_engine_version", "0.8.0"),
                ),
            )
            self._connection.execute("PRAGMA user_version = 8")

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
        )
        expected = {s.split()[2]: s for s in statements}
        actual = dict(
            self._connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        )
        require(expected == actual, "calibration schema/index/trigger corruption")
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
        }
        require(
            dict(self._connection.execute("SELECT key,value FROM metadata")) == metadata,
            "calibration metadata corruption",
        )
        require(
            self._connection.execute("PRAGMA user_version").fetchone()[0] == 8,
            "calibration integer version corruption",
        )

    def check_calibration_bounds(self, value: Artifact) -> None:
        check_bounds(value, self.calibration_bounds)

    def put(self, value: Artifact) -> str:
        if type(value) not in CALIBRATION_TYPES:
            return super().put(value)
        require(self._in_transaction, "calibration write requires transaction")
        self.check_calibration_bounds(value)
        identity, payload = value.fingerprint, canonical_json(value)
        require(deserialize(payload) == value, "calibration canonical validation mismatch")
        if self._connection.execute(
            "SELECT 1 FROM c_artifacts WHERE fingerprint=?", (identity,)
        ).fetchone():
            require(self.get(type(value), identity) == value, "conflicting calibration payload")
            return identity
        for cls, table, bound in (
            (CalibratedForecast, "c_forecasts", self.calibration_bounds.forecasts),
            (CalibrationEvaluation, "c_evaluations", self.calibration_bounds.evaluations),
            (CalibrationDriftDiagnostics, "c_drifts", self.calibration_bounds.diagnostics),
        ):
            if isinstance(value, cls):
                require(
                    self._connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                    < bound,
                    "calibration stored result bound",
                )
        self._validate_links(value)
        self._connection.execute(
            "INSERT INTO c_artifacts VALUES (?, ?, ?, ?)",
            (identity, type(value).__name__, "1.0", payload),
        )
        for table, values in calibration_indexes(value, identity):
            self._connection.execute(
                f"INSERT INTO {table} VALUES ({','.join('?' for _ in values)})", values
            )
        return identity

    def get(self, cls: type[C], identity: str) -> C:
        if cls not in CALIBRATION_TYPES:
            return super().get(cls, identity)
        validate_fingerprint(identity, cls.domain)
        row = self._connection.execute(
            "SELECT type_name,schema_version,payload FROM c_artifacts WHERE fingerprint=?",
            (identity,),
        ).fetchone()
        if row is None:
            raise KeyError(identity)
        require(row[:2] == (cls.__name__, "1.0"), "calibration family/schema corruption")
        value = deserialize(row[2])
        require(
            type(value) is cls and value.fingerprint == identity,
            "calibration payload/fingerprint corruption",
        )
        self.check_calibration_bounds(value)
        for table, values in calibration_indexes(value, identity):
            require(
                self._connection.execute(
                    f"SELECT * FROM {table} WHERE fingerprint=?", (identity,)
                ).fetchone()
                == values,
                "calibration relational index corruption",
            )
        return cast(C, value)

    def get_any(self, identity: str) -> Artifact:
        if not identity.startswith("afre.c_"):
            return super().get_any(identity)
        row = self._connection.execute(
            "SELECT type_name FROM c_artifacts WHERE fingerprint=?", (identity,)
        ).fetchone()
        classes = {c.__name__: c for c in CALIBRATION_TYPES}
        require(row is not None and row[0] in classes, "unresolved calibration reference")
        assert row is not None
        return self.resolve(classes[row[0]], identity)

    def _validate_links(self, value: Artifact) -> None:
        if type(value) not in CALIBRATION_TYPES:
            super()._validate_links(value)
            return
        from afre.calibration.validation import validate_calibration_links

        identity = self.identity(value)
        if identity not in self._calibration_validated:
            validate_calibration_links(self, value)
            self._calibration_validated.add(identity)

    def calibration_history(self, raw_model_id: str) -> tuple[CalibrationFitRun, ...]:
        rows = self._connection.execute(
            (
                "SELECT fingerprint FROM c_fits WHERE raw_model_id=? ORDER BY "
                "available_ns,spec_id,fingerprint"
            ),
            (raw_model_id,),
        ).fetchall()
        require(len(rows) <= self.calibration_bounds.evaluations, "calibration history bound")
        return tuple(self.resolve(CalibrationFitRun, r[0]) for r in rows)

    def audit(self) -> int:
        if not self._reading and not self._in_transaction:
            with self.read_snapshot():
                return self.audit()
        count = super().audit()
        with self.validation_cache():
            classes = {c.__name__: c for c in CALIBRATION_TYPES}
            for identity, name in self._connection.execute(
                "SELECT fingerprint,type_name FROM c_artifacts"
            ):
                require(name in classes, "unknown calibration family")
                self._validate_links(self.resolve(classes[name], identity))
                count += 1
            for table, family in TABLE_FAMILIES:
                require(
                    self._connection.execute(
                        (
                            f"SELECT count(*) FROM {table} LEFT JOIN c_artifacts a ON "
                            f"{table}.fingerprint=a.fingerprint WHERE a.fingerprint IS NULL OR "
                            f"a.type_name!=?"
                        ),
                        (family,),
                    ).fetchone()[0]
                    == 0,
                    "orphan calibration index",
                )
        return count

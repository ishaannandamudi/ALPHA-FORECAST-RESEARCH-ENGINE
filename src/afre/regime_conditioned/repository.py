"""Store1.11 / SQLite12, preserving every earlier registry row, DDL and metadata."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import ClassVar, TypeVar, cast

from afre.calibration.storage import calibration_schema
from afre.cross_sectional.storage import cross_section_schema
from afre.event_conditioned.repository import EventRepository
from afre.event_conditioned.storage import event_schema
from afre.feature_store.repository import feature_store_schema
from afre.ids import validate_fingerprint
from afre.multihorizon.storage import multihorizon_schema
from afre.persistence import _schema_statements
from afre.probabilistic.storage import probabilistic_schema
from afre.regime_conditioned.artifacts import (
    RegimeAudit,
    RegimeCalibrationAssessment,
    RegimeConditionedEvaluation,
    RegimeConditionedForecast,
    RegimeConditionedModel,
    RegimeConditionedSample,
    RegimeDriftDiagnostic,
    RegimeEvaluationPair,
    RegimeGroupMetric,
    RegimeMatchSet,
    RegimeRankEvaluation,
    RegimeRanking,
    RegimeSoftDiagnostic,
    RegimeStateFit,
    RegimeTransition,
)
from afre.regime_conditioned.bounds import artifact_limit, check_regime_bounds
from afre.regime_conditioned.definitions import RegimeConditioningSpec
from afre.regime_conditioned.memberships import RegimeMembership
from afre.regime_conditioned.regimes import (
    RegimeProviderReference,
    RegimeSnapshot,
    RegimeSubject,
    RegimeTaxonomy,
)
from afre.regime_conditioned.schema import RegimeBounds
from afre.regime_conditioned.storage import regime_index, regime_schema
from afre.research_datasets.storage import dataset_schema
from afre.schema import Artifact, require
from afre.serialization import canonical_json, deserialize
from afre.statistical_models.storage import model_schema
from afre.target_engine.repository import target_schema
from afre.universe.repository import universe_schema

REGIME_TYPES: tuple[type[Artifact], ...] = (
    RegimeAudit,
    RegimeCalibrationAssessment,
    RegimeConditionedEvaluation,
    RegimeConditionedForecast,
    RegimeConditionedModel,
    RegimeConditionedSample,
    RegimeDriftDiagnostic,
    RegimeEvaluationPair,
    RegimeGroupMetric,
    RegimeMatchSet,
    RegimeRankEvaluation,
    RegimeRanking,
    RegimeSoftDiagnostic,
    RegimeStateFit,
    RegimeTransition,
    RegimeConditioningSpec,
    RegimeMembership,
    RegimeProviderReference,
    RegimeSnapshot,
    RegimeSubject,
    RegimeTaxonomy,
    RegimeBounds,
)
A = TypeVar("A", bound=Artifact)


class RegimeRepository(EventRepository):
    _snapshot_engine_version: ClassVar[str] = "0.12.0"

    def __init__(self, path: str | Path, bounds: RegimeBounds | None = None) -> None:
        self.regime_bounds = bounds or RegimeBounds()
        self._regime_validated: set[str] = set()
        super().__init__(path)

    @contextmanager
    def validation_cache(self) -> Iterator[None]:
        with super().validation_cache():
            try:
                yield
            finally:
                self._regime_validated.clear()

    def _migrate(self) -> None:
        version = self._connection.execute("PRAGMA user_version").fetchone()[0]
        require(version in range(13), "unknown future regime store version")
        if version == 12:
            return
        if version < 11:
            EventRepository._migrate(self)
        with self.transaction():
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 12:
                return
            require(version == 11, "unexpected regime migration version")
            EventRepository._validate_layout(self)
            for statement in regime_schema():
                self._connection.execute(statement)
            self._connection.executemany(
                "INSERT INTO metadata VALUES (?,?)",
                (
                    ("regime_store_schema_version", "1.11"),
                    ("regime_conditioned_schema", "1.0"),
                    ("regime_conditioned_engine_version", "0.12.0"),
                ),
            )
            self._connection.execute("PRAGMA user_version=12")

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
            *cross_section_schema(),
            *event_schema(),
            *regime_schema(),
        )
        require(
            {s.split()[2]: s for s in statements}
            == dict(
                self._connection.execute(
                    "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
                )
            ),
            "regime schema/index/trigger corruption",
        )
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
            "cross_sectional_store_schema_version": "1.9",
            "cross_sectional_schema": "1.0",
            "cross_sectional_engine_version": "0.10.0",
            "event_store_schema_version": "1.10",
            "event_conditioned_schema": "1.0",
            "event_conditioned_engine_version": "0.11.0",
            "regime_store_schema_version": "1.11",
            "regime_conditioned_schema": "1.0",
            "regime_conditioned_engine_version": "0.12.0",
        }
        require(
            dict(self._connection.execute("SELECT key,value FROM metadata")) == metadata,
            "regime metadata corruption",
        )
        require(
            self._connection.execute("PRAGMA user_version").fetchone()[0] == 12,
            "regime integer version corruption",
        )

    def put(self, value: Artifact) -> str:
        if type(value) not in REGIME_TYPES:
            return super().put(value)
        require(self._in_transaction, "regime write requires transaction")
        check_regime_bounds(value, self.regime_bounds)
        identity, payload = value.fingerprint, canonical_json(value)
        require(deserialize(payload) == value, "regime canonical mismatch")
        if self._connection.execute(
            "SELECT 1 FROM rc_artifacts WHERE fingerprint=?", (identity,)
        ).fetchone():
            require(self.get(type(value), identity) == value, "conflicting regime payload")
            return identity
        count = self._connection.execute(
            "SELECT count(*) FROM rc_artifacts WHERE type_name=?", (type(value).__name__,)
        ).fetchone()[0]
        require(
            count < artifact_limit(value, self.regime_bounds), "stored regime artifact bound"
        )
        self._validate_links(value)
        self._connection.execute(
            "INSERT INTO rc_artifacts VALUES (?,?,?,?)",
            (identity, type(value).__name__, "1.0", payload),
        )
        self._connection.execute(
            "INSERT INTO rc_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            regime_index(value),
        )
        return identity

    def get(self, cls: type[A], identity: str) -> A:
        if cls not in REGIME_TYPES:
            return super().get(cls, identity)
        validate_fingerprint(identity, cls.domain)
        row = self._connection.execute(
            "SELECT type_name,schema_version,payload FROM rc_artifacts WHERE fingerprint=?",
            (identity,),
        ).fetchone()
        if row is None:
            raise KeyError(identity)
        require(row[:2] == (cls.__name__, "1.0"), "regime family/schema corruption")
        value = deserialize(row[2])
        require(type(value) is cls and value.fingerprint == identity, "regime hash corruption")
        check_regime_bounds(value, self.regime_bounds)
        require(
            self._connection.execute(
                "SELECT * FROM rc_records WHERE fingerprint=?", (identity,)
            ).fetchone()
            == regime_index(value),
            "regime relational index corruption",
        )
        return cast(A, value)

    def get_any(self, identity: str) -> Artifact:
        if not identity.startswith("afre.rc_"):
            return super().get_any(identity)
        row = self._connection.execute(
            "SELECT type_name FROM rc_artifacts WHERE fingerprint=?", (identity,)
        ).fetchone()
        classes = {c.__name__: c for c in REGIME_TYPES}
        require(row is not None and row[0] in classes, "unresolved regime reference")
        assert row is not None
        return self.resolve(classes[row[0]], identity)

    def _validate_links(self, value: Artifact) -> None:
        if type(value) not in REGIME_TYPES:
            super()._validate_links(value)
            return
        from afre.regime_conditioned.validation import validate_regime

        if value.fingerprint not in self._regime_validated:
            validate_regime(self, value)
            self._regime_validated.add(value.fingerprint)

    def audit(self) -> int:
        if not self._reading and not self._in_transaction:
            with self.read_snapshot():
                return self.audit()
        count = super().audit()
        with self.validation_cache():
            for identity, name in self._connection.execute(
                "SELECT fingerprint,type_name FROM rc_artifacts"
            ):
                require(name in {c.__name__ for c in REGIME_TYPES}, "unknown regime family")
                self._validate_links(self.get_any(identity))
                count += 1
            require(
                self._connection.execute(
                    "SELECT count(*) FROM rc_records r LEFT JOIN rc_artifacts a ON "
                    "r.fingerprint=a.fingerprint WHERE a.fingerprint IS NULL"
                ).fetchone()[0]
                == 0,
                "orphan regime index",
            )
        return count

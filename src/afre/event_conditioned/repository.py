"""Store1.10 / SQLite11, preserving every earlier registry row, DDL and metadata."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import ClassVar, TypeVar, cast

from afre.calibration.storage import calibration_schema
from afre.cross_sectional.repository import CrossSectionRepository
from afre.cross_sectional.storage import cross_section_schema
from afre.event_conditioned.artifacts import (
    EventAudit,
    EventCalibrationAssessment,
    EventConditionedEvaluation,
    EventConditionedForecast,
    EventConditionedModel,
    EventConditionedObservation,
    EventEvaluationPair,
    EventGroupMetric,
    EventMatchSet,
    EventRankEvaluation,
    EventRanking,
)
from afre.event_conditioned.bounds import check_event_bounds
from afre.event_conditioned.definitions import (
    EventConditioningSpec,
    EventValueRule,
    EventWindowSpec,
)
from afre.event_conditioned.events import (
    EventReference,
    EventSubject,
    EventSurprise,
    EventValue,
)
from afre.event_conditioned.schema import EventBounds
from afre.event_conditioned.storage import event_index, event_schema
from afre.feature_store.repository import feature_store_schema
from afre.ids import validate_fingerprint
from afre.multihorizon.storage import multihorizon_schema
from afre.persistence import _schema_statements
from afre.probabilistic.storage import probabilistic_schema
from afre.research_datasets.storage import dataset_schema
from afre.schema import Artifact, require
from afre.serialization import canonical_json, deserialize
from afre.statistical_models.storage import model_schema
from afre.target_engine.repository import target_schema
from afre.universe.repository import universe_schema

EVENT_TYPES: tuple[type[Artifact], ...] = (
    EventAudit,
    EventCalibrationAssessment,
    EventConditionedEvaluation,
    EventConditionedForecast,
    EventConditionedModel,
    EventConditionedObservation,
    EventEvaluationPair,
    EventGroupMetric,
    EventMatchSet,
    EventRankEvaluation,
    EventRanking,
    EventConditioningSpec,
    EventValueRule,
    EventWindowSpec,
    EventReference,
    EventSubject,
    EventSurprise,
    EventValue,
    EventBounds,
)
A = TypeVar("A", bound=Artifact)


class EventRepository(CrossSectionRepository):
    _snapshot_engine_version: ClassVar[str] = "0.11.0"

    def __init__(self, path: str | Path, bounds: EventBounds | None = None) -> None:
        self.event_bounds = bounds or EventBounds()
        self._event_validated: set[str] = set()
        super().__init__(path)

    @contextmanager
    def validation_cache(self) -> Iterator[None]:
        with super().validation_cache():
            try:
                yield
            finally:
                self._event_validated.clear()

    def _migrate(self) -> None:
        version = self._connection.execute("PRAGMA user_version").fetchone()[0]
        require(version in range(12), "unknown future event store version")
        if version == 11:
            return
        if version < 10:
            CrossSectionRepository._migrate(self)
        with self.transaction():
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 11:
                return
            require(version == 10, "unexpected event migration version")
            CrossSectionRepository._validate_layout(self)
            for statement in event_schema():
                self._connection.execute(statement)
            self._connection.executemany(
                "INSERT INTO metadata VALUES (?,?)",
                (
                    ("event_store_schema_version", "1.10"),
                    ("event_conditioned_schema", "1.0"),
                    ("event_conditioned_engine_version", "0.11.0"),
                ),
            )
            self._connection.execute("PRAGMA user_version=11")

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
        )
        require(
            {s.split()[2]: s for s in statements}
            == dict(
                self._connection.execute(
                    "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
                )
            ),
            "event schema/index/trigger corruption",
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
        }
        require(
            dict(self._connection.execute("SELECT key,value FROM metadata")) == metadata,
            "event metadata corruption",
        )
        require(
            self._connection.execute("PRAGMA user_version").fetchone()[0] == 11,
            "event integer version corruption",
        )

    def put(self, value: Artifact) -> str:
        if type(value) not in EVENT_TYPES:
            return super().put(value)
        require(self._in_transaction, "event write requires transaction")
        check_event_bounds(value, self.event_bounds)
        identity, payload = value.fingerprint, canonical_json(value)
        require(deserialize(payload) == value, "event canonical mismatch")
        if self._connection.execute(
            "SELECT 1 FROM ec_artifacts WHERE fingerprint=?", (identity,)
        ).fetchone():
            require(self.get(type(value), identity) == value, "conflicting event payload")
            return identity
        count = self._connection.execute(
            "SELECT count(*) FROM ec_artifacts WHERE type_name=?", (type(value).__name__,)
        ).fetchone()[0]
        require(
            count
            < (
                self.event_bounds.events
                if isinstance(value, EventReference)
                else self.event_bounds.samples
            ),
            "stored event artifact bound",
        )
        self._validate_links(value)
        self._connection.execute(
            "INSERT INTO ec_artifacts VALUES (?,?,?,?)",
            (identity, type(value).__name__, "1.0", payload),
        )
        self._connection.execute(
            "INSERT INTO ec_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", event_index(value)
        )
        return identity

    def get(self, cls: type[A], identity: str) -> A:
        if cls not in EVENT_TYPES:
            return super().get(cls, identity)
        validate_fingerprint(identity, cls.domain)
        row = self._connection.execute(
            "SELECT type_name,schema_version,payload FROM ec_artifacts WHERE fingerprint=?",
            (identity,),
        ).fetchone()
        if row is None:
            raise KeyError(identity)
        require(row[:2] == (cls.__name__, "1.0"), "event family/schema corruption")
        value = deserialize(row[2])
        require(type(value) is cls and value.fingerprint == identity, "event hash corruption")
        check_event_bounds(value, self.event_bounds)
        require(
            self._connection.execute(
                "SELECT * FROM ec_records WHERE fingerprint=?", (identity,)
            ).fetchone()
            == event_index(value),
            "event relational index corruption",
        )
        return cast(A, value)

    def get_any(self, identity: str) -> Artifact:
        if not identity.startswith("afre.ec_"):
            return super().get_any(identity)
        row = self._connection.execute(
            "SELECT type_name FROM ec_artifacts WHERE fingerprint=?", (identity,)
        ).fetchone()
        classes = {c.__name__: c for c in EVENT_TYPES}
        require(row is not None and row[0] in classes, "unresolved event reference")
        assert row is not None
        return self.resolve(classes[row[0]], identity)

    def _validate_links(self, value: Artifact) -> None:
        if type(value) not in EVENT_TYPES:
            super()._validate_links(value)
            return
        from afre.event_conditioned.validation import validate_event

        if value.fingerprint not in self._event_validated:
            validate_event(self, value)
            self._event_validated.add(value.fingerprint)

    def audit(self) -> int:
        if not self._reading and not self._in_transaction:
            with self.read_snapshot():
                return self.audit()
        count = super().audit()
        with self.validation_cache():
            for identity, name in self._connection.execute(
                "SELECT fingerprint,type_name FROM ec_artifacts"
            ):
                require(name in {c.__name__ for c in EVENT_TYPES}, "unknown event family")
                self._validate_links(self.get_any(identity))
                count += 1
            require(
                self._connection.execute(
                    "SELECT count(*) FROM ec_records r LEFT JOIN ec_artifacts a ON "
                    "r.fingerprint=a.fingerprint WHERE a.fingerprint IS NULL"
                ).fetchone()[0]
                == 0,
                "orphan event index",
            )
        return count

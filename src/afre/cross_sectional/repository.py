"""Store 1.9 / SQLite 10; additive over the frozen AFRE-0 through AFRE-8 registry."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import ClassVar, TypeVar, cast

from afre.calibration.storage import calibration_schema
from afre.cross_sectional.artifacts import (
    CrossSectionAudit,
    CrossSectionEvaluation,
    CrossSectionObservation,
    CrossSectionRanking,
    CrossSectionTruth,
    ICSeries,
    PeerState,
    RankEntry,
    RankStability,
    RawScore,
    ScoreBucket,
    TruthRow,
)
from afre.cross_sectional.bounds import check_bounds
from afre.cross_sectional.definitions import (
    CrossSectionIdentity,
    CrossSectionSpec,
    GroupPolicy,
    NormalizationPolicy,
    ScoreSpec,
)
from afre.cross_sectional.external import ExternalSignal
from afre.cross_sectional.groups import GroupMembership
from afre.cross_sectional.models import (
    CrossSectionModel,
    CrossSectionModelSpec,
    CrossSectionPrediction,
)
from afre.cross_sectional.schema import CrossSectionBounds
from afre.cross_sectional.storage import cross_section_indexes, cross_section_schema
from afre.feature_store.repository import feature_store_schema
from afre.ids import validate_fingerprint
from afre.multihorizon.repository import MultiHorizonRepository
from afre.multihorizon.storage import multihorizon_schema
from afre.persistence import _schema_statements
from afre.probabilistic.storage import probabilistic_schema
from afre.research_datasets.storage import dataset_schema
from afre.schema import Artifact, require
from afre.serialization import canonical_json, deserialize
from afre.statistical_models.storage import model_schema
from afre.target_engine.repository import target_schema
from afre.universe.repository import universe_schema

CROSS_SECTION_TYPES: tuple[type[Artifact], ...] = (
    CrossSectionBounds,
    CrossSectionIdentity,
    CrossSectionSpec,
    GroupPolicy,
    NormalizationPolicy,
    ScoreSpec,
    ExternalSignal,
    GroupMembership,
    CrossSectionObservation,
    RawScore,
    PeerState,
    RankEntry,
    CrossSectionRanking,
    TruthRow,
    CrossSectionTruth,
    ScoreBucket,
    CrossSectionEvaluation,
    ICSeries,
    RankStability,
    CrossSectionAudit,
    CrossSectionModelSpec,
    CrossSectionModel,
    CrossSectionPrediction,
)
M = TypeVar("M", bound=Artifact)


class CrossSectionRepository(MultiHorizonRepository):
    _snapshot_engine_version: ClassVar[str] = "0.10.0"

    def __init__(self, path: str | Path, bounds: CrossSectionBounds | None = None) -> None:
        self.cross_section_bounds = bounds or CrossSectionBounds()
        self._cross_section_validated: set[str] = set()
        super().__init__(path)

    @contextmanager
    def validation_cache(self) -> Iterator[None]:
        with super().validation_cache():
            try:
                yield
            finally:
                self._cross_section_validated.clear()

    def _migrate(self) -> None:
        version = self._connection.execute("PRAGMA user_version").fetchone()[0]
        require(version in range(11), "unknown future cross-sectional store version")
        if version == 10:
            return
        if version < 9:
            MultiHorizonRepository._migrate(self)
        with self.transaction():
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 10:
                return
            require(version == 9, "unexpected cross-sectional migration version")
            MultiHorizonRepository._validate_layout(self)
            for statement in cross_section_schema():
                self._connection.execute(statement)
            self._connection.executemany(
                "INSERT INTO metadata VALUES (?, ?)",
                (
                    ("cross_sectional_store_schema_version", "1.9"),
                    ("cross_sectional_schema", "1.0"),
                    ("cross_sectional_engine_version", "0.10.0"),
                ),
            )
            self._connection.execute("PRAGMA user_version = 10")

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
        )
        expected = {s.split()[2]: s for s in statements}
        actual = dict(
            self._connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        )
        require(expected == actual, "cross-sectional schema/index/trigger corruption")
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
        }
        require(
            dict(self._connection.execute("SELECT key,value FROM metadata")) == metadata,
            "cross-sectional metadata corruption",
        )
        require(
            self._connection.execute("PRAGMA user_version").fetchone()[0] == 10,
            "cross-sectional integer version corruption",
        )

    def check_cross_section_bounds(self, value: Artifact) -> None:
        check_bounds(value, self.cross_section_bounds)

    def put(self, value: Artifact) -> str:
        if type(value) not in CROSS_SECTION_TYPES:
            return super().put(value)
        require(self._in_transaction, "cross-sectional write requires transaction")
        self.check_cross_section_bounds(value)
        identity, payload = value.fingerprint, canonical_json(value)
        require(deserialize(payload) == value, "cross-sectional canonical mismatch")
        if self._connection.execute(
            "SELECT 1 FROM cs_artifacts WHERE fingerprint=?", (identity,)
        ).fetchone():
            require(
                self.get(type(value), identity) == value, "conflicting cross-sectional payload"
            )
            return identity
        for cls, bound in (
            (CrossSectionRanking, self.cross_section_bounds.rankings),
            (CrossSectionEvaluation, self.cross_section_bounds.rankings),
            (ExternalSignal, self.cross_section_bounds.external_signals),
            (GroupMembership, self.cross_section_bounds.external_signals),
            (CrossSectionTruth, self.cross_section_bounds.truths),
        ):
            if isinstance(value, cls):
                require(
                    self._connection.execute(
                        "SELECT count(*) FROM cs_artifacts WHERE type_name=?", (cls.__name__,)
                    ).fetchone()[0]
                    < bound,
                    "stored cross-sectional result bound",
                )
        self._validate_links(value)
        self._connection.execute(
            "INSERT INTO cs_artifacts VALUES (?, ?, ?, ?)",
            (identity, type(value).__name__, "1.0", payload),
        )
        for table, values in cross_section_indexes(value, identity):
            self._connection.execute(
                f"INSERT INTO {table} VALUES ({','.join('?' for _ in values)})", values
            )
        return identity

    def get(self, cls: type[M], identity: str) -> M:
        if cls not in CROSS_SECTION_TYPES:
            return super().get(cls, identity)
        validate_fingerprint(identity, cls.domain)
        row = self._connection.execute(
            "SELECT type_name,schema_version,payload FROM cs_artifacts WHERE fingerprint=?",
            (identity,),
        ).fetchone()
        if row is None:
            raise KeyError(identity)
        require(row[:2] == (cls.__name__, "1.0"), "cross-sectional family/schema corruption")
        value = deserialize(row[2])
        require(
            type(value) is cls and value.fingerprint == identity,
            "cross-sectional hash corruption",
        )
        self.check_cross_section_bounds(value)
        expected = cross_section_indexes(value, identity)
        actual = (
            (
                "cs_records",
                self._connection.execute(
                    "SELECT * FROM cs_records WHERE fingerprint=?", (identity,)
                ).fetchone(),
            ),
            *(
                ("cs_members", r)
                for r in self._connection.execute(
                    "SELECT * FROM cs_members WHERE fingerprint=? ORDER BY security_id",
                    (identity,),
                )
            ),
        )
        require(expected == actual, "cross-sectional relational index corruption")
        return cast(M, value)

    def get_any(self, identity: str) -> Artifact:
        if not identity.startswith("afre.cs_"):
            return super().get_any(identity)
        row = self._connection.execute(
            "SELECT type_name FROM cs_artifacts WHERE fingerprint=?", (identity,)
        ).fetchone()
        classes = {c.__name__: c for c in CROSS_SECTION_TYPES}
        require(row is not None and row[0] in classes, "unresolved cross-sectional reference")
        assert row is not None
        return self.resolve(classes[row[0]], identity)

    def _validate_links(self, value: Artifact) -> None:
        if type(value) not in CROSS_SECTION_TYPES:
            super()._validate_links(value)
            return
        from afre.cross_sectional.validation import validate_links

        identity = self.identity(value)
        if identity not in self._cross_section_validated:
            validate_links(self, value)
            self._cross_section_validated.add(identity)

    def audit(self) -> int:
        if not self._reading and not self._in_transaction:
            with self.read_snapshot():
                return self.audit()
        count = super().audit()
        with self.validation_cache():
            classes = {c.__name__: c for c in CROSS_SECTION_TYPES}
            for identity, name in self._connection.execute(
                "SELECT fingerprint,type_name FROM cs_artifacts"
            ):
                require(name in classes, "unknown cross-sectional family")
                self._validate_links(self.resolve(classes[name], identity))
                count += 1
            for table in ("cs_records", "cs_members"):
                require(
                    self._connection.execute(
                        f"SELECT count(*) FROM {table} LEFT JOIN cs_artifacts a ON "
                        f"{table}.fingerprint=a.fingerprint WHERE a.fingerprint IS NULL"
                    ).fetchone()[0]
                    == 0,
                    "orphan cross-sectional index",
                )
        return count

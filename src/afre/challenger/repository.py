"""Immutable additive SQLite24 repository with semantic replay before reuse."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import ClassVar, TypeVar, cast

from afre.challenger.artifacts import (
    ChallengerComparison,
    ChallengeRun,
    CommonMatchedEvidence,
    EvaluationEvidence,
    ParticipantMetricResult,
    PromotionAssessment,
    RollbackAssessment,
    ShadowForecast,
)
from afre.challenger.costs import ChallengeCostPlan
from afre.challenger.criteria import PromotionCriterion, RollbackCriterion
from afre.challenger.lineage import ChallengeAudit, challenge_edges
from afre.challenger.participants import ParticipantReference
from afre.challenger.programs import ChallengeMetricRequest, ChallengeProgram
from afre.challenger.schema import ChallengeBounds
from afre.challenger.storage import METADATA, all_statements, challenge_schema, record_index
from afre.challenger.windows import ChallengeWindow
from afre.health.guards import guard
from afre.health.repository import HealthRepository
from afre.ids import validate_fingerprint
from afre.schema import Artifact, require
from afre.serialization import canonical_json, deserialize

CHALLENGE_TYPES: tuple[type[Artifact], ...] = (
    ChallengeBounds,
    ChallengeWindow,
    ParticipantReference,
    ChallengeMetricRequest,
    ChallengeProgram,
    PromotionCriterion,
    RollbackCriterion,
    ChallengeCostPlan,
    ShadowForecast,
    EvaluationEvidence,
    CommonMatchedEvidence,
    ParticipantMetricResult,
    ChallengerComparison,
    PromotionAssessment,
    RollbackAssessment,
    ChallengeRun,
    ChallengeAudit,
)
A = TypeVar("A", bound=Artifact)


class ChallengeRepository(HealthRepository):
    _snapshot_engine_version: ClassVar[str] = "0.24.0"

    def __init__(self, path: str | Path, bounds: ChallengeBounds | None = None) -> None:
        self.challenge_bounds = bounds or ChallengeBounds()
        self._challenge_active: set[str] = set()
        self._challenge_validated: set[tuple[str, bool]] = set()
        self._challenge_pending: dict[str, Artifact] = {}
        super().__init__(path)

    @contextmanager
    def pending_results(self) -> Iterator[None]:
        require(
            self._reading and not self._challenge_pending,
            "pending results require one frozen read snapshot",
        )
        try:
            yield
        finally:
            self._challenge_pending.clear()

    def stage_result(self, value: Artifact) -> None:
        require(
            self._reading and type(value) in CHALLENGE_TYPES,
            "only challenge results staged inside frozen snapshot",
        )
        self._check_challenge_bounds(value)
        self._validate_links(value)
        self._challenge_pending[value.fingerprint] = value

    @contextmanager
    def validation_cache(self) -> Iterator[None]:
        outer = self._validation_cache is None
        with super().validation_cache():
            try:
                yield
            finally:
                if outer:
                    self._challenge_validated.clear()

    @contextmanager
    def read_snapshot(self) -> Iterator[None]:
        with super().read_snapshot():
            pages = self._connection.execute("PRAGMA page_count").fetchone()[0]
            page_size = self._connection.execute("PRAGMA page_size").fetchone()[0]
            require(
                pages * page_size <= self.challenge_bounds.snapshot_bytes,
                "challenge frozen snapshot byte bound",
            )
            yield

    def _migrate(self) -> None:
        version = self._connection.execute("PRAGMA user_version").fetchone()[0]
        require(version in range(25), "unknown future challenge store version")
        if version == 24:
            return
        if version < 23:
            HealthRepository._migrate(self)
        with self.transaction():
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 24:
                return
            require(version == 23, "unexpected challenge migration version")
            HealthRepository._validate_layout(self)
            for sql in challenge_schema():
                self._connection.execute(sql)
            self._connection.executemany(
                "INSERT INTO metadata VALUES (?,?)",
                (
                    ("challenge_store_schema_version", "1.23"),
                    ("challenge_schema", "1.0"),
                    ("challenge_engine_version", "0.24.0"),
                ),
            )
            self._connection.execute("PRAGMA user_version=24")

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
            "challenge layout corruption",
        )
        require(
            dict(self._connection.execute("SELECT key,value FROM metadata")) == METADATA
            and self._connection.execute("PRAGMA user_version").fetchone()[0] == 24,
            "challenge metadata/version corruption",
        )

    def _check_challenge_bounds(self, value: Artifact) -> None:
        b = self.challenge_bounds
        for name, maximum in (
            ("shadow_ids", b.shadow_rows),
            ("assignments", b.samples),
            ("truth_assignments", b.samples),
            ("sample_ids", b.samples),
            ("challenger_ids", b.challengers),
            ("requests", b.metrics),
            ("criterion_results", b.criteria),
            ("comparison_ids", b.comparisons),
            ("node_ids", b.lineage_nodes),
        ):
            require(
                len(getattr(value, name, ())) <= maximum, "configured challenge artifact bound"
            )
        require(
            len(canonical_json(value).encode()) <= b.payload_bytes,
            "challenge payload byte bound",
        )

    def get(self, cls: type[A], identity: str) -> A:
        guard(self, cls, identity)
        if cls not in CHALLENGE_TYPES:
            return super().get(cls, identity)
        validate_fingerprint(identity, cls.domain)
        if identity in self._challenge_pending:
            pending = self._challenge_pending[identity]
            require(type(pending) is cls, "pending exact result type")
            return cast(A, pending)
        row = self._connection.execute(
            "SELECT type_name,schema_version,CASE WHEN length(CAST(payload AS BLOB))<=? "
            "THEN payload ELSE NULL END FROM ch_artifacts WHERE fingerprint=?",
            (self.challenge_bounds.payload_bytes, identity),
        ).fetchone()
        if row is None:
            raise KeyError(identity)
        require(
            row[:2] == (cls.__name__, "1.0") and type(row[2]) is str,
            "challenge type/schema/payload bound or corruption",
        )
        value = deserialize(row[2])
        require(
            type(value) is cls and value.fingerprint == identity, "challenge hash corruption"
        )
        self._check_challenge_bounds(value)
        require(
            self._connection.execute(
                "SELECT * FROM ch_records WHERE fingerprint=?", (identity,)
            ).fetchone()
            == record_index(value),
            "challenge index corruption",
        )
        require(
            tuple(
                r[0]
                for r in self._connection.execute(
                    "SELECT reference_id FROM ch_links WHERE fingerprint=? "
                    "ORDER BY reference_id",
                    (identity,),
                )
            )
            == tuple(sorted(set(challenge_edges(value)))),
            "challenge link corruption",
        )
        return cast(A, value)

    def resolve(self, cls: type[A], identity: str) -> A:
        guard(self, cls, identity)
        if cls not in CHALLENGE_TYPES:
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
        if not identity.startswith("afre.ch_"):
            if self._validation_cache is not None and identity in self._validation_cache:
                guard(self, type(self._validation_cache[identity]), identity)
            value = super().get_any(identity)
            guard(self, type(value), identity)
            return value
        row = self._connection.execute(
            "SELECT type_name FROM ch_artifacts WHERE fingerprint=?", (identity,)
        ).fetchone()
        classes = {c.__name__: c for c in CHALLENGE_TYPES}
        require(row is not None and row[0] in classes, "unresolved challenge reference")
        assert row is not None
        return self.resolve(classes[row[0]], identity)

    def put(self, value: Artifact) -> str:
        if type(value) not in CHALLENGE_TYPES:
            return super().put(value)
        require(self._in_transaction, "challenge write requires transaction")
        self._check_challenge_bounds(value)
        payload = canonical_json(value)
        require(deserialize(payload) == value, "challenge canonical mismatch")
        self._validate_links(value)
        if self._connection.execute(
            "SELECT 1 FROM ch_artifacts WHERE fingerprint=?", (value.fingerprint,)
        ).fetchone():
            require(
                self.get(type(value), value.fingerprint) == value,
                "conflicting challenge payload",
            )
            return value.fingerprint
        require(
            self._connection.execute("SELECT count(*) FROM ch_artifacts").fetchone()[0]
            < self.challenge_bounds.artifacts,
            "stored challenge artifact bound",
        )
        self._connection.execute(
            "INSERT INTO ch_artifacts VALUES (?,?,?,?)",
            (value.fingerprint, type(value).__name__, "1.0", payload),
        )
        self._connection.execute(
            "INSERT INTO ch_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            record_index(value),
        )
        self._connection.executemany(
            "INSERT INTO ch_links VALUES (?,?)",
            tuple((value.fingerprint, i) for i in sorted(set(challenge_edges(value)))),
        )
        return value.fingerprint

    def _validate_links(self, value: Artifact) -> None:
        if type(value) not in CHALLENGE_TYPES:
            super()._validate_links(value)
            return
        key = value.fingerprint, bool(self._feature_only_depth)
        if self._validation_cache is not None and key in self._challenge_validated:
            return
        require(value.fingerprint not in self._challenge_active, "challenge reference cycle")
        self._challenge_active.add(value.fingerprint)
        try:
            from afre.challenger.validation import validate_challenge

            validate_challenge(self, value)
            if self._validation_cache is not None:
                self._challenge_validated.add(key)
        finally:
            self._challenge_active.remove(value.fingerprint)

    def audit(self) -> int:
        if not self._reading and not self._in_transaction:
            with self.read_snapshot():
                return self.audit()
        count = super().audit()
        with self.validation_cache():
            for (identity,) in self._connection.execute(
                "SELECT fingerprint FROM ch_artifacts ORDER BY fingerprint"
            ):
                self.get_any(identity)
                count += 1
        for table in ("ch_records", "ch_links"):
            require(
                self._connection.execute(
                    f"SELECT count(*) FROM {table} r LEFT JOIN ch_artifacts a "
                    "ON r.fingerprint=a.fingerprint WHERE a.fingerprint IS NULL"
                ).fetchone()[0]
                == 0,
                "orphan challenge projection",
            )
        return count

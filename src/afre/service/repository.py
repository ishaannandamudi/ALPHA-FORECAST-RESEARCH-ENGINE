"""Immutable publication store and before-cache truth/outcome protection."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, TypeVar, cast

from afre.challenger.repository import ChallengeRepository
from afre.ids import validate_fingerprint
from afre.schema import CONTRACTS, Artifact, ContractError, require
from afre.serialization import canonical_json, deserialize
from afre.service.audit import SnapshotAudit
from afre.service.bounds import ServiceBounds
from afre.service.queries import PublicationCatalog
from afre.service.registry_entries import RegistryEntry
from afre.service.snapshots import ForecastSnapshot
from afre.service.storage import METADATA, all_statements, links, record_index, service_schema

if TYPE_CHECKING:
    from afre.service.native import NativeSnapshotSource
    from afre.service.snapshots import SnapshotLineage

PERSISTED = (ForecastSnapshot, RegistryEntry, PublicationCatalog, SnapshotAudit)
A = TypeVar("A", bound=Artifact)
OUTCOMES = {
    "TargetVintage",
    "TargetBar",
    "TargetSourceBuild",
    "TargetEvaluation",
    "TestEvaluation",
    "PointEvaluation",
    "ProbabilisticEvaluation",
    "CalibratedEvaluation",
    "MixtureEvaluation",
    "FusionEvaluation",
    "CostEvaluation",
    "StabilityMetric",
    "FamilyAnalysis",
    "ResearchTrial",
    "SelectionResult",
    "EvaluationEvidence",
    "CommonMatchedEvidence",
    "ParticipantMetricResult",
    "ChallengerComparison",
    "HealthObservation",
    "CalibrationScoredPair",
    "CalibrationEvaluation",
    "ProbabilisticScoredPair",
    "EvaluationPair",
    "EventEvaluationPair",
    "EventGroupMetric",
    "EventConditionedEvaluation",
    "EventRankEvaluation",
    "RegimeEvaluationPair",
    "RegimeGroupMetric",
    "RegimeConditionedEvaluation",
    "RegimeRankEvaluation",
    "MixtureEvaluationPair",
    "MixtureRankEvaluation",
    "NonlinearEvaluationPair",
    "NonlinearEvaluation",
    "NonlinearRankEvaluation",
    "SequenceEvaluationPair",
    "SequenceEvaluation",
    "SequenceRankEvaluation",
    "UncertaintyEvaluationPair",
    "UncertaintyEvaluation",
    "FusionEvaluationPair",
    "TruthRow",
    "CrossSectionTruth",
    "CrossSectionEvaluation",
    "CandidateValidationPair",
    "CandidateValidationResult",
    "TrialObservation",
}


class ServiceRepository(ChallengeRepository):
    _snapshot_engine_version: ClassVar[str] = "0.25.0"

    def __init__(self, path: str | Path, bounds: ServiceBounds | None = None) -> None:
        self.service_bounds = bounds or ServiceBounds()
        self._service_active: set[str] = set()
        self._service_request_depth = 0
        self._service_sources: dict[str, NativeSnapshotSource] = {}
        self._service_graphs: dict[tuple[str, tuple[str, ...]], SnapshotLineage] = {}
        super().__init__(path)

    def _migrate(self) -> None:
        version = self._connection.execute("PRAGMA user_version").fetchone()[0]
        require(version in range(26), "unknown future service store version")
        if version == 25:
            return
        if version < 24:
            ChallengeRepository._migrate(self)
        with self.transaction():
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 25:
                return
            require(version == 24, "unexpected service migration version")
            ChallengeRepository._validate_layout(self)
            for sql in service_schema():
                self._connection.execute(sql)
            self._connection.executemany(
                "INSERT INTO metadata VALUES (?,?)",
                tuple(
                    (k, v)
                    for k, v in METADATA.items()
                    if k.startswith(
                        ("service_", "forecast_service_", "forecast_snapshot_", "registry_")
                    )
                ),
            )
            self._connection.execute("PRAGMA user_version=25")

    def _validate_layout(self) -> None:
        expected = {
            s.split()[3] if s.startswith("CREATE UNIQUE INDEX") else s.split()[2]: s
            for s in all_statements()
        }
        require(
            expected
            == dict(
                self._connection.execute(
                    "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
                )
            ),
            "service layout corruption",
        )
        require(
            dict(self._connection.execute("SELECT key,value FROM metadata")) == METADATA
            and self._connection.execute("PRAGMA user_version").fetchone()[0] == 25,
            "service metadata/version corruption",
        )

    def _snapshot_bound(self) -> None:
        pages = self._connection.execute("PRAGMA page_count").fetchone()[0]
        size = self._connection.execute("PRAGMA page_size").fetchone()[0]
        require(
            pages * size <= self.service_bounds.snapshot_bytes,
            "service frozen snapshot byte bound",
        )

    @contextmanager
    def read_snapshot(self) -> Iterator[None]:
        self._snapshot_bound()
        with super().read_snapshot():
            self._snapshot_bound()
            yield

    @contextmanager
    def request(self) -> Iterator[None]:
        self._service_request_depth += 1
        try:
            if self._validation_cache is not None:
                with self.feature_only():
                    yield
            elif self._reading or self._in_transaction:
                with self.validation_cache(), self.feature_only():
                    yield
            else:
                with self.read_snapshot(), self.validation_cache(), self.feature_only():
                    yield
        finally:
            self._service_request_depth -= 1
            if not self._service_request_depth:
                self._service_sources.clear()
                self._service_graphs.clear()

    def _service_guard(self, cls: type[Artifact], identity: str) -> None:
        if self._service_request_depth:
            require(
                cls.__name__ not in OUTCOMES
                and not identity.startswith("afre.target_vintage:"),
                "service target-free boundary excludes truth and later outcomes before cache",
            )

    def raw(self, identity: str) -> Artifact:
        validate_fingerprint(identity)
        domain = identity.split(":")[0].removeprefix("afre.")
        classes = tuple(c for c in CONTRACTS.values() if c.domain == domain)
        require(len(classes) == 1, "unresolved service native artifact type")
        return self.get(classes[0], identity)

    def exists(self, identity: str) -> bool:
        try:
            self.raw(identity)
        except KeyError:
            return False
        except ContractError as error:
            if str(error) == "unsupported artifact family":
                return False
            raise
        return True

    def get(self, cls: type[A], identity: str) -> A:
        self._service_guard(cls, identity)
        if cls not in PERSISTED:
            return super().get(cls, identity)
        validate_fingerprint(identity, cls.domain)
        row = self._connection.execute(
            "SELECT type_name,schema_version,CASE WHEN length(CAST(payload AS BLOB))<=? "
            "THEN payload ELSE NULL END FROM svc_artifacts WHERE fingerprint=?",
            (self.service_bounds.payload_bytes, identity),
        ).fetchone()
        if row is None:
            raise KeyError(identity)
        require(
            row[:2] == (cls.__name__, "1.0") and type(row[2]) is str,
            "service type/schema/payload bound corruption",
        )
        value = deserialize(row[2])
        require(type(value) is cls and value.fingerprint == identity, "service hash corruption")
        require(
            self._connection.execute(
                "SELECT * FROM svc_records WHERE fingerprint=?", (identity,)
            ).fetchone()
            == record_index(value),
            "service index corruption",
        )
        require(
            tuple(
                r[0]
                for r in self._connection.execute(
                    "SELECT reference_id FROM svc_links WHERE fingerprint=? ORDER BY "
                    "reference_id",
                    (identity,),
                )
            )
            == links(value),
            "service link corruption",
        )
        return cast(A, value)

    def resolve(self, cls: type[A], identity: str) -> A:
        self._service_guard(cls, identity)
        if self._service_request_depth and cls.__name__ == "ParameterCovariance":
            # A frozen TRAIN fitting certificate; reopening its matrix would violate
            # the forecast read boundary. Native prediction algebra still replays.
            value = self.get(cls, identity)
            policy = self.raw(getattr(value, "spec_id", "missing"))
            require(
                getattr(policy, "model_id", None) == getattr(value, "model_id", None),
                "uncertainty covariance model certificate corruption",
            )
            return value
        if cls not in PERSISTED:
            return super().resolve(cls, identity)
        value = self.get(cls, identity)
        with self.request():
            self._validate_links(value)
        return value

    def get_any(self, identity: str) -> Artifact:
        validate_fingerprint(identity)
        if self._service_request_depth:
            domain = identity.split(":")[0].removeprefix("afre.")
            for cls in CONTRACTS.values():
                if cls.domain == domain:
                    self._service_guard(cls, identity)
        if identity.startswith("afre.svc_"):
            value = self.raw(identity)
            self._validate_links(value)
            return value
        return super().get_any(identity)

    def put(self, value: Artifact) -> str:
        if type(value) not in PERSISTED:
            return super().put(value)
        require(self._in_transaction, "service publication requires writer transaction")
        payload = canonical_json(value)
        require(
            len(payload.encode()) <= self.service_bounds.payload_bytes,
            "service payload byte bound",
        )
        require(deserialize(payload) == value, "service canonical corruption")
        with self.request():
            self._validate_links(value)
        if self._connection.execute(
            "SELECT 1 FROM svc_artifacts WHERE fingerprint=?", (value.fingerprint,)
        ).fetchone():
            require(
                self.get(type(value), value.fingerprint) == value,
                "conflicting immutable service payload",
            )
            return value.fingerprint
        require(
            self._connection.execute("SELECT count(*) FROM svc_artifacts").fetchone()[0]
            < self.service_bounds.artifacts,
            "stored service artifact bound",
        )
        self._connection.execute(
            "INSERT INTO svc_artifacts VALUES (?,?,?,?)",
            (value.fingerprint, type(value).__name__, "1.0", payload),
        )
        self._connection.execute(
            "INSERT INTO svc_records VALUES (?,?,?,?,?,?,?,?,?,?)", record_index(value)
        )
        self._connection.executemany(
            "INSERT INTO svc_links VALUES (?,?)",
            tuple((value.fingerprint, i) for i in links(value)),
        )
        return value.fingerprint

    def _validate_links(self, value: Artifact) -> None:
        if type(value) not in PERSISTED:
            super()._validate_links(value)
            return
        require(value.fingerprint not in self._service_active, "service reference cycle")
        self._service_active.add(value.fingerprint)
        try:
            from afre.service.validation import validate_service

            validate_service(self, value)
        finally:
            self._service_active.remove(value.fingerprint)

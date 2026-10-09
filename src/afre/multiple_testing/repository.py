"""Strict immutable additive SQLite20 registry with inherited causal response guards."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import ClassVar, TypeVar, cast

from afre.costs.repository import CostResearchRepository
from afre.ids import validate_fingerprint
from afre.multiple_testing.diagnostics import (
    DeflatedPerformanceDiagnostic,
    ResearchOverfittingDiagnostic,
)
from afre.multiple_testing.effects import EffectSizeResult
from afre.multiple_testing.evaluations import AdjustedHypothesisResult, FamilyAnalysis
from afre.multiple_testing.families import FamilyAnalysisSpec, HypothesisFamily
from afre.multiple_testing.hypotheses import HypothesisDefinition, TestAssumptions
from afre.multiple_testing.lineage import MultipleTestingAudit, testing_edges
from afre.multiple_testing.pvalues import PValueResult
from afre.multiple_testing.registry import TrialRegistrySnapshot
from afre.multiple_testing.schema import MultipleTestingBounds
from afre.multiple_testing.selection_bias import SelectionBiasDiagnostic, SelectionEvent
from afre.multiple_testing.storage import (
    METADATA,
    all_statements,
    multiple_testing_schema,
    record_index,
)
from afre.multiple_testing.test_reuse import TestReuseDiagnostic, TestReusePolicy
from afre.multiple_testing.trials import ResearchTrial, TrialSpecification
from afre.schema import Artifact, require
from afre.serialization import canonical_json, deserialize

TESTING_TYPES: tuple[type[Artifact], ...] = (
    TestAssumptions,
    HypothesisDefinition,
    TrialSpecification,
    HypothesisFamily,
    ResearchTrial,
    PValueResult,
    EffectSizeResult,
    FamilyAnalysisSpec,
    AdjustedHypothesisResult,
    FamilyAnalysis,
    TrialRegistrySnapshot,
    TestReusePolicy,
    TestReuseDiagnostic,
    SelectionEvent,
    SelectionBiasDiagnostic,
    ResearchOverfittingDiagnostic,
    DeflatedPerformanceDiagnostic,
    MultipleTestingAudit,
    MultipleTestingBounds,
)
PLANNING_TYPES = (
    TestAssumptions,
    HypothesisDefinition,
    TrialSpecification,
    HypothesisFamily,
    TestReusePolicy,
    MultipleTestingBounds,
)
A = TypeVar("A", bound=Artifact)


class MultipleTestingRepository(CostResearchRepository):
    _snapshot_engine_version: ClassVar[str] = "0.20.0"

    def __init__(self, path: str | Path, bounds: MultipleTestingBounds | None = None) -> None:
        self.multiple_testing_bounds = bounds or MultipleTestingBounds()
        self._multiple_testing_validated: set[str] = set()
        self._adjustment_replays: dict[
            str, tuple[tuple[AdjustedHypothesisResult, ...], FamilyAnalysis]
        ] = {}
        self._frozen_registry_publications: set[str] = set()
        super().__init__(path)

    @contextmanager
    def validation_cache(self) -> Iterator[None]:
        with super().validation_cache():
            try:
                yield
            finally:
                self._multiple_testing_validated.clear()
                self._adjustment_replays.clear()

    def _migrate(self) -> None:
        version = self._connection.execute("PRAGMA user_version").fetchone()[0]
        require(version in range(21), "unknown future multiple_testing store version")
        if version == 20:
            return
        if version < 19:
            CostResearchRepository._migrate(self)
        with self.transaction():
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 20:
                return
            require(version == 19, "unexpected multiple_testing migration version")
            CostResearchRepository._validate_layout(self)
            for statement in multiple_testing_schema():
                self._connection.execute(statement)
            self._connection.executemany(
                "INSERT INTO metadata VALUES (?,?)",
                (
                    ("multiple_testing_store_schema_version", "1.19"),
                    ("multiple_testing_schema", "1.0"),
                    ("multiple_testing_engine_version", "0.20.0"),
                ),
            )
            self._connection.execute("PRAGMA user_version=20")

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
            "multiple_testing schema/index/trigger corruption",
        )
        require(
            dict(self._connection.execute("SELECT key,value FROM metadata")) == METADATA,
            "multiple_testing metadata corruption",
        )
        require(
            self._connection.execute("PRAGMA user_version").fetchone()[0] == 20,
            "multiple_testing integer version corruption",
        )

    def _multiple_testing_check_bounds(self, value: Artifact) -> None:
        from afre.multiple_testing.bounds import check_bounds

        check_bounds(self.multiple_testing_bounds, value)

    def _guard(self, cls: type[Artifact]) -> None:
        super()._guard(cls)
        require(
            not self._feature_only_depth or cls not in TESTING_TYPES or cls in PLANNING_TYPES,
            "planned registration cannot read later truth/results",
        )

    def resolve(self, cls: type[A], identity: str) -> A:
        self._guard(cls)
        if cls not in TESTING_TYPES:
            return super().resolve(cls, identity)
        if self._validation_cache is None:
            if not self._reading and not self._in_transaction:
                with self.read_snapshot(), self.validation_cache():
                    return self.resolve(cls, identity)
            with self.validation_cache():
                return self.resolve(cls, identity)
        value = super().resolve(cls, identity)
        self._validate_links(value)
        return value

    def put(self, value: Artifact) -> str:
        if type(value) not in TESTING_TYPES:
            return super().put(value)
        require(self._in_transaction, "multiple_testing write requires transaction")
        self._multiple_testing_check_bounds(value)
        identity, payload = value.fingerprint, canonical_json(value)
        require(deserialize(payload) == value, "multiple_testing canonical mismatch")
        if self._connection.execute(
            "SELECT 1 FROM mt_artifacts WHERE fingerprint=?", (identity,)
        ).fetchone():
            require(
                self.get(type(value), identity) == value,
                "conflicting multiple_testing payload",
            )
            self._validate_links(value)
            return identity
        if isinstance(value, ResearchTrial):
            require(
                self._connection.execute(
                    "SELECT 1 FROM mt_records WHERE kind='ResearchTrial' AND plan_id=?",
                    (value.plan_id,),
                ).fetchone()
                is None,
                (
                    "reevaluation requires a distinct declared attempt; cannot collapse "
                    "completions"
                ),
            )
        limit = (
            self.multiple_testing_bounds.registry_snapshots
            if isinstance(value, TrialRegistrySnapshot)
            else self.multiple_testing_bounds.selection_events
            if isinstance(value, SelectionEvent)
            else self.multiple_testing_bounds.artifacts
        )
        require(
            self._connection.execute(
                "SELECT count(*) FROM mt_artifacts WHERE type_name=?", (type(value).__name__,)
            ).fetchone()[0]
            < limit,
            "stored multiple_testing artifact bound",
        )
        self._validate_links(value)
        self._connection.execute(
            "INSERT INTO mt_artifacts VALUES (?,?,?,?)",
            (identity, type(value).__name__, "1.0", payload),
        )
        self._connection.execute(
            "INSERT INTO mt_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            record_index(value),
        )

        self._connection.executemany(
            "INSERT INTO mt_links VALUES (?,?)",
            tuple((identity, i) for i in sorted(set(testing_edges(value)))),
        )
        if isinstance(value, ResearchTrial):
            self._connection.executemany(
                "INSERT INTO mt_test_uses VALUES (?,?)",
                tuple((identity, i) for i in value.test_seal_ids),
            )
        return identity

    def get(self, cls: type[A], identity: str) -> A:
        self._guard(cls)
        if cls not in TESTING_TYPES:
            return super().get(cls, identity)
        validate_fingerprint(identity, cls.domain)
        row = self._connection.execute(
            "SELECT type_name,schema_version,CASE WHEN length(CAST(payload AS BLOB)) <= ? "
            "THEN payload ELSE NULL END FROM mt_artifacts WHERE fingerprint=?",
            (self.multiple_testing_bounds.serialized_bytes, identity),
        ).fetchone()
        if row is None:
            raise KeyError(identity)
        require(row[:2] == (cls.__name__, "1.0"), "multiple_testing family/schema corruption")
        require(type(row[2]) is str, "raw multiple testing payload bound/type")
        value = deserialize(row[2])
        require(
            type(value) is cls and value.fingerprint == identity,
            "multiple_testing hash corruption",
        )
        self._multiple_testing_check_bounds(value)
        require(
            self._connection.execute(
                "SELECT * FROM mt_records WHERE fingerprint=?", (identity,)
            ).fetchone()
            == record_index(value),
            "multiple_testing relational index corruption",
        )

        require(
            tuple(
                r[0]
                for r in self._connection.execute(
                    (
                        "SELECT reference_id FROM mt_links WHERE fingerprint=? "
                        "ORDER BY reference_id"
                    ),
                    (identity,),
                )
            )
            == tuple(sorted(set(testing_edges(value)))),
            "multiple_testing link index corruption",
        )
        actual_uses = tuple(
            r[0]
            for r in self._connection.execute(
                "SELECT seal_id FROM mt_test_uses WHERE fingerprint=? ORDER BY seal_id",
                (identity,),
            )
        )
        require(
            actual_uses == (value.test_seal_ids if isinstance(value, ResearchTrial) else ()),
            "multiple testing TEST projection corruption",
        )
        return cast(A, value)

    def get_any(self, identity: str) -> Artifact:
        validate_fingerprint(identity)
        if self._validation_cache is not None and identity in self._validation_cache:
            self._guard(type(self._validation_cache[identity]))
        if not identity.startswith("afre.mt_"):
            return super().get_any(identity)
        row = self._connection.execute(
            "SELECT type_name FROM mt_artifacts WHERE fingerprint=?", (identity,)
        ).fetchone()
        classes = {c.__name__: c for c in TESTING_TYPES}
        require(row is not None and row[0] in classes, "unresolved multiple_testing reference")
        assert row is not None
        return self.resolve(classes[row[0]], identity)

    def _validate_links(self, value: Artifact) -> None:
        if type(value) not in TESTING_TYPES:
            super()._validate_links(value)
            return
        if value.fingerprint not in self._multiple_testing_validated:
            from afre.multiple_testing.validation import validate_testing

            validate_testing(self, value)
            self._multiple_testing_validated.add(value.fingerprint)

    def audit(self) -> int:
        if not self._reading and not self._in_transaction:
            with self.read_snapshot():
                return self.audit()
        count = super().audit()
        with self.validation_cache():
            for identity, name in self._connection.execute(
                "SELECT fingerprint,type_name FROM mt_artifacts"
            ):
                require(
                    name in {c.__name__ for c in TESTING_TYPES},
                    "unknown multiple_testing family",
                )
                self._validate_links(self.get_any(identity))
                count += 1
            for table in ("mt_links", "mt_records", "mt_test_uses"):
                require(
                    self._connection.execute(
                        f"SELECT count(*) FROM {table} r LEFT JOIN mt_artifacts a "
                        "ON r.fingerprint=a.fingerprint WHERE a.fingerprint IS NULL"
                    ).fetchone()[0]
                    == 0,
                    "orphan multiple_testing projection",
                )
        return count

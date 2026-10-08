"""Strict immutable additive SQLite19 family with inherited causal response guards."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import ClassVar, TypeVar, cast

from afre.costs.artifacts import (
    BreakEvenCostDiagnostic,
    CostAwareComparison,
    CostAwareEvaluation,
    CostAwareSampleEvaluation,
    CostCohortEvaluation,
    CostComponentEstimate,
    CostResearchAudit,
    CostSensitivityCurve,
    ResearchExposureChange,
    ResearchExposurePath,
    TotalCostEstimate,
)
from afre.costs.cost_inputs import CostInputReference
from afre.costs.definitions import (
    CostComponentSpec,
    CostScenario,
    CostSensitivitySpec,
    ResearchExposureRule,
)
from afre.costs.schema import CostResearchBounds
from afre.costs.storage import METADATA, all_statements, costs_index, costs_schema
from afre.ids import validate_fingerprint
from afre.invariance.repository import InvarianceRepository
from afre.schema import Artifact, require
from afre.serialization import canonical_json, deserialize

COST_TYPES: tuple[type[Artifact], ...] = (
    CostInputReference,
    ResearchExposureRule,
    CostComponentSpec,
    CostScenario,
    CostSensitivitySpec,
    ResearchExposureChange,
    ResearchExposurePath,
    CostComponentEstimate,
    TotalCostEstimate,
    CostAwareSampleEvaluation,
    CostAwareEvaluation,
    BreakEvenCostDiagnostic,
    CostSensitivityCurve,
    CostAwareComparison,
    CostCohortEvaluation,
    CostResearchAudit,
    CostResearchBounds,
)
A = TypeVar("A", bound=Artifact)


class CostResearchRepository(InvarianceRepository):
    _snapshot_engine_version: ClassVar[str] = "0.19.0"

    def __init__(self, path: str | Path, bounds: CostResearchBounds | None = None) -> None:
        self.cost_research_bounds = bounds or CostResearchBounds()
        self._cost_research_validated: set[str] = set()
        super().__init__(path)

    @contextmanager
    def validation_cache(self) -> Iterator[None]:
        with super().validation_cache():
            try:
                yield
            finally:
                self._cost_research_validated.clear()

    def _migrate(self) -> None:
        version = self._connection.execute("PRAGMA user_version").fetchone()[0]
        require(version in range(20), "unknown future cost_research store version")
        if version == 19:
            return
        if version < 18:
            InvarianceRepository._migrate(self)
        with self.transaction():
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 19:
                return
            require(version == 18, "unexpected cost_research migration version")
            InvarianceRepository._validate_layout(self)
            for statement in costs_schema():
                self._connection.execute(statement)
            self._connection.executemany(
                "INSERT INTO metadata VALUES (?,?)",
                (
                    ("cost_research_store_schema_version", "1.18"),
                    ("cost_research_schema", "1.0"),
                    ("cost_research_engine_version", "0.19.0"),
                ),
            )
            self._connection.execute("PRAGMA user_version=19")

    def _validate_layout(self) -> None:
        require(
            {s.split()[2]: s for s in all_statements()}
            == dict(
                self._connection.execute(
                    "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
                )
            ),
            "cost_research schema/index/trigger corruption",
        )
        require(
            dict(self._connection.execute("SELECT key,value FROM metadata")) == METADATA,
            "cost_research metadata corruption",
        )
        require(
            self._connection.execute("PRAGMA user_version").fetchone()[0] == 19,
            "cost_research integer version corruption",
        )

    def _cost_research_check_bounds(self, value: Artifact) -> None:
        b = self.cost_research_bounds
        require(len(canonical_json(value).encode()) <= b.serialized_bytes, "cost payload bound")
        if isinstance(value, CostScenario):
            require(
                len(value.components) <= b.components
                and len(value.sample_ids) <= b.samples
                and len(value.bindings) <= b.samples * b.components,
                # Uncertainty remains separate metadata, with a bounded supplied set.
                "cost scenario input bounds",
            )
        if isinstance(value, (ResearchExposurePath, CostAwareEvaluation)):
            values = (
                value.change_ids
                if isinstance(value, ResearchExposurePath)
                else value.sample_evaluation_ids
            )
            require(len(values) <= b.samples, "cost sample/path bounds")
        if isinstance(value, TotalCostEstimate):
            require(len(value.component_ids) <= b.components, "cost component bounds")
        if isinstance(value, CostSensitivitySpec):
            require(
                len(value.rates)
                * max(1, len(value.participation_rates))
                * len(value.turnover_multipliers)
                <= b.grid_points
                and len(value.participation_rates) <= b.participation_rates,
                "cost sensitivity input bounds",
            )
        if isinstance(value, CostSensitivityCurve):
            require(len(value.points) <= b.grid_points, "cost curve bounds")
        if isinstance(value, CostCohortEvaluation):
            require(len(value.membership_ids) <= b.samples, "cost cohort bounds")
        if isinstance(value, CostAwareComparison):
            require(len(value.sample_ids) <= b.samples, "cost matched comparison bounds")
        if isinstance(value, CostResearchAudit):
            require(len(value.node_ids) <= b.audit_nodes, "cost audit node bounds")

    def _guard(self, cls: type[Artifact]) -> None:
        super()._guard(cls)
        require(
            not self._feature_only_depth
            or cls
            not in (
                CostAwareSampleEvaluation,
                CostAwareEvaluation,
                BreakEvenCostDiagnostic,
                CostSensitivityCurve,
                CostAwareComparison,
                CostCohortEvaluation,
                CostResearchAudit,
            ),
            "cost metadata cannot read later truth/evaluation results",
        )

    def resolve(self, cls: type[A], identity: str) -> A:
        self._guard(cls)
        if cls not in COST_TYPES:
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
        if type(value) not in COST_TYPES:
            return super().put(value)
        require(self._in_transaction, "cost_research write requires transaction")
        self._cost_research_check_bounds(value)
        identity, payload = value.fingerprint, canonical_json(value)
        require(deserialize(payload) == value, "cost_research canonical mismatch")
        if self._connection.execute(
            "SELECT 1 FROM cost_artifacts WHERE fingerprint=?", (identity,)
        ).fetchone():
            require(
                self.get(type(value), identity) == value,
                "conflicting cost_research payload",
            )
            return identity
        require(
            self._connection.execute(
                "SELECT count(*) FROM cost_artifacts WHERE type_name=?", (type(value).__name__,)
            ).fetchone()[0]
            < self.cost_research_bounds.artifacts,
            "stored cost_research artifact bound",
        )
        self._validate_links(value)
        self._connection.execute(
            "INSERT INTO cost_artifacts VALUES (?,?,?,?)",
            (identity, type(value).__name__, "1.0", payload),
        )
        self._connection.execute(
            "INSERT INTO cost_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            costs_index(value),
        )
        from afre.costs.lineage import cost_edges

        self._connection.executemany(
            "INSERT INTO cost_links VALUES (?,?)",
            tuple((identity, i) for i in sorted(set(cost_edges(value)))),
        )
        return identity

    def get(self, cls: type[A], identity: str) -> A:
        self._guard(cls)
        if cls not in COST_TYPES:
            return super().get(cls, identity)
        validate_fingerprint(identity, cls.domain)
        row = self._connection.execute(
            "SELECT type_name,schema_version,CASE WHEN length(CAST(payload AS BLOB)) <= ? "
            "THEN payload ELSE NULL END FROM cost_artifacts WHERE fingerprint=?",
            (self.cost_research_bounds.serialized_bytes, identity),
        ).fetchone()
        if row is None:
            raise KeyError(identity)
        require(row[:2] == (cls.__name__, "1.0"), "cost_research family/schema corruption")
        require(type(row[2]) is str, "raw cost payload bound/type")
        value = deserialize(row[2])
        require(
            type(value) is cls and value.fingerprint == identity,
            "cost_research hash corruption",
        )
        self._cost_research_check_bounds(value)
        require(
            self._connection.execute(
                "SELECT * FROM cost_records WHERE fingerprint=?", (identity,)
            ).fetchone()
            == costs_index(value),
            "cost_research relational index corruption",
        )
        from afre.costs.lineage import cost_edges

        require(
            tuple(
                r[0]
                for r in self._connection.execute(
                    (
                        "SELECT reference_id FROM cost_links WHERE fingerprint=? "
                        "ORDER BY reference_id"
                    ),
                    (identity,),
                )
            )
            == tuple(sorted(set(cost_edges(value)))),
            "cost_research link index corruption",
        )
        return cast(A, value)

    def get_any(self, identity: str) -> Artifact:
        if not identity.startswith("afre.cost_"):
            return super().get_any(identity)
        row = self._connection.execute(
            "SELECT type_name FROM cost_artifacts WHERE fingerprint=?", (identity,)
        ).fetchone()
        classes = {c.__name__: c for c in COST_TYPES}
        require(row is not None and row[0] in classes, "unresolved cost_research reference")
        assert row is not None
        return self.resolve(classes[row[0]], identity)

    def _validate_links(self, value: Artifact) -> None:
        if type(value) not in COST_TYPES:
            super()._validate_links(value)
            return
        if value.fingerprint not in self._cost_research_validated:
            from afre.costs.validation import validate_costs

            validate_costs(self, value)
            self._cost_research_validated.add(value.fingerprint)

    def audit(self) -> int:
        if not self._reading and not self._in_transaction:
            with self.read_snapshot():
                return self.audit()
        count = super().audit()
        with self.validation_cache():
            for identity, name in self._connection.execute(
                "SELECT fingerprint,type_name FROM cost_artifacts"
            ):
                require(
                    name in {c.__name__ for c in COST_TYPES},
                    "unknown cost_research family",
                )
                self._validate_links(self.get_any(identity))
                count += 1
            for table in ("cost_links", "cost_records"):
                require(
                    self._connection.execute(
                        f"SELECT count(*) FROM {table} r LEFT JOIN cost_artifacts a "
                        "ON r.fingerprint=a.fingerprint WHERE a.fingerprint IS NULL"
                    ).fetchone()[0]
                    == 0,
                    "orphan cost_research projection",
                )
        return count

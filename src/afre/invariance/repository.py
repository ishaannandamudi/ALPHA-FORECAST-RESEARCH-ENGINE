"""Strict immutable additive SQLite18 family with inherited causal response guards."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import ClassVar, TypeVar, cast

from afre.ids import validate_fingerprint
from afre.invariance.artifacts import (
    EnvironmentMembership,
    EnvironmentMetric,
    FeatureShiftDiagnostic,
    ForecastDegradation,
    ModelStabilityDiagnostic,
    NeutralEnvironmentLabel,
    PredictionStabilityDiagnostic,
    StabilityAudit,
    StabilityComparison,
    StabilityTrend,
)
from afre.invariance.definitions import (
    EnvironmentDefinition,
    EnvironmentSet,
    StabilityAnalysisSpec,
    StabilityTimeWindow,
)
from afre.invariance.schema import InvarianceBounds
from afre.invariance.storage import (
    METADATA,
    all_statements,
    invariance_index,
    invariance_schema,
)
from afre.orthogonalization.repository import OrthogonalizationRepository
from afre.schema import Artifact, require
from afre.serialization import canonical_json, deserialize

INVARIANCE_TYPES: tuple[type[Artifact], ...] = (
    EnvironmentDefinition,
    EnvironmentSet,
    StabilityAnalysisSpec,
    StabilityTimeWindow,
    EnvironmentMembership,
    EnvironmentMetric,
    FeatureShiftDiagnostic,
    ForecastDegradation,
    ModelStabilityDiagnostic,
    NeutralEnvironmentLabel,
    PredictionStabilityDiagnostic,
    StabilityAudit,
    StabilityComparison,
    StabilityTrend,
    InvarianceBounds,
)
A = TypeVar("A", bound=Artifact)


class InvarianceRepository(OrthogonalizationRepository):
    _snapshot_engine_version: ClassVar[str] = "0.18.0"

    def __init__(self, path: str | Path, bounds: InvarianceBounds | None = None) -> None:
        self.invariance_bounds = bounds or InvarianceBounds()
        self._invariance_validated: set[str] = set()
        super().__init__(path)

    @contextmanager
    def validation_cache(self) -> Iterator[None]:
        with super().validation_cache():
            try:
                yield
            finally:
                self._invariance_validated.clear()

    def _migrate(self) -> None:
        version = self._connection.execute("PRAGMA user_version").fetchone()[0]
        require(version in range(19), "unknown future invariance store version")
        if version == 18:
            return
        if version < 17:
            OrthogonalizationRepository._migrate(self)
        with self.transaction():
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 18:
                return
            require(version == 17, "unexpected invariance migration version")
            OrthogonalizationRepository._validate_layout(self)
            for statement in invariance_schema():
                self._connection.execute(statement)
            self._connection.executemany(
                "INSERT INTO metadata VALUES (?,?)",
                (
                    ("invariance_store_schema_version", "1.17"),
                    ("invariance_schema", "1.0"),
                    ("invariance_engine_version", "0.18.0"),
                ),
            )
            self._connection.execute("PRAGMA user_version=18")

    def _validate_layout(self) -> None:
        require(
            {s.split()[2]: s for s in all_statements()}
            == dict(
                self._connection.execute(
                    "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
                )
            ),
            "invariance schema/index/trigger corruption",
        )
        require(
            dict(self._connection.execute("SELECT key,value FROM metadata")) == METADATA,
            "invariance metadata corruption",
        )
        require(
            self._connection.execute("PRAGMA user_version").fetchone()[0] == 18,
            "invariance integer version corruption",
        )

    def _invariance_check_bounds(self, value: Artifact) -> None:
        bounds = self.invariance_bounds
        require(
            len(canonical_json(value).encode()) <= bounds.serialized_bytes,
            "invariance payload bound",
        )
        if isinstance(value, EnvironmentSet):
            require(
                len(value.definitions) <= bounds.environments
                and sum(bool(d.component_ids) for d in value.definitions) <= bounds.compounds
                and sum(d.window is not None for d in value.definitions) <= bounds.windows,
                "invariance environment/window/compound bound",
            )
        if isinstance(value, StabilityAnalysisSpec):
            require(
                len(value.sample_ids) <= bounds.samples
                and len(value.forecast_ids) <= bounds.forecasts
                and len(value.uncertainty_ids) <= bounds.forecasts
                and len(value.metrics) <= bounds.metrics
                and len(value.feature_reference_ids) <= bounds.features,
                "invariance analysis input bounds",
            )
        if isinstance(
            value, (EnvironmentMetric, FeatureShiftDiagnostic, PredictionStabilityDiagnostic)
        ):
            require(len(value.membership_ids) <= bounds.shift_cells, "invariance grid bound")
        if isinstance(value, FeatureShiftDiagnostic):
            require(
                len(value.observation_ids) <= bounds.samples,
                "invariance shift observation bound",
            )
        if isinstance(value, ModelStabilityDiagnostic):
            require(
                len(value.assignments) <= bounds.environments
                and sum(len(r.values) for r in value.records) <= bounds.shift_cells,
                "invariance parameter bound",
            )
        if isinstance(value, StabilityTrend):
            require(len(value.metric_ids) <= bounds.windows, "invariance trend window bound")
        if isinstance(value, StabilityAudit):
            require(len(value.node_ids) <= bounds.audit_nodes, "invariance audit node bound")

    def _guard(self, cls: type[Artifact]) -> None:
        super()._guard(cls)
        require(
            not self._feature_only_depth
            or cls
            not in (
                EnvironmentMetric,
                StabilityComparison,
                ForecastDegradation,
                ModelStabilityDiagnostic,
                PredictionStabilityDiagnostic,
                StabilityTrend,
                StabilityAudit,
            ),
            "forecast metadata cannot read later invariance research/target results",
        )

    def resolve(self, cls: type[A], identity: str) -> A:
        self._guard(cls)
        if cls not in INVARIANCE_TYPES:
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
        if type(value) not in INVARIANCE_TYPES:
            return super().put(value)
        require(self._in_transaction, "invariance write requires transaction")
        self._invariance_check_bounds(value)
        identity, payload = value.fingerprint, canonical_json(value)
        require(deserialize(payload) == value, "invariance canonical mismatch")
        if self._connection.execute(
            "SELECT 1 FROM inv_artifacts WHERE fingerprint=?", (identity,)
        ).fetchone():
            require(
                self.get(type(value), identity) == value,
                "conflicting invariance payload",
            )
            return identity
        require(
            self._connection.execute(
                "SELECT count(*) FROM inv_artifacts WHERE type_name=?", (type(value).__name__,)
            ).fetchone()[0]
            < self.invariance_bounds.artifacts,
            "stored invariance artifact bound",
        )
        self._validate_links(value)
        self._connection.execute(
            "INSERT INTO inv_artifacts VALUES (?,?,?,?)",
            (identity, type(value).__name__, "1.0", payload),
        )
        self._connection.execute(
            "INSERT INTO inv_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            invariance_index(value),
        )
        from afre.invariance.lineage import invariance_edges

        self._connection.executemany(
            "INSERT INTO inv_links VALUES (?,?)",
            tuple((identity, i) for i in sorted(set(invariance_edges(value)))),
        )
        return identity

    def get(self, cls: type[A], identity: str) -> A:
        self._guard(cls)
        if cls not in INVARIANCE_TYPES:
            return super().get(cls, identity)
        validate_fingerprint(identity, cls.domain)
        row = self._connection.execute(
            "SELECT type_name,schema_version,payload FROM inv_artifacts WHERE fingerprint=?",
            (identity,),
        ).fetchone()
        if row is None:
            raise KeyError(identity)
        require(row[:2] == (cls.__name__, "1.0"), "invariance family/schema corruption")
        value = deserialize(row[2])
        require(
            type(value) is cls and value.fingerprint == identity,
            "invariance hash corruption",
        )
        self._invariance_check_bounds(value)
        require(
            self._connection.execute(
                "SELECT * FROM inv_records WHERE fingerprint=?", (identity,)
            ).fetchone()
            == invariance_index(value),
            "invariance relational index corruption",
        )
        from afre.invariance.lineage import invariance_edges

        require(
            tuple(
                r[0]
                for r in self._connection.execute(
                    (
                        "SELECT reference_id FROM inv_links WHERE fingerprint=? "
                        "ORDER BY reference_id"
                    ),
                    (identity,),
                )
            )
            == tuple(sorted(set(invariance_edges(value)))),
            "invariance link index corruption",
        )
        return cast(A, value)

    def get_any(self, identity: str) -> Artifact:
        if not identity.startswith("afre.inv_"):
            return super().get_any(identity)
        row = self._connection.execute(
            "SELECT type_name FROM inv_artifacts WHERE fingerprint=?", (identity,)
        ).fetchone()
        classes = {c.__name__: c for c in INVARIANCE_TYPES}
        require(row is not None and row[0] in classes, "unresolved invariance reference")
        assert row is not None
        return self.resolve(classes[row[0]], identity)

    def _validate_links(self, value: Artifact) -> None:
        if type(value) not in INVARIANCE_TYPES:
            super()._validate_links(value)
            return
        if value.fingerprint not in self._invariance_validated:
            from afre.invariance.validation import validate_invariance

            validate_invariance(self, value)
            self._invariance_validated.add(value.fingerprint)

    def audit(self) -> int:
        if not self._reading and not self._in_transaction:
            with self.read_snapshot():
                return self.audit()
        count = super().audit()
        with self.validation_cache():
            for identity, name in self._connection.execute(
                "SELECT fingerprint,type_name FROM inv_artifacts"
            ):
                require(
                    name in {c.__name__ for c in INVARIANCE_TYPES},
                    "unknown invariance family",
                )
                self._validate_links(self.get_any(identity))
                count += 1
            for table in ("inv_links", "inv_records"):
                require(
                    self._connection.execute(
                        f"SELECT count(*) FROM {table} r LEFT JOIN inv_artifacts a "
                        "ON r.fingerprint=a.fingerprint WHERE a.fingerprint IS NULL"
                    ).fetchone()[0]
                    == 0,
                    "orphan invariance projection",
                )
        return count

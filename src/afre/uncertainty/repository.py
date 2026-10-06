"""Strict immutable SQLite 16 repository; earlier repository interfaces are inherited."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import ClassVar, TypeVar, cast

from afre.ids import validate_fingerprint
from afre.schema import Artifact, require
from afre.sequence.repository import SequenceRepository
from afre.serialization import canonical_json, deserialize
from afre.uncertainty.artifacts import (
    ForecastUncertaintyDecomposition,
    ParameterCovariance,
    UncertaintyAudit,
    UncertaintyComponent,
    UncertaintyInterval,
)
from afre.uncertainty.definitions import (
    ParameterUncertaintySpec,
    UncertaintyRequest,
    UncertaintySpec,
)
from afre.uncertainty.evaluation_artifacts import (
    UncertaintyComparison,
    UncertaintyDrift,
    UncertaintyEvaluation,
    UncertaintyEvaluationPair,
    UncertaintyEvaluationSpec,
)
from afre.uncertainty.schema import UncertaintyBounds
from afre.uncertainty.storage import (
    METADATA,
    all_statements,
    uncertainty_index,
    uncertainty_schema,
)

UNCERTAINTY_TYPES: tuple[type[Artifact], ...] = (
    ForecastUncertaintyDecomposition,
    ParameterCovariance,
    UncertaintyAudit,
    UncertaintyComponent,
    UncertaintyInterval,
    ParameterUncertaintySpec,
    UncertaintyRequest,
    UncertaintySpec,
    UncertaintyComparison,
    UncertaintyDrift,
    UncertaintyEvaluation,
    UncertaintyEvaluationPair,
    UncertaintyEvaluationSpec,
    UncertaintyBounds,
)
A = TypeVar("A", bound=Artifact)


class UncertaintyRepository(SequenceRepository):
    _snapshot_engine_version: ClassVar[str] = "0.16.0"

    def __init__(self, path: str | Path, bounds: UncertaintyBounds | None = None) -> None:
        self.uncertainty_bounds = bounds or UncertaintyBounds()
        self._uncertainty_validated: set[str] = set()
        super().__init__(path)

    @contextmanager
    def validation_cache(self) -> Iterator[None]:
        with super().validation_cache():
            try:
                yield
            finally:
                self._uncertainty_validated.clear()

    def _migrate(self) -> None:
        version = self._connection.execute("PRAGMA user_version").fetchone()[0]
        require(version in range(17), "unknown future uncertainty store version")
        if version == 16:
            return
        if version < 15:
            SequenceRepository._migrate(self)
        with self.transaction():
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 16:
                return
            require(version == 15, "unexpected uncertainty migration version")
            SequenceRepository._validate_layout(self)
            for statement in uncertainty_schema():
                self._connection.execute(statement)
            self._connection.executemany(
                "INSERT INTO metadata VALUES (?,?)",
                (
                    ("uncertainty_store_schema_version", "1.15"),
                    ("uncertainty_schema", "1.0"),
                    ("uncertainty_engine_version", "0.16.0"),
                ),
            )
            self._connection.execute("PRAGMA user_version=16")

    def _validate_layout(self) -> None:
        require(
            {s.split()[2]: s for s in all_statements()}
            == dict(
                self._connection.execute(
                    "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
                )
            ),
            "uncertainty schema/index/trigger corruption",
        )
        require(
            dict(self._connection.execute("SELECT key,value FROM metadata")) == METADATA,
            "uncertainty metadata corruption",
        )
        require(
            self._connection.execute("PRAGMA user_version").fetchone()[0] == 16,
            "uncertainty integer version corruption",
        )

    def _uncertainty_check_bounds(self, value: Artifact) -> None:
        b = self.uncertainty_bounds
        require(
            len(canonical_json(value).encode()) <= b.serialized_bytes,
            "uncertainty payload bound",
        )
        if isinstance(value, (UncertaintySpec, ForecastUncertaintyDecomposition)):
            count = (
                len(value.requests)
                if isinstance(value, UncertaintySpec)
                else len(value.components)
            )
            require(count <= b.components, "uncertainty component bound")
        if isinstance(value, UncertaintySpec):
            require(
                len(value.alternative_forecast_ids) <= b.experts, "alternative source bound"
            )
        if isinstance(value, ParameterCovariance):
            require(
                len(value.covariance) <= b.dimensions
                and len(value.train_sample_ids) <= b.samples,
                "covariance dimensions/TRAIN sample bound",
            )
        if isinstance(value, UncertaintyEvaluation):
            require(
                len(value.pairs) <= b.samples
                and len(value.buckets) <= b.buckets
                and len(value.cohorts) <= b.cohorts,
                "uncertainty evaluation resource bound",
            )
        if isinstance(value, UncertaintyDrift):
            require(len(value.evaluation_ids) <= b.drift_windows, "uncertainty drift bound")

    def _guard(self, cls: type[Artifact]) -> None:
        from afre.nonlinear.artifacts import InteractionMatrix, InteractionTrainingRow
        from afre.sequence.artifacts import SequenceDataset, SequenceTrainingRow
        from afre.statistical_models.artifacts import DesignMatrix, TrainingMatrixRow
        from afre.target_engine.models import TargetVintage

        require(
            not self._feature_only_depth
            or cls
            not in (
                TargetVintage,
                DesignMatrix,
                TrainingMatrixRow,
                InteractionMatrix,
                InteractionTrainingRow,
                SequenceDataset,
                SequenceTrainingRow,
            ),
            "forecast uncertainty cannot read target truth or training responses",
        )

    def resolve(self, cls: type[A], identity: str) -> A:
        self._guard(cls)
        return super().resolve(cls, identity)

    def put(self, value: Artifact) -> str:
        if type(value) not in UNCERTAINTY_TYPES:
            return super().put(value)
        require(self._in_transaction, "uncertainty write requires transaction")
        self._uncertainty_check_bounds(value)
        identity, payload = value.fingerprint, canonical_json(value)
        require(deserialize(payload) == value, "uncertainty canonical mismatch")
        if self._connection.execute(
            "SELECT 1 FROM unc_artifacts WHERE fingerprint=?", (identity,)
        ).fetchone():
            require(self.get(type(value), identity) == value, "conflicting uncertainty payload")
            return identity
        require(
            self._connection.execute(
                "SELECT count(*) FROM unc_artifacts WHERE type_name=?", (type(value).__name__,)
            ).fetchone()[0]
            < self.uncertainty_bounds.artifacts,
            "stored uncertainty artifact bound",
        )
        self._validate_links(value)
        self._connection.execute(
            "INSERT INTO unc_artifacts VALUES (?,?,?,?)",
            (identity, type(value).__name__, "1.0", payload),
        )
        self._connection.execute(
            "INSERT INTO unc_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            uncertainty_index(value),
        )
        from afre.uncertainty.lineage import uncertainty_edges

        self._connection.executemany(
            "INSERT INTO unc_links VALUES (?,?)",
            tuple((identity, i) for i in sorted(set(uncertainty_edges(value)))),
        )
        return identity

    def get(self, cls: type[A], identity: str) -> A:
        self._guard(cls)
        if cls not in UNCERTAINTY_TYPES:
            return super().get(cls, identity)
        validate_fingerprint(identity, cls.domain)
        row = self._connection.execute(
            "SELECT type_name,schema_version,payload FROM unc_artifacts WHERE fingerprint=?",
            (identity,),
        ).fetchone()
        if row is None:
            raise KeyError(identity)
        require(row[:2] == (cls.__name__, "1.0"), "uncertainty family/schema corruption")
        value = deserialize(row[2])
        require(
            type(value) is cls and value.fingerprint == identity, "uncertainty hash corruption"
        )
        self._uncertainty_check_bounds(value)
        require(
            self._connection.execute(
                "SELECT * FROM unc_records WHERE fingerprint=?", (identity,)
            ).fetchone()
            == uncertainty_index(value),
            "uncertainty relational index corruption",
        )
        from afre.uncertainty.lineage import uncertainty_edges

        require(
            tuple(
                r[0]
                for r in self._connection.execute(
                    (
                        "SELECT reference_id FROM unc_links WHERE fingerprint=? "
                        "ORDER BY reference_id"
                    ),
                    (identity,),
                )
            )
            == tuple(sorted(set(uncertainty_edges(value)))),
            "uncertainty link index corruption",
        )
        return cast(A, value)

    def get_any(self, identity: str) -> Artifact:
        if not identity.startswith("afre.unc_"):
            return super().get_any(identity)
        row = self._connection.execute(
            "SELECT type_name FROM unc_artifacts WHERE fingerprint=?", (identity,)
        ).fetchone()
        classes = {c.__name__: c for c in UNCERTAINTY_TYPES}
        require(row is not None and row[0] in classes, "unresolved uncertainty reference")
        assert row is not None
        return self.resolve(classes[row[0]], identity)

    def _validate_links(self, value: Artifact) -> None:
        if type(value) not in UNCERTAINTY_TYPES:
            super()._validate_links(value)
            return
        if value.fingerprint not in self._uncertainty_validated:
            from afre.uncertainty.validation import validate_uncertainty

            validate_uncertainty(self, value)
            self._uncertainty_validated.add(value.fingerprint)

    def audit(self) -> int:
        if not self._reading and not self._in_transaction:
            with self.read_snapshot():
                return self.audit()
        count = super().audit()
        with self.validation_cache():
            for identity, name in self._connection.execute(
                "SELECT fingerprint,type_name FROM unc_artifacts"
            ):
                require(
                    name in {c.__name__ for c in UNCERTAINTY_TYPES},
                    "unknown uncertainty family",
                )
                self._validate_links(self.get_any(identity))
                count += 1
            for table in ("unc_links", "unc_records"):
                require(
                    self._connection.execute(
                        f"SELECT count(*) FROM {table} r LEFT JOIN unc_artifacts a "
                        "ON r.fingerprint=a.fingerprint WHERE a.fingerprint IS NULL"
                    ).fetchone()[0]
                    == 0,
                    "orphan uncertainty projection",
                )
        return count

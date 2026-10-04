"""Shared store 1.6; frozen earlier layouts, payloads and metadata are preserved."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import ClassVar, TypeVar, cast

from afre.feature_store.repository import feature_store_schema
from afre.ids import validate_fingerprint
from afre.persistence import _schema_statements
from afre.probabilistic.artifacts import (
    ProbabilisticComparison,
    ProbabilisticEvaluation,
    ProbabilisticFitDiagnostics,
    ProbabilisticFitInputs,
    ProbabilisticFitRun,
    ProbabilisticForecast,
    ProbabilisticLineageAudit,
    ProbabilisticModelArtifact,
    TrainingDistribution,
    TrainingObservations,
)
from afre.probabilistic.definitions import (
    ProbabilisticEvaluationProtocol,
    ProbabilisticModelSpec,
    QuantileDefinition,
    QuantileInterval,
    ScaleSpec,
    ThresholdDefinition,
    ThresholdRequest,
)
from afre.probabilistic.schema import ProbabilisticBounds
from afre.probabilistic.storage import TABLES, probabilistic_schema, probability_indexes
from afre.research_datasets.schema import DatasetBounds
from afre.research_datasets.storage import dataset_schema
from afre.schema import Artifact, require
from afre.serialization import canonical_json, deserialize
from afre.statistical_models.repository import ModelRepository
from afre.statistical_models.schema import ModelBounds
from afre.statistical_models.storage import model_schema
from afre.target_engine.repository import target_schema
from afre.universe.repository import universe_schema
from afre.version import ENGINE_VERSION

PROBABILITY_TYPES: tuple[type[Artifact], ...] = (
    ProbabilisticBounds,
    ProbabilisticModelSpec,
    QuantileDefinition,
    ThresholdRequest,
    ThresholdDefinition,
    ScaleSpec,
    QuantileInterval,
    ProbabilisticEvaluationProtocol,
    TrainingObservations,
    ProbabilisticFitInputs,
    ProbabilisticFitDiagnostics,
    TrainingDistribution,
    ProbabilisticModelArtifact,
    ProbabilisticFitRun,
    ProbabilisticForecast,
    ProbabilisticEvaluation,
    ProbabilisticComparison,
    ProbabilisticLineageAudit,
)
P = TypeVar("P", bound=Artifact)


class ProbabilisticRepository(ModelRepository):
    _snapshot_engine_version: ClassVar[str] = ENGINE_VERSION

    def __init__(
        self,
        path: str | Path,
        bounds: ProbabilisticBounds | None = None,
        model_bounds: ModelBounds | None = None,
        dataset_bounds: DatasetBounds | None = None,
    ) -> None:
        self.probabilistic_bounds = bounds or ProbabilisticBounds()
        self._probability_validated: set[str] = set()
        super().__init__(path, model_bounds, dataset_bounds)

    @contextmanager
    def validation_cache(self) -> Iterator[None]:
        with super().validation_cache():
            try:
                yield
            finally:
                self._probability_validated.clear()

    def _migrate(self) -> None:
        version = self._connection.execute("PRAGMA user_version").fetchone()[0]
        require(version in range(8), "unknown future probabilistic store version")
        if version == 7:
            return
        if version < 6:
            ModelRepository._migrate(self)
        with self.transaction():
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 7:
                return
            require(version == 6, "unexpected probability migration version")
            ModelRepository._validate_layout(self)
            for statement in probabilistic_schema():
                self._connection.execute(statement)
            self._connection.executemany(
                "INSERT INTO metadata VALUES (?, ?)",
                (
                    ("probabilistic_store_schema_version", "1.6"),
                    ("probabilistic_schema", "1.0"),
                    ("probabilistic_engine_version", "0.7.0"),
                ),
            )
            self._connection.execute("PRAGMA user_version = 7")

    def _validate_layout(self) -> None:
        statements = (
            *_schema_statements(),
            *feature_store_schema(),
            *target_schema(),
            *universe_schema(),
            *dataset_schema(),
            *model_schema(),
            *probabilistic_schema(),
        )
        expected = {s.split()[2]: s for s in statements}
        actual = dict(
            self._connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        )
        require(expected == actual, "probabilistic schema/index/trigger corruption")
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
        }
        require(
            dict(self._connection.execute("SELECT key,value FROM metadata")) == metadata,
            "probabilistic metadata corruption",
        )
        require(
            self._connection.execute("PRAGMA user_version").fetchone()[0] == 7,
            "probabilistic integer version corruption",
        )

    def check_probability_bounds(self, value: Artifact) -> None:
        b = self.probabilistic_bounds
        require(
            len(canonical_json(value).encode()) <= b.serialized_bytes,
            "probability serialized byte bound",
        )
        if isinstance(value, ProbabilisticModelSpec):
            self.check_probability_bounds(value.quantiles)
            self.check_probability_bounds(value.thresholds)
        if isinstance(value, QuantileDefinition):
            require(len(value.levels) <= b.quantiles, "quantile level bound")
        if isinstance(value, ThresholdDefinition):
            require(len(value.requests) <= b.thresholds, "threshold request bound")
        if isinstance(value, TrainingObservations):
            require(len(value.rows) <= b.observations, "TRAIN observation bound")
        if isinstance(value, TrainingDistribution):
            require(len(value.values) <= b.observations, "TRAIN distribution count bound")
        if isinstance(value, ProbabilisticFitInputs):
            require(len(value.train_sample_ids) <= b.observations, "TRAIN fit evidence bound")
        if isinstance(value, ProbabilisticForecast):
            require(
                len(value.quantiles) <= b.quantiles
                and len(value.threshold_probabilities) <= b.thresholds
                and len(value.distribution.samples) <= b.observations,
                "forecast distribution bound",
            )
        if isinstance(value, ProbabilisticEvaluation):
            require(
                len(value.forecast_ids) <= b.forecasts, "probability evaluation forecast bound"
            )
        if isinstance(value, ProbabilisticLineageAudit):
            require(len(value.evidence_ids) <= b.audit_nodes, "probability audit node bound")

    def put(self, value: Artifact) -> str:
        if type(value) not in PROBABILITY_TYPES:
            return super().put(value)
        require(
            self._in_transaction and not self._reading,
            "probability writes require writer transaction",
        )
        self.check_probability_bounds(value)
        payload, identity = canonical_json(value), value.fingerprint
        require(deserialize(payload) == value, "probability canonical validation mismatch")
        if self._connection.execute(
            "SELECT 1 FROM p_artifacts WHERE fingerprint=?", (identity,)
        ).fetchone():
            require(self.get(type(value), identity) == value, "probability conflicting payload")
            return identity
        if isinstance(value, ProbabilisticEvaluation):
            require(
                self._connection.execute("SELECT count(*) FROM p_evaluations").fetchone()[0]
                < self.probabilistic_bounds.evaluations,
                "probability evaluation result bound",
            )
        self._validate_links(value)
        self._connection.execute(
            "INSERT INTO p_artifacts VALUES (?, ?, ?, ?)",
            (identity, type(value).__name__, "1.0", payload),
        )
        for table, values in probability_indexes(value, identity):
            self._connection.execute(
                f"INSERT INTO {table} VALUES ({','.join('?' for _ in values)})", values
            )
        return identity

    def get(self, cls: type[P], identity: str) -> P:
        if cls not in PROBABILITY_TYPES:
            return super().get(cls, identity)
        validate_fingerprint(identity, cls.domain)
        row = self._connection.execute(
            "SELECT type_name,schema_version,payload FROM p_artifacts WHERE fingerprint=?",
            (identity,),
        ).fetchone()
        if row is None:
            raise KeyError(identity)
        require(row[:2] == (cls.__name__, "1.0"), "probability family/schema corruption")
        value = deserialize(row[2])
        require(
            type(value) is cls and value.fingerprint == identity,
            "probability payload/fingerprint corruption",
        )
        self.check_probability_bounds(value)
        for table, values in probability_indexes(value, identity):
            require(
                self._connection.execute(
                    f"SELECT * FROM {table} WHERE fingerprint=?", (identity,)
                ).fetchone()
                == values,
                "probability relational index corruption",
            )
        return cast(P, value)

    def get_any(self, identity: str) -> Artifact:
        if not identity.startswith("afre.p_"):
            return super().get_any(identity)
        row = self._connection.execute(
            "SELECT type_name FROM p_artifacts WHERE fingerprint=?", (identity,)
        ).fetchone()
        classes = {c.__name__: c for c in PROBABILITY_TYPES}
        require(row is not None and row[0] in classes, "unresolved probability reference")
        assert row is not None
        return self.resolve(classes[row[0]], identity)

    def _validate_links(self, value: Artifact) -> None:
        if type(value) not in PROBABILITY_TYPES:
            super()._validate_links(value)
            return
        from afre.probabilistic.validation import validate_probability_links

        identity = self.identity(value)
        if identity not in self._probability_validated:
            validate_probability_links(self, value)
            self._probability_validated.add(identity)

    def probability_history(self, fold_id: str) -> tuple[ProbabilisticFitRun, ...]:
        rows = self._connection.execute(
            "SELECT fingerprint FROM p_fits WHERE fold_id=? "
            "ORDER BY available_ns,spec_id,fingerprint",
            (fold_id,),
        ).fetchall()
        require(len(rows) <= self.probabilistic_bounds.evaluations, "probability history bound")
        return tuple(self.resolve(ProbabilisticFitRun, row[0]) for row in rows)

    def audit(self) -> int:
        if not self._reading and not self._in_transaction:
            with self.read_snapshot():
                return self.audit()
        count = super().audit()
        with self.validation_cache():
            classes = {c.__name__: c for c in PROBABILITY_TYPES}
            for identity, name in self._connection.execute(
                "SELECT fingerprint,type_name FROM p_artifacts"
            ):
                require(name in classes, "unknown probabilistic family")
                self._validate_links(self.resolve(classes[name], identity))
                count += 1
            for table, family in zip(
                TABLES[1:],
                (
                    "ProbabilisticModelSpec",
                    "ProbabilisticFitRun",
                    "ProbabilisticForecast",
                    "ProbabilisticEvaluation",
                ),
                strict=True,
            ):
                require(
                    self._connection.execute(
                        f"SELECT count(*) FROM {table} LEFT JOIN p_artifacts a "
                        f"ON {table}.fingerprint=a.fingerprint "
                        "WHERE a.fingerprint IS NULL OR a.type_name!=?",
                        (family,),
                    ).fetchone()[0]
                    == 0,
                    "orphan probability index",
                )
        return count

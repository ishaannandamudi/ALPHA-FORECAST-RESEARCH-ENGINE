"""Additive shared store 1.5 with closed immutable model families and indexes."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import ClassVar, TypeVar, cast

from afre.feature_store.repository import feature_store_schema
from afre.ids import validate_fingerprint
from afre.models import ModelSpec
from afre.persistence import _schema_statements
from afre.research_datasets.manifests import ResearchDatasetManifest
from afre.research_datasets.repository import DatasetRepository
from afre.research_datasets.schema import DatasetBounds
from afre.research_datasets.splits import FoldDefinition
from afre.research_datasets.storage import dataset_schema
from afre.schema import Artifact, require
from afre.serialization import canonical_json, deserialize
from afre.statistical_models.artifacts import (
    BaselineComparison,
    DesignMatrix,
    FitDiagnostics,
    FittedModelArtifact,
    ModelFitInputs,
    ModelFitRun,
    ModelLineageAudit,
    PointEvaluation,
    PointForecast,
    PredictionInput,
)
from afre.statistical_models.definitions import BaselineModelSpec, PersistenceReference
from afre.statistical_models.schema import ModelBounds
from afre.statistical_models.storage import TABLES, model_indexes, model_schema
from afre.target_engine.repository import target_schema
from afre.universe.repository import universe_schema
from afre.version import ENGINE_VERSION

MODEL_TYPES: tuple[type[Artifact], ...] = (
    ModelBounds,
    PersistenceReference,
    BaselineModelSpec,
    DesignMatrix,
    ModelFitInputs,
    FitDiagnostics,
    FittedModelArtifact,
    ModelFitRun,
    PredictionInput,
    PointForecast,
    PointEvaluation,
    BaselineComparison,
    ModelLineageAudit,
)
M = TypeVar("M", bound=Artifact)


class ModelRepository(DatasetRepository):
    _snapshot_engine_version: ClassVar[str] = ENGINE_VERSION

    def __init__(
        self,
        path: str | Path,
        bounds: ModelBounds | None = None,
        dataset_bounds: DatasetBounds | None = None,
    ) -> None:
        self.model_bounds = bounds or ModelBounds()
        self._model_validated: set[str] = set()
        super().__init__(path, dataset_bounds)

    @contextmanager
    def validation_cache(self) -> Iterator[None]:
        with super().validation_cache():
            try:
                yield
            finally:
                self._model_validated.clear()

    def _migrate(self) -> None:
        version = self._connection.execute("PRAGMA user_version").fetchone()[0]
        require(version in range(7), "unknown future model store version")
        if version == 6:
            return
        if version < 5:
            DatasetRepository._migrate(self)
        with self.transaction():
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 6:
                return
            require(version == 5, "unexpected model migration version")
            DatasetRepository._validate_layout(self)
            for statement in model_schema():
                self._connection.execute(statement)
            self._connection.executemany(
                "INSERT INTO metadata VALUES (?, ?)",
                (
                    ("model_store_schema_version", "1.5"),
                    ("model_schema", "1.0"),
                    ("model_engine_version", "0.6.0"),
                ),
            )
            self._connection.execute("PRAGMA user_version = 6")

    def _validate_layout(self) -> None:
        statements = (
            *_schema_statements(),
            *feature_store_schema(),
            *target_schema(),
            *universe_schema(),
            *dataset_schema(),
            *model_schema(),
        )
        expected = {s.split()[2]: s for s in statements}
        actual = dict(
            self._connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        )
        require(expected == actual, "model schema/index/trigger corruption")
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
        }
        require(
            dict(self._connection.execute("SELECT key,value FROM metadata")) == metadata,
            "model metadata corruption",
        )
        require(
            self._connection.execute("PRAGMA user_version").fetchone()[0] == 6,
            "model integer version corruption",
        )

    def check_model_bounds(self, value: Artifact) -> None:
        b = self.model_bounds
        require(
            len(canonical_json(value).encode()) <= b.serialized_bytes,
            "model serialized byte bound",
        )
        if isinstance(value, BaselineModelSpec):
            require(
                len(value.feature_set.definitions) <= b.features
                and value.max_iterations <= b.iterations,
                "model feature/iteration bound",
            )
        if isinstance(value, DesignMatrix):
            require(
                len(value.rows) + len(value.exclusions) <= b.samples
                and len(value.feature_ids) <= b.features
                and len(value.rows) * max(1, len(value.feature_ids)) <= b.dense_cells,
                "model matrix sample/feature/dense-cell bound",
            )
        if isinstance(value, FittedModelArtifact):
            require(len(value.coefficients) <= b.coefficients, "model coefficient bound")
        if isinstance(value, ModelFitInputs):
            require(len(value.train_sample_ids) <= b.samples, "model TRAIN sample bound")
        if isinstance(value, PointEvaluation):
            require(len(value.prediction_ids) <= b.predictions, "evaluation prediction bound")
        if isinstance(value, ModelLineageAudit):
            require(len(value.evidence_ids) <= b.audit_nodes, "model audit node bound")

    def put(self, value: Artifact) -> str:
        if type(value) not in MODEL_TYPES:
            return super().put(value)
        require(
            self._in_transaction and not self._reading,
            "model writes require writer transaction",
        )
        self.check_model_bounds(value)
        payload, identity = canonical_json(value), value.fingerprint
        require(deserialize(payload) == value, "model canonical validation mismatch")
        if self._connection.execute(
            "SELECT 1 FROM m_artifacts WHERE fingerprint=?", (identity,)
        ).fetchone():
            require(self.get(type(value), identity) == value, "model conflicting payload")
            return identity
        if isinstance(value, PointEvaluation):
            require(
                self._connection.execute("SELECT count(*) FROM m_evaluations").fetchone()[0]
                < self.model_bounds.evaluations,
                "model evaluation result bound",
            )
        self._validate_links(value)
        self._connection.execute(
            "INSERT INTO m_artifacts VALUES (?, ?, ?, ?)",
            (identity, type(value).__name__, "1.0", payload),
        )
        for table, values in model_indexes(value, identity):
            self._connection.execute(
                f"INSERT INTO {table} VALUES ({','.join('?' for _ in values)})", values
            )
        return identity

    def get(self, cls: type[M], identity: str) -> M:
        if cls not in MODEL_TYPES:
            return super().get(cls, identity)
        validate_fingerprint(identity, cls.domain)
        row = self._connection.execute(
            "SELECT type_name,schema_version,payload FROM m_artifacts WHERE fingerprint=?",
            (identity,),
        ).fetchone()
        if row is None:
            raise KeyError(identity)
        require(row[:2] == (cls.__name__, "1.0"), "model family/schema corruption")
        value = deserialize(row[2])
        require(
            type(value) is cls and value.fingerprint == identity,
            "model payload/fingerprint corruption",
        )
        self.check_model_bounds(value)
        for table, values in model_indexes(value, identity):
            require(
                self._connection.execute(
                    f"SELECT * FROM {table} WHERE fingerprint=?", (identity,)
                ).fetchone()
                == values,
                "model relational index corruption",
            )
        return cast(M, value)

    def get_any(self, identity: str) -> Artifact:
        if identity.startswith("afre.model_spec:"):
            return self.resolve(ModelSpec, identity)
        if not identity.startswith("afre.m_"):
            return super().get_any(identity)
        row = self._connection.execute(
            "SELECT type_name FROM m_artifacts WHERE fingerprint=?", (identity,)
        ).fetchone()
        classes = {c.__name__: c for c in MODEL_TYPES}
        require(row is not None and row[0] in classes, "unresolved model reference")
        assert row is not None
        return self.resolve(classes[row[0]], identity)

    def resolve_dataset(self, identity: str) -> ResearchDatasetManifest:
        return self.resolve(ResearchDatasetManifest, identity)

    def resolve_fold(self, identity: str) -> FoldDefinition:
        return self.resolve(FoldDefinition, identity)

    def _validate_links(self, value: Artifact) -> None:
        if type(value) not in MODEL_TYPES:
            super()._validate_links(value)
            return
        from afre.statistical_models.validation import validate_model_links

        identity = self.identity(value)
        if identity not in self._model_validated:
            validate_model_links(self, value)
            self._model_validated.add(identity)

    def model_history(self, fold_id: str) -> tuple[ModelFitRun, ...]:
        rows = self._connection.execute(
            "SELECT fingerprint FROM m_fits WHERE fold_id=? "
            "ORDER BY available_ns,spec_id,fingerprint",
            (fold_id,),
        ).fetchall()
        require(len(rows) <= self.model_bounds.evaluations, "model history bound")
        return tuple(self.resolve(ModelFitRun, row[0]) for row in rows)

    def audit(self) -> int:
        if not self._reading and not self._in_transaction:
            with self.read_snapshot():
                return self.audit()
        count = super().audit()
        with self.validation_cache():
            classes = {c.__name__: c for c in MODEL_TYPES}
            for identity, name in self._connection.execute(
                "SELECT fingerprint,type_name FROM m_artifacts"
            ):
                require(name in classes, "unknown model family")
                self._validate_links(self.resolve(classes[name], identity))
                count += 1
            for table, expected_type in zip(
                TABLES[1:],
                ("BaselineModelSpec", "ModelFitRun", "PointForecast", "PointEvaluation"),
                strict=True,
            ):
                require(
                    self._connection.execute(
                        f"SELECT count(*) FROM {table} LEFT JOIN m_artifacts a ON "
                        f"{table}.fingerprint=a.fingerprint WHERE a.fingerprint IS NULL "
                        "OR a.type_name!=?",
                        (expected_type,),
                    ).fetchone()[0]
                    == 0,
                    "orphan model index",
                )
        return count

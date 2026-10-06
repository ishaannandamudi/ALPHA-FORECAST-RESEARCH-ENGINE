"""Store1.13 / SQLite14 additive migration above the unchanged mixture registry."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import ClassVar, TypeVar, cast

from afre.calibration.storage import calibration_schema
from afre.cross_sectional.storage import cross_section_schema
from afre.event_conditioned.storage import event_schema
from afre.feature_store.repository import feature_store_schema
from afre.ids import validate_fingerprint
from afre.mixture.repository import MixtureRepository
from afre.mixture.storage import mixture_schema
from afre.multihorizon.storage import multihorizon_schema
from afre.nonlinear.artifacts import (
    FittedTransformArtifact,
    InteractionMatrix,
    InteractionStability,
    InteractionTrainingRow,
    InteractionValue,
    NonlinearAudit,
    NonlinearCalibrationAssessment,
    NonlinearEvaluation,
    NonlinearEvaluationPair,
    NonlinearForecast,
    NonlinearInput,
    NonlinearModelArtifact,
    NonlinearProbabilityView,
    NonlinearRankEvaluation,
    NonlinearRanking,
    ScalarInput,
    TreeNode,
    TreePathStep,
)
from afre.nonlinear.bounds import artifact_limit, check_nonlinear_bounds
from afre.nonlinear.definitions import (
    InteractionDefinition,
    InteractionSet,
    NonlinearModelSpec,
    ScalarFeatureDefinition,
    TransformParameters,
    TreeParameters,
)
from afre.nonlinear.schema import NonlinearBounds
from afre.nonlinear.storage import nonlinear_index, nonlinear_schema
from afre.persistence import _schema_statements
from afre.probabilistic.storage import probabilistic_schema
from afre.regime_conditioned.storage import regime_schema
from afre.research_datasets.storage import dataset_schema
from afre.schema import Artifact, require
from afre.serialization import canonical_json, deserialize
from afre.statistical_models.storage import model_schema
from afre.target_engine.repository import target_schema
from afre.universe.repository import universe_schema

NONLINEAR_TYPES: tuple[type[Artifact], ...] = (
    ScalarInput,
    NonlinearInput,
    FittedTransformArtifact,
    InteractionValue,
    InteractionTrainingRow,
    InteractionMatrix,
    TreeNode,
    NonlinearModelArtifact,
    NonlinearProbabilityView,
    TreePathStep,
    NonlinearForecast,
    NonlinearEvaluationPair,
    NonlinearEvaluation,
    InteractionStability,
    NonlinearCalibrationAssessment,
    NonlinearRanking,
    NonlinearRankEvaluation,
    NonlinearAudit,
    ScalarFeatureDefinition,
    TransformParameters,
    InteractionDefinition,
    InteractionSet,
    TreeParameters,
    NonlinearModelSpec,
    NonlinearBounds,
)
A = TypeVar("A", bound=Artifact)


class NonlinearRepository(MixtureRepository):
    _snapshot_engine_version: ClassVar[str] = "0.14.0"

    def __init__(self, path: str | Path, bounds: NonlinearBounds | None = None) -> None:
        self.nonlinear_bounds = bounds or NonlinearBounds()
        self._nonlinear_validated: set[str] = set()
        super().__init__(path)

    @contextmanager
    def validation_cache(self) -> Iterator[None]:
        with super().validation_cache():
            try:
                yield
            finally:
                self._nonlinear_validated.clear()

    def _migrate(self) -> None:
        version = self._connection.execute("PRAGMA user_version").fetchone()[0]
        require(version in range(15), "unknown future nonlinear store version")
        if version == 14:
            return
        if version < 13:
            MixtureRepository._migrate(self)
        with self.transaction():
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 14:
                return
            require(version == 13, "unexpected nonlinear migration version")
            MixtureRepository._validate_layout(self)
            for statement in nonlinear_schema():
                self._connection.execute(statement)
            self._connection.executemany(
                "INSERT INTO metadata VALUES (?,?)",
                (
                    ("nonlinear_store_schema_version", "1.13"),
                    ("nonlinear_schema", "1.0"),
                    ("nonlinear_engine_version", "0.14.0"),
                ),
            )
            self._connection.execute("PRAGMA user_version=14")

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
            *regime_schema(),
            *mixture_schema(),
            *nonlinear_schema(),
        )
        require(
            {s.split()[2]: s for s in statements}
            == dict(
                self._connection.execute(
                    "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
                )
            ),
            "nonlinear schema/index/trigger corruption",
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
            "regime_store_schema_version": "1.11",
            "regime_conditioned_schema": "1.0",
            "regime_conditioned_engine_version": "0.12.0",
            "mixture_store_schema_version": "1.12",
            "mixture_schema": "1.0",
            "mixture_engine_version": "0.13.0",
            "nonlinear_store_schema_version": "1.13",
            "nonlinear_schema": "1.0",
            "nonlinear_engine_version": "0.14.0",
        }
        require(
            dict(self._connection.execute("SELECT key,value FROM metadata")) == metadata,
            "nonlinear metadata corruption",
        )
        require(
            self._connection.execute("PRAGMA user_version").fetchone()[0] == 14,
            "nonlinear integer version corruption",
        )

    def put(self, value: Artifact) -> str:
        if type(value) not in NONLINEAR_TYPES:
            return super().put(value)
        require(self._in_transaction, "nonlinear write requires transaction")
        check_nonlinear_bounds(value, self.nonlinear_bounds)
        identity, payload = value.fingerprint, canonical_json(value)
        require(deserialize(payload) == value, "nonlinear canonical mismatch")
        if self._connection.execute(
            "SELECT 1 FROM nl_artifacts WHERE fingerprint=?", (identity,)
        ).fetchone():
            require(self.get(type(value), identity) == value, "conflicting mixture payload")
            return identity
        count = self._connection.execute(
            "SELECT count(*) FROM nl_artifacts WHERE type_name=?", (type(value).__name__,)
        ).fetchone()[0]
        require(
            count < artifact_limit(value, self.nonlinear_bounds),
            "stored mixture artifact bound",
        )
        self._validate_links(value)
        self._connection.execute(
            "INSERT INTO nl_artifacts VALUES (?,?,?,?)",
            (identity, type(value).__name__, "1.0", payload),
        )
        self._connection.execute(
            "INSERT INTO nl_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            nonlinear_index(value),
        )
        from afre.nonlinear.lineage import nonlinear_edges

        self._connection.executemany(
            "INSERT INTO nl_links VALUES (?,?)",
            tuple((identity, i) for i in sorted(set(nonlinear_edges(value)))),
        )
        return identity

    def get(self, cls: type[A], identity: str) -> A:
        if cls not in NONLINEAR_TYPES:
            return super().get(cls, identity)
        validate_fingerprint(identity, cls.domain)
        row = self._connection.execute(
            "SELECT type_name,schema_version,payload FROM nl_artifacts WHERE fingerprint=?",
            (identity,),
        ).fetchone()
        if row is None:
            raise KeyError(identity)
        require(row[:2] == (cls.__name__, "1.0"), "nonlinear family/schema corruption")
        value = deserialize(row[2])
        require(
            type(value) is cls and value.fingerprint == identity, "nonlinear hash corruption"
        )
        check_nonlinear_bounds(value, self.nonlinear_bounds)
        require(
            self._connection.execute(
                "SELECT * FROM nl_records WHERE fingerprint=?", (identity,)
            ).fetchone()
            == nonlinear_index(value),
            "nonlinear relational index corruption",
        )
        from afre.nonlinear.lineage import nonlinear_edges

        require(
            tuple(
                r[0]
                for r in self._connection.execute(
                    (
                        "SELECT reference_id FROM nl_links WHERE fingerprint=? ORDER BY "
                        "reference_id"
                    ),
                    (identity,),
                )
            )
            == tuple(sorted(set(nonlinear_edges(value)))),
            "nonlinear link index corruption",
        )
        return cast(A, value)

    def get_any(self, identity: str) -> Artifact:
        if not identity.startswith("afre.nl_"):
            return super().get_any(identity)
        row = self._connection.execute(
            "SELECT type_name FROM nl_artifacts WHERE fingerprint=?", (identity,)
        ).fetchone()
        classes = {c.__name__: c for c in NONLINEAR_TYPES}
        require(row is not None and row[0] in classes, "unresolved nonlinear reference")
        assert row is not None
        return self.resolve(classes[row[0]], identity)

    def _validate_links(self, value: Artifact) -> None:
        if type(value) not in NONLINEAR_TYPES:
            super()._validate_links(value)
            return
        from afre.nonlinear.validation import validate_nonlinear

        if value.fingerprint not in self._nonlinear_validated:
            validate_nonlinear(self, value)
            self._nonlinear_validated.add(value.fingerprint)

    def audit(self) -> int:
        if not self._reading and not self._in_transaction:
            with self.read_snapshot():
                return self.audit()
        count = super().audit()
        with self.validation_cache():
            for identity, name in self._connection.execute(
                "SELECT fingerprint,type_name FROM nl_artifacts"
            ):
                require(
                    name in {c.__name__ for c in NONLINEAR_TYPES}, "unknown nonlinear family"
                )
                self._validate_links(self.get_any(identity))
                count += 1
            require(
                self._connection.execute(
                    "SELECT count(*) FROM nl_links l LEFT JOIN nl_artifacts a ON "
                    "l.fingerprint=a.fingerprint WHERE a.fingerprint IS NULL"
                ).fetchone()[0]
                == 0,
                "orphan nonlinear links",
            )
            require(
                self._connection.execute(
                    "SELECT count(*) FROM nl_records r LEFT JOIN nl_artifacts a ON "
                    "r.fingerprint=a.fingerprint WHERE a.fingerprint IS NULL"
                ).fetchone()[0]
                == 0,
                "orphan mixture index",
            )
        return count

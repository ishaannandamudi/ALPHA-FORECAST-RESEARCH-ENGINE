"""Store1.12 / SQLite13, preserving every earlier registry row, DDL and metadata."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import ClassVar, TypeVar, cast

from afre.calibration.storage import calibration_schema
from afre.cross_sectional.storage import cross_section_schema
from afre.event_conditioned.storage import event_schema
from afre.feature_store.repository import feature_store_schema
from afre.ids import validate_fingerprint
from afre.mixture.artifacts import (
    ExpertContribution,
    ExpertDiagnostic,
    GateDriftDiagnostic,
    GateModelArtifact,
    GateTrainingRow,
    MatchedExpertComparison,
    MixtureAudit,
    MixtureCalibrationAssessment,
    MixtureComponent,
    MixtureDiagnostics,
    MixtureDistribution,
    MixtureEvaluation,
    MixtureEvaluationPair,
    MixtureForecast,
    MixtureRankEvaluation,
    MixtureRanking,
    MixtureRequest,
)
from afre.mixture.bounds import artifact_limit, check_mixture_bounds
from afre.mixture.definitions import ExpertSet, FixedGateSpec, LearnedGateSpec
from afre.mixture.experts import (
    ExpertForecastBinding,
    ExpertReference,
    ExternalExpertForecast,
    GatingFeatureReference,
)
from afre.mixture.schema import MixtureBounds
from afre.mixture.storage import mixture_index, mixture_schema
from afre.multihorizon.storage import multihorizon_schema
from afre.persistence import _schema_statements
from afre.probabilistic.storage import probabilistic_schema
from afre.regime_conditioned.repository import RegimeRepository
from afre.regime_conditioned.storage import regime_schema
from afre.research_datasets.storage import dataset_schema
from afre.schema import Artifact, require
from afre.serialization import canonical_json, deserialize
from afre.statistical_models.storage import model_schema
from afre.target_engine.repository import target_schema
from afre.universe.repository import universe_schema

MIXTURE_TYPES: tuple[type[Artifact], ...] = (
    MixtureAudit,
    MixtureCalibrationAssessment,
    MixtureEvaluation,
    MixtureForecast,
    MixtureDiagnostics,
    GateDriftDiagnostic,
    MixtureEvaluationPair,
    ExpertDiagnostic,
    GateModelArtifact,
    GateTrainingRow,
    MixtureDistribution,
    MixtureComponent,
    ExpertContribution,
    MatchedExpertComparison,
    MixtureRequest,
    MixtureRanking,
    MixtureRankEvaluation,
    ExpertSet,
    FixedGateSpec,
    LearnedGateSpec,
    ExpertReference,
    ExpertForecastBinding,
    ExternalExpertForecast,
    GatingFeatureReference,
    MixtureBounds,
)
A = TypeVar("A", bound=Artifact)


class MixtureRepository(RegimeRepository):
    _snapshot_engine_version: ClassVar[str] = "0.13.0"

    def __init__(self, path: str | Path, bounds: MixtureBounds | None = None) -> None:
        self.mixture_bounds = bounds or MixtureBounds()
        self._mixture_validated: set[str] = set()
        super().__init__(path)

    @contextmanager
    def validation_cache(self) -> Iterator[None]:
        with super().validation_cache():
            try:
                yield
            finally:
                self._mixture_validated.clear()

    def _migrate(self) -> None:
        version = self._connection.execute("PRAGMA user_version").fetchone()[0]
        require(version in range(14), "unknown future mixture store version")
        if version == 13:
            return
        if version < 12:
            RegimeRepository._migrate(self)
        with self.transaction():
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 13:
                return
            require(version == 12, "unexpected mixture migration version")
            RegimeRepository._validate_layout(self)
            for statement in mixture_schema():
                self._connection.execute(statement)
            self._connection.executemany(
                "INSERT INTO metadata VALUES (?,?)",
                (
                    ("mixture_store_schema_version", "1.12"),
                    ("mixture_schema", "1.0"),
                    ("mixture_engine_version", "0.13.0"),
                ),
            )
            self._connection.execute("PRAGMA user_version=13")

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
        )
        require(
            {s.split()[2]: s for s in statements}
            == dict(
                self._connection.execute(
                    "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
                )
            ),
            "mixture schema/index/trigger corruption",
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
        }
        require(
            dict(self._connection.execute("SELECT key,value FROM metadata")) == metadata,
            "mixture metadata corruption",
        )
        require(
            self._connection.execute("PRAGMA user_version").fetchone()[0] == 13,
            "mixture integer version corruption",
        )

    def put(self, value: Artifact) -> str:
        if type(value) not in MIXTURE_TYPES:
            return super().put(value)
        require(self._in_transaction, "mixture write requires transaction")
        check_mixture_bounds(value, self.mixture_bounds)
        identity, payload = value.fingerprint, canonical_json(value)
        require(deserialize(payload) == value, "mixture canonical mismatch")
        if self._connection.execute(
            "SELECT 1 FROM mix_artifacts WHERE fingerprint=?", (identity,)
        ).fetchone():
            require(self.get(type(value), identity) == value, "conflicting mixture payload")
            return identity
        count = self._connection.execute(
            "SELECT count(*) FROM mix_artifacts WHERE type_name=?", (type(value).__name__,)
        ).fetchone()[0]
        require(
            count < artifact_limit(value, self.mixture_bounds), "stored mixture artifact bound"
        )
        self._validate_links(value)
        self._connection.execute(
            "INSERT INTO mix_artifacts VALUES (?,?,?,?)",
            (identity, type(value).__name__, "1.0", payload),
        )
        self._connection.execute(
            "INSERT INTO mix_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            mixture_index(value),
        )
        return identity

    def get(self, cls: type[A], identity: str) -> A:
        if cls not in MIXTURE_TYPES:
            return super().get(cls, identity)
        validate_fingerprint(identity, cls.domain)
        row = self._connection.execute(
            "SELECT type_name,schema_version,payload FROM mix_artifacts WHERE fingerprint=?",
            (identity,),
        ).fetchone()
        if row is None:
            raise KeyError(identity)
        require(row[:2] == (cls.__name__, "1.0"), "mixture family/schema corruption")
        value = deserialize(row[2])
        require(type(value) is cls and value.fingerprint == identity, "mixture hash corruption")
        check_mixture_bounds(value, self.mixture_bounds)
        require(
            self._connection.execute(
                "SELECT * FROM mix_records WHERE fingerprint=?", (identity,)
            ).fetchone()
            == mixture_index(value),
            "mixture relational index corruption",
        )
        return cast(A, value)

    def get_any(self, identity: str) -> Artifact:
        if not identity.startswith("afre.mix_"):
            return super().get_any(identity)
        row = self._connection.execute(
            "SELECT type_name FROM mix_artifacts WHERE fingerprint=?", (identity,)
        ).fetchone()
        classes = {c.__name__: c for c in MIXTURE_TYPES}
        require(row is not None and row[0] in classes, "unresolved mixture reference")
        assert row is not None
        return self.resolve(classes[row[0]], identity)

    def _validate_links(self, value: Artifact) -> None:
        if type(value) not in MIXTURE_TYPES:
            super()._validate_links(value)
            return
        from afre.mixture.validation import validate_mixture

        if value.fingerprint not in self._mixture_validated:
            validate_mixture(self, value)
            self._mixture_validated.add(value.fingerprint)

    def audit(self) -> int:
        if not self._reading and not self._in_transaction:
            with self.read_snapshot():
                return self.audit()
        count = super().audit()
        with self.validation_cache():
            for identity, name in self._connection.execute(
                "SELECT fingerprint,type_name FROM mix_artifacts"
            ):
                require(name in {c.__name__ for c in MIXTURE_TYPES}, "unknown mixture family")
                self._validate_links(self.get_any(identity))
                count += 1
            require(
                self._connection.execute(
                    "SELECT count(*) FROM mix_records r LEFT JOIN mix_artifacts a ON "
                    "r.fingerprint=a.fingerprint WHERE a.fingerprint IS NULL"
                ).fetchone()[0]
                == 0,
                "orphan mixture index",
            )
        return count

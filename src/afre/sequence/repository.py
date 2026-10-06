"""Strict store1.14/SQLite15; every earlier interface remains inherited and unchanged."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import ClassVar, TypeVar, cast

from afre.forecast import ForecastOrigin
from afre.ids import validate_fingerprint
from afre.nonlinear.repository import NonlinearRepository
from afre.schema import Artifact, require
from afre.sequence.artifacts import (
    SequenceAudit,
    SequenceCalibrationAssessment,
    SequenceContribution,
    SequenceCoverage,
    SequenceDataset,
    SequenceEvaluation,
    SequenceEvaluationPair,
    SequenceForecast,
    SequenceModelArtifact,
    SequenceObservation,
    SequenceRankEvaluation,
    SequenceRanking,
    SequenceSnapshot,
    SequenceStability,
    SequenceTrainingRow,
    SequenceTransformArtifact,
)
from afre.sequence.definitions import (
    SequenceFeatureDefinition,
    SequenceModelSpec,
    SequenceWindowSpec,
)
from afre.sequence.schema import SequenceBounds
from afre.sequence.storage import METADATA, all_statements, sequence_index, sequence_schema
from afre.serialization import canonical_json, deserialize

SEQUENCE_TYPES: tuple[type[Artifact], ...] = (
    SequenceAudit,
    SequenceCalibrationAssessment,
    SequenceContribution,
    SequenceCoverage,
    SequenceDataset,
    SequenceEvaluation,
    SequenceEvaluationPair,
    SequenceForecast,
    SequenceModelArtifact,
    SequenceObservation,
    SequenceRankEvaluation,
    SequenceRanking,
    SequenceSnapshot,
    SequenceStability,
    SequenceTrainingRow,
    SequenceTransformArtifact,
    SequenceFeatureDefinition,
    SequenceModelSpec,
    SequenceWindowSpec,
    SequenceBounds,
)
A = TypeVar("A", bound=Artifact)


class SequenceRepository(NonlinearRepository):
    _snapshot_engine_version: ClassVar[str] = "0.15.0"

    def __init__(self, path: str | Path, bounds: SequenceBounds | None = None) -> None:
        self.sequence_bounds = bounds or SequenceBounds()
        self._sequence_validated: set[str] = set()
        self._feature_only_depth = 0
        super().__init__(path)

    @contextmanager
    def feature_only(self) -> Iterator[None]:
        self._feature_only_depth += 1
        try:
            yield
        finally:
            self._feature_only_depth -= 1

    @contextmanager
    def validation_cache(self) -> Iterator[None]:
        with super().validation_cache():
            try:
                yield
            finally:
                self._sequence_validated.clear()

    def _migrate(self) -> None:
        version = self._connection.execute("PRAGMA user_version").fetchone()[0]
        require(version in range(16), "unknown future sequence store version")
        if version == 15:
            return
        if version < 14:
            NonlinearRepository._migrate(self)
        with self.transaction():
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 15:
                return
            require(version == 14, "unexpected sequence migration version")
            NonlinearRepository._validate_layout(self)
            for statement in sequence_schema():
                self._connection.execute(statement)
            self._connection.executemany(
                "INSERT INTO metadata VALUES (?,?)",
                (
                    ("sequence_store_schema_version", "1.14"),
                    ("sequence_schema", "1.0"),
                    ("sequence_engine_version", "0.15.0"),
                ),
            )
            self._connection.execute("PRAGMA user_version=15")

    def _validate_layout(self) -> None:
        require(
            {s.split()[2]: s for s in all_statements()}
            == dict(
                self._connection.execute(
                    "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
                )
            ),
            "sequence schema/index/trigger corruption",
        )
        require(
            dict(self._connection.execute("SELECT key,value FROM metadata")) == METADATA,
            "sequence metadata corruption",
        )
        require(
            self._connection.execute("PRAGMA user_version").fetchone()[0] == 15,
            "sequence integer version corruption",
        )

    def observation_ids(
        self,
        features: tuple[SequenceFeatureDefinition, ...],
        origin: "ForecastOrigin",
        constructed_ns: int | None = None,
    ) -> tuple[str, ...]:
        from afre.forecast import ForecastOrigin

        require(
            isinstance(origin, ForecastOrigin)
            and 0 < len(features) <= self.sequence_bounds.features,
            "sequence observation query bounds",
        )
        placeholders = ",".join("?" for _ in features)
        rows = self._connection.execute(
            (
                f"SELECT fingerprint FROM sq_records WHERE feature_id IN ({placeholders}) "
                "AND security_id=? AND available_ns<=? AND afre_ready_ns<=? "
                "ORDER BY origin_ns,available_ns,fingerprint LIMIT ?"
            ),
            (
                *tuple(f.fingerprint for f in features),
                origin.instrument.fingerprint,
                origin.availability_cutoff_ns if constructed_ns is None else constructed_ns,
                origin.availability_cutoff_ns if constructed_ns is None else constructed_ns,
                self.sequence_bounds.observations + 1,
            ),
        ).fetchall()
        require(
            len(rows) <= self.sequence_bounds.observations, "sequence history query overflow"
        )
        return tuple(r[0] for r in rows)

    def _bounds(self, value: Artifact) -> None:
        b = self.sequence_bounds
        require(
            len(canonical_json(value).encode()) <= b.serialized_bytes, "sequence payload bound"
        )
        if isinstance(value, SequenceSnapshot):
            require(
                len(value.values) <= b.length
                and len(value.feature_ids) <= b.features
                and len(value.candidate_ids) <= b.observations,
                "snapshot resource bound",
            )
        if isinstance(value, SequenceModelSpec):
            require(
                len(value.features) <= b.features
                and value.window.maximum_observations <= b.length,
                "model dimension bound",
            )
        if isinstance(value, SequenceWindowSpec):
            require(
                value.maximum_observations <= b.length
                and len(value.exact_observation_ids) <= b.observations,
                "window resource bound",
            )
        if isinstance(value, SequenceModelArtifact):
            require(
                len(value.coefficients) <= b.features
                and len(value.train_sample_ids) <= b.training_rows,
                "fitted model resource bound",
            )
        if isinstance(value, SequenceTransformArtifact):
            require(
                len(value.centers) <= b.features
                and len(value.train_bindings) <= b.training_rows,
                "transform resource bound",
            )
        if isinstance(value, SequenceForecast):
            require(
                len(value.aggregates) <= b.features
                and len(value.contributions) <= b.length * b.features
                and len(value.state_trajectory) <= b.length,
                "forecast resource bound",
            )
        if isinstance(value, SequenceDataset):
            require(len(value.rows) <= b.training_rows, "dataset TRAIN bound")

    def put(self, value: Artifact) -> str:
        if type(value) not in SEQUENCE_TYPES:
            return super().put(value)
        require(self._in_transaction, "sequence write requires transaction")
        self._bounds(value)
        identity, payload = value.fingerprint, canonical_json(value)
        require(deserialize(payload) == value, "sequence canonical mismatch")
        if self._connection.execute(
            "SELECT 1 FROM sq_artifacts WHERE fingerprint=?", (identity,)
        ).fetchone():
            require(self.get(type(value), identity) == value, "conflicting sequence payload")
            return identity
        count = self._connection.execute(
            "SELECT count(*) FROM sq_artifacts WHERE type_name=?", (type(value).__name__,)
        ).fetchone()[0]
        limit = (
            self.sequence_bounds.observations
            if isinstance(value, SequenceObservation)
            else self.sequence_bounds.forecasts
        )
        require(count < limit, "stored sequence artifact bound")
        self._validate_links(value)
        self._connection.execute(
            "INSERT INTO sq_artifacts VALUES (?,?,?,?)",
            (identity, type(value).__name__, "1.0", payload),
        )
        self._connection.execute(
            "INSERT INTO sq_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            sequence_index(value),
        )
        from afre.sequence.lineage import sequence_edges

        self._connection.executemany(
            "INSERT INTO sq_links VALUES (?,?)",
            tuple((identity, i) for i in sorted(set(sequence_edges(value)))),
        )
        return identity

    def get(self, cls: type[A], identity: str) -> A:
        from afre.nonlinear.artifacts import InteractionMatrix, InteractionTrainingRow
        from afre.target_engine.models import TargetVintage

        require(
            not self._feature_only_depth
            or cls
            not in (
                TargetVintage,
                SequenceDataset,
                SequenceTrainingRow,
                InteractionMatrix,
                InteractionTrainingRow,
            ),
            "sequence prediction cannot read target truth or training labels",
        )
        if cls not in SEQUENCE_TYPES:
            return super().get(cls, identity)
        validate_fingerprint(identity, cls.domain)
        row = self._connection.execute(
            ("SELECT type_name,schema_version,payload FROM sq_artifacts WHERE fingerprint=?"),
            (identity,),
        ).fetchone()
        if row is None:
            raise KeyError(identity)
        require(row[:2] == (cls.__name__, "1.0"), "sequence family/schema corruption")
        value = deserialize(row[2])
        require(
            type(value) is cls and value.fingerprint == identity, "sequence hash corruption"
        )
        self._bounds(value)
        require(
            self._connection.execute(
                "SELECT * FROM sq_records WHERE fingerprint=?", (identity,)
            ).fetchone()
            == sequence_index(value),
            "sequence relational index corruption",
        )
        from afre.sequence.lineage import sequence_edges

        require(
            tuple(
                r[0]
                for r in self._connection.execute(
                    (
                        "SELECT reference_id FROM sq_links WHERE fingerprint=? "
                        "ORDER BY reference_id"
                    ),
                    (identity,),
                )
            )
            == tuple(sorted(set(sequence_edges(value)))),
            "sequence link index corruption",
        )
        return cast(A, value)

    def get_any(self, identity: str) -> Artifact:
        if not identity.startswith("afre.sq_"):
            return super().get_any(identity)
        row = self._connection.execute(
            "SELECT type_name FROM sq_artifacts WHERE fingerprint=?", (identity,)
        ).fetchone()
        classes = {c.__name__: c for c in SEQUENCE_TYPES}
        require(row is not None and row[0] in classes, "unresolved sequence reference")
        assert row is not None
        return self.resolve(classes[row[0]], identity)

    def _validate_links(self, value: Artifact) -> None:
        if type(value) not in SEQUENCE_TYPES:
            super()._validate_links(value)
            return
        if value.fingerprint not in self._sequence_validated:
            from afre.sequence.validation import validate_sequence

            validate_sequence(self, value)
            self._sequence_validated.add(value.fingerprint)

    def audit(self) -> int:
        if not self._reading and not self._in_transaction:
            with self.read_snapshot():
                return self.audit()
        count = super().audit()
        with self.validation_cache():
            for identity, name in self._connection.execute(
                "SELECT fingerprint,type_name FROM sq_artifacts"
            ):
                require(name in {c.__name__ for c in SEQUENCE_TYPES}, "unknown sequence family")
                self._validate_links(self.get_any(identity))
                count += 1
            for table in ("sq_links", "sq_records"):
                require(
                    self._connection.execute(
                        f"SELECT count(*) FROM {table} r LEFT JOIN sq_artifacts a "
                        "ON r.fingerprint=a.fingerprint WHERE a.fingerprint IS NULL"
                    ).fetchone()[0]
                    == 0,
                    "orphan sequence projection",
                )
        return count

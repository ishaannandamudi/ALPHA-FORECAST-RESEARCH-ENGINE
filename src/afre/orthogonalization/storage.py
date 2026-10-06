"""Additive immutable SQLite17 objects; all earlier DDL and metadata preserved."""

from afre.orthogonalization.artifacts import (
    AlignedSignalRow,
    OrthogonalSignalValue,
    ProjectionArtifact,
    RedundancyMatrix,
)
from afre.orthogonalization.definitions import OrthogonalizationSpec, SignalReference
from afre.orthogonalization.evaluation_artifacts import (
    PredictiveModelPair,
    RedundancyEvaluation,
)
from afre.orthogonalization.signals import SignalObservation
from afre.schema import Artifact
from afre.uncertainty.storage import METADATA as PREVIOUS_METADATA
from afre.uncertainty.storage import all_statements as previous_statements

METADATA = {
    **PREVIOUS_METADATA,
    "orthogonalization_store_schema_version": "1.16",
    "orthogonalization_schema": "1.0",
    "orthogonalization_engine_version": "0.17.0",
}


def orthogonalization_schema() -> tuple[str, ...]:
    statements = [
        (
            "CREATE TABLE ort_artifacts (fingerprint TEXT PRIMARY KEY NOT NULL, "
            "type_name TEXT NOT NULL, schema_version TEXT NOT NULL, payload TEXT "
            "NOT NULL)"
        ),
        (
            "CREATE TABLE ort_records (fingerprint TEXT PRIMARY KEY NOT NULL, "
            "candidate_id TEXT, source_id TEXT, projection_id TEXT, sample_id TEXT, "
            "security_id TEXT, origin_ns INTEGER, target_id TEXT, horizon_id TEXT, "
            "fold_id TEXT, cutoff_ns INTEGER, available_ns INTEGER, test_id TEXT)"
        ),
        (
            "CREATE TABLE ort_links (fingerprint TEXT NOT NULL, reference_id TEXT "
            "NOT NULL, PRIMARY KEY (fingerprint, reference_id))"
        ),
        "CREATE INDEX ort_candidate_idx ON ort_records (candidate_id, source_id, available_ns)",
        "CREATE INDEX ort_projection_idx ON ort_records (projection_id, available_ns)",
        "CREATE INDEX ort_origin_idx ON ort_records (security_id, origin_ns, sample_id)",
        "CREATE INDEX ort_target_idx ON ort_records (target_id, horizon_id)",
        "CREATE INDEX ort_evaluation_idx ON ort_records (fold_id, cutoff_ns, test_id)",
        "CREATE INDEX ort_reference_idx ON ort_links (reference_id, fingerprint)",
    ]
    for table in ("ort_artifacts", "ort_records"):
        statements.append(
            f"CREATE TRIGGER immutable_{table}_insert BEFORE INSERT ON {table} WHEN "
            f"EXISTS (SELECT 1 FROM {table} WHERE fingerprint=NEW.fingerprint) BEGIN "
            f"SELECT RAISE(ABORT, 'immutable AFRE artifact'); END"
        )
    for table in ("ort_artifacts", "ort_records", "ort_links"):
        for operation in ("UPDATE", "DELETE"):
            statements.append(
                f"CREATE TRIGGER immutable_{table}_{operation.lower()} BEFORE "
                f"{operation} ON {table} BEGIN SELECT RAISE(ABORT, 'immutable AFRE "
                f"artifact'); END"
            )
    return tuple(statements)


def all_statements() -> tuple[str, ...]:
    return (*previous_statements(), *orthogonalization_schema())


def orthogonalization_index(v: Artifact) -> tuple[object, ...]:
    candidate = source = projection = sample = security = origin = target = horizon = fold = (
        cutoff
    ) = available = test = None
    if isinstance(v, SignalReference):
        candidate = v.fingerprint
    elif isinstance(v, OrthogonalizationSpec):
        candidate = v.candidate.fingerprint
        target = v.target.fingerprint
        horizon = v.target.horizon.fingerprint
        fold = v.fold_id
        cutoff = v.cutoff_ns
    elif isinstance(v, SignalObservation):
        candidate = v.reference_id
        source = v.source_id
        sample = v.sample_id
        security = v.origin.instrument.fingerprint
        origin = v.origin.timestamp_ns
        available = v.available_ns
    elif isinstance(v, AlignedSignalRow):
        sample = v.sample_id
        security = v.origin.instrument.fingerprint
        origin = v.origin.timestamp_ns
        available = v.available_ns
    elif isinstance(v, ProjectionArtifact):
        projection = v.fingerprint
        cutoff = v.cutoff_ns
        available = v.available_ns
    elif isinstance(v, OrthogonalSignalValue):
        projection = v.projection_id
        sample = v.sample_id
        security = v.origin.instrument.fingerprint
        origin = v.origin.timestamp_ns
        available = v.available_ns
    elif isinstance(v, (PredictiveModelPair, RedundancyEvaluation)):
        projection = v.projection_id
        cutoff = v.cutoff_ns
        available = v.available_ns
        test = v.test_evaluation_id if isinstance(v, RedundancyEvaluation) else None
    elif isinstance(v, RedundancyMatrix):
        available = v.available_ns
    return (
        v.fingerprint,
        candidate,
        source,
        projection,
        sample,
        security,
        origin,
        target,
        horizon,
        fold,
        cutoff,
        available,
        test,
    )

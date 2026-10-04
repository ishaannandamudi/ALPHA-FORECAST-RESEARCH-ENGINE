"""Fixed immutable model artifact tables and independently checked indexes."""

from afre.schema import Artifact
from afre.statistical_models.artifacts import ModelFitRun, PointEvaluation, PointForecast
from afre.statistical_models.definitions import BaselineModelSpec

TABLES = ("m_artifacts", "m_specs", "m_fits", "m_predictions", "m_evaluations")


def model_schema() -> tuple[str, ...]:
    statements = [
        "CREATE TABLE m_artifacts (fingerprint TEXT PRIMARY KEY NOT NULL, type_name "
        "TEXT NOT NULL, schema_version TEXT NOT NULL, payload TEXT NOT NULL)",
        "CREATE TABLE m_specs (fingerprint TEXT PRIMARY KEY NOT NULL, family TEXT "
        "NOT NULL, fold_id TEXT NOT NULL, target_id TEXT NOT NULL, feature_set_id "
        "TEXT NOT NULL)",
        "CREATE TABLE m_fits (fingerprint TEXT PRIMARY KEY NOT NULL, artifact_id "
        "TEXT NOT NULL UNIQUE, spec_id TEXT NOT NULL, dataset_id TEXT NOT NULL, "
        "split_id TEXT NOT NULL, fold_id TEXT NOT NULL, matrix_id TEXT NOT NULL, "
        "available_ns INTEGER NOT NULL)",
        "CREATE TABLE m_predictions (fingerprint TEXT PRIMARY KEY NOT NULL, "
        "artifact_id TEXT NOT NULL, target_id TEXT NOT NULL, security_id TEXT NOT "
        "NULL, origin_ns INTEGER NOT NULL, scope TEXT NOT NULL, sample_id TEXT, "
        "available_ns INTEGER NOT NULL)",
        "CREATE TABLE m_evaluations (fingerprint TEXT PRIMARY KEY NOT NULL, "
        "artifact_id TEXT NOT NULL, dataset_id TEXT NOT NULL, fold_id TEXT NOT NULL, "
        "target_id TEXT NOT NULL, scope TEXT NOT NULL, cutoff_ns INTEGER NOT NULL)",
        "CREATE INDEX m_spec_idx ON m_specs (fold_id, target_id, family)",
        "CREATE INDEX m_fit_idx ON m_fits (dataset_id, split_id, fold_id, spec_id, "
        "available_ns)",
        "CREATE INDEX m_prediction_idx ON m_predictions (artifact_id, target_id, "
        "origin_ns, security_id, scope)",
        "CREATE INDEX m_evaluation_idx ON m_evaluations (artifact_id, fold_id, "
        "target_id, scope, cutoff_ns)",
    ]
    for table in TABLES:
        statements.append(
            f"CREATE TRIGGER immutable_{table}_insert BEFORE INSERT ON {table} WHEN "
            f"EXISTS (SELECT 1 FROM {table} WHERE fingerprint=NEW.fingerprint) BEGIN "
            f"SELECT RAISE(ABORT, 'immutable AFRE artifact'); END"
        )
        for operation in ("UPDATE", "DELETE"):
            statements.append(
                f"CREATE TRIGGER immutable_{table}_{operation.lower()} BEFORE {operation} ON "
                f"{table} BEGIN SELECT RAISE(ABORT, 'immutable AFRE artifact'); END"
            )
    return tuple(statements)


def model_indexes(value: Artifact, identity: str) -> tuple[tuple[str, tuple[object, ...]], ...]:
    if isinstance(value, BaselineModelSpec):
        return (
            (
                "m_specs",
                (
                    identity,
                    value.family.value,
                    value.fold_id,
                    value.target.fingerprint,
                    value.feature_set.fingerprint,
                ),
            ),
        )
    if isinstance(value, ModelFitRun):
        inputs = value.inputs
        return (
            (
                "m_fits",
                (
                    identity,
                    value.artifact_id,
                    inputs.spec_id,
                    inputs.dataset_id,
                    inputs.split_id,
                    inputs.fold_id,
                    inputs.matrix_id,
                    inputs.model_available_ns,
                ),
            ),
        )
    if isinstance(value, PointForecast):
        return (
            (
                "m_predictions",
                (
                    identity,
                    value.model_artifact_id,
                    value.target_definition_id,
                    value.input.origin.instrument.fingerprint,
                    value.input.origin.timestamp_ns,
                    value.input.scope.value,
                    value.input.sample_id,
                    value.available_ns,
                ),
            ),
        )
    if isinstance(value, PointEvaluation):
        return (
            (
                "m_evaluations",
                (
                    identity,
                    value.model_artifact_id,
                    value.dataset_id,
                    value.fold_id,
                    value.target_definition_id,
                    value.scope.value,
                    value.evaluation_cutoff_ns,
                ),
            ),
        )
    return ()

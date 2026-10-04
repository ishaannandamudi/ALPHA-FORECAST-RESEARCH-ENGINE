"""Additive immutable probability tables and independently verified indexes."""

from afre.probabilistic.artifacts import (
    ProbabilisticEvaluation,
    ProbabilisticFitRun,
    ProbabilisticForecast,
)
from afre.probabilistic.definitions import ProbabilisticModelSpec
from afre.schema import Artifact

TABLES = ("p_artifacts", "p_specs", "p_fits", "p_forecasts", "p_evaluations")


def probabilistic_schema() -> tuple[str, ...]:
    statements = [
        "CREATE TABLE p_artifacts (fingerprint TEXT PRIMARY KEY NOT NULL, type_name TEXT "
        "NOT NULL, schema_version TEXT NOT NULL, payload TEXT NOT NULL)",
        "CREATE TABLE p_specs (fingerprint TEXT PRIMARY KEY NOT NULL, point_model_id "
        "TEXT NOT NULL, family TEXT NOT NULL, fold_id TEXT NOT NULL, target_id TEXT NOT "
        "NULL)",
        "CREATE TABLE p_fits (fingerprint TEXT PRIMARY KEY NOT NULL, artifact_id TEXT "
        "NOT NULL UNIQUE, spec_id TEXT NOT NULL, point_model_id TEXT NOT NULL, "
        "dataset_id TEXT NOT NULL, split_id TEXT NOT NULL, fold_id TEXT NOT NULL, "
        "target_id TEXT NOT NULL, available_ns INTEGER NOT NULL)",
        "CREATE TABLE p_forecasts (fingerprint TEXT PRIMARY KEY NOT NULL, artifact_id "
        "TEXT NOT NULL, target_id TEXT NOT NULL, security_id TEXT NOT NULL, origin_ns "
        "INTEGER NOT NULL, scope TEXT NOT NULL, available_ns INTEGER NOT NULL)",
        "CREATE TABLE p_evaluations (fingerprint TEXT PRIMARY KEY NOT NULL, artifact_id "
        "TEXT NOT NULL, dataset_id TEXT NOT NULL, fold_id TEXT NOT NULL, target_id TEXT "
        "NOT NULL, scope TEXT NOT NULL, cutoff_ns INTEGER NOT NULL)",
        "CREATE INDEX p_spec_idx ON p_specs (point_model_id, family, fold_id, target_id)",
        "CREATE INDEX p_fit_idx ON p_fits (dataset_id, split_id, fold_id, target_id, "
        "spec_id, point_model_id, available_ns)",
        "CREATE INDEX p_forecast_idx ON p_forecasts (artifact_id, target_id, origin_ns, "
        "security_id, scope)",
        "CREATE INDEX p_evaluation_idx ON p_evaluations (artifact_id, fold_id, "
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
                f"CREATE TRIGGER immutable_{table}_{operation.lower()} BEFORE "
                f"{operation} ON {table} BEGIN SELECT RAISE(ABORT, 'immutable AFRE "
                f"artifact'); END"
            )
    return tuple(statements)


def probability_indexes(
    value: Artifact, identity: str
) -> tuple[tuple[str, tuple[object, ...]], ...]:
    if isinstance(value, ProbabilisticModelSpec):
        return (
            (
                "p_specs",
                (
                    identity,
                    value.point_model_id,
                    value.family.value,
                    value.fold_id,
                    value.target.fingerprint,
                ),
            ),
        )
    if isinstance(value, ProbabilisticFitRun):
        i = value.inputs
        return (
            (
                "p_fits",
                (
                    identity,
                    value.artifact_id,
                    i.spec_id,
                    i.point_model_id,
                    i.dataset_id,
                    i.split_id,
                    i.fold_id,
                    i.target_definition_id,
                    i.available_ns,
                ),
            ),
        )
    if isinstance(value, ProbabilisticForecast):
        return (
            (
                "p_forecasts",
                (
                    identity,
                    value.model_artifact_id,
                    value.target_definition_id,
                    value.input.origin.instrument.fingerprint,
                    value.input.origin.timestamp_ns,
                    value.input.scope.value,
                    value.available_ns,
                ),
            ),
        )
    if isinstance(value, ProbabilisticEvaluation):
        return (
            (
                "p_evaluations",
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

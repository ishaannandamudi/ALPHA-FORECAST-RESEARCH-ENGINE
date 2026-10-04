"""Additive immutable calibration tables with independently checked query indexes."""

from afre.calibration.artifacts import (
    CalibratedForecast,
    CalibrationDriftDiagnostics,
    CalibrationEvaluation,
    CalibrationFitRun,
    ProbabilityMapping,
    QuantileOffset,
)
from afre.calibration.definitions import CalibrationSpec
from afre.schema import Artifact

TABLE_FAMILIES = (
    ("c_specs", "CalibrationSpec"),
    ("c_fits", "CalibrationFitRun"),
    ("c_forecasts", "CalibratedForecast"),
    ("c_evaluations", "CalibrationEvaluation"),
    ("c_mappings", "ProbabilityMapping"),
    ("c_offsets", "QuantileOffset"),
    ("c_drifts", "CalibrationDriftDiagnostics"),
)
TABLES = ("c_artifacts", *(t for t, _ in TABLE_FAMILIES))


def calibration_schema() -> tuple[str, ...]:
    statements = [
        (
            "CREATE TABLE c_artifacts (fingerprint TEXT PRIMARY KEY NOT NULL, "
            "type_name TEXT NOT NULL, schema_version TEXT NOT NULL, payload "
            "TEXT NOT NULL)"
        ),
        (
            "CREATE TABLE c_specs (fingerprint TEXT PRIMARY KEY NOT NULL, "
            "raw_model_id TEXT NOT NULL, raw_spec_id TEXT NOT NULL, target_id "
            "TEXT NOT NULL, fold_id TEXT NOT NULL, method TEXT NOT NULL, "
            "cutoff_ns INTEGER NOT NULL)"
        ),
        (
            "CREATE TABLE c_fits (fingerprint TEXT PRIMARY KEY NOT NULL, "
            "state_id TEXT NOT NULL UNIQUE, spec_id TEXT NOT NULL, "
            "raw_model_id TEXT NOT NULL, cutoff_ns INTEGER NOT NULL, "
            "available_ns INTEGER NOT NULL)"
        ),
        (
            "CREATE TABLE c_forecasts (fingerprint TEXT PRIMARY KEY NOT NULL, "
            "raw_forecast_id TEXT NOT NULL, state_id TEXT NOT NULL, target_id "
            "TEXT NOT NULL, security_id TEXT NOT NULL, origin_ns INTEGER NOT "
            "NULL, available_ns INTEGER NOT NULL)"
        ),
        (
            "CREATE TABLE c_evaluations (fingerprint TEXT PRIMARY KEY NOT "
            "NULL, state_id TEXT NOT NULL, raw_evaluation_id TEXT NOT NULL, "
            "cutoff_ns INTEGER NOT NULL)"
        ),
        (
            "CREATE TABLE c_mappings (fingerprint TEXT PRIMARY KEY NOT NULL, "
            "spec_id TEXT NOT NULL, event_id TEXT NOT NULL)"
        ),
        (
            "CREATE TABLE c_offsets (fingerprint TEXT PRIMARY KEY NOT NULL, "
            "spec_id TEXT NOT NULL, level REAL NOT NULL)"
        ),
        (
            "CREATE TABLE c_drifts (fingerprint TEXT PRIMARY KEY NOT NULL, "
            "spec_id TEXT NOT NULL, state_id TEXT NOT NULL, window_count "
            "INTEGER NOT NULL, cutoff_ns INTEGER NOT NULL)"
        ),
        (
            "CREATE INDEX c_spec_idx ON c_specs (raw_model_id, raw_spec_id, "
            "target_id, fold_id, method, cutoff_ns)"
        ),
        "CREATE INDEX c_fit_idx ON c_fits (spec_id, raw_model_id, cutoff_ns, available_ns)",
        (
            "CREATE INDEX c_forecast_idx ON c_forecasts (state_id, target_id, "
            "origin_ns, security_id, raw_forecast_id)"
        ),
        (
            "CREATE INDEX c_evaluation_idx ON c_evaluations (state_id, "
            "raw_evaluation_id, cutoff_ns)"
        ),
        "CREATE INDEX c_mapping_idx ON c_mappings (spec_id, event_id)",
        "CREATE INDEX c_offset_idx ON c_offsets (spec_id, level)",
        "CREATE INDEX c_drift_idx ON c_drifts (state_id, spec_id, window_count, cutoff_ns)",
    ]
    for table in TABLES:
        statements.append(
            f"CREATE TRIGGER immutable_{table}_insert BEFORE INSERT ON {table} "
            f"WHEN EXISTS (SELECT 1 FROM {table} WHERE "
            f"fingerprint=NEW.fingerprint) BEGIN SELECT RAISE(ABORT, "
            f"'immutable AFRE artifact'); END"
        )
        for operation in ("UPDATE", "DELETE"):
            statements.append(
                f"CREATE TRIGGER immutable_{table}_{operation.lower()} BEFORE "
                f"{operation} ON {table} BEGIN SELECT RAISE(ABORT, 'immutable AFRE "
                f"artifact'); END"
            )
    return tuple(statements)


def calibration_indexes(
    value: Artifact, identity: str
) -> tuple[tuple[str, tuple[object, ...]], ...]:
    if isinstance(value, CalibrationSpec):
        return (
            (
                "c_specs",
                (
                    identity,
                    value.raw_model_id,
                    value.raw_spec_id,
                    value.target.fingerprint,
                    value.partition.fold_id,
                    value.method.value,
                    value.cutoff_ns,
                ),
            ),
        )
    if isinstance(value, CalibrationFitRun):
        i = value.inputs
        return (
            (
                "c_fits",
                (
                    identity,
                    value.state_id,
                    i.spec_id,
                    i.raw_model_id,
                    i.cutoff_ns,
                    i.available_ns,
                ),
            ),
        )
    if isinstance(value, CalibratedForecast):
        return (
            (
                "c_forecasts",
                (
                    identity,
                    value.raw_forecast_id,
                    value.state_id,
                    value.target_definition_id,
                    value.input.origin.instrument.fingerprint,
                    value.input.origin.timestamp_ns,
                    value.available_ns,
                ),
            ),
        )
    if isinstance(value, CalibrationEvaluation):
        return (
            (
                "c_evaluations",
                (identity, value.state_id, value.raw_evaluation_id, value.cutoff_ns),
            ),
        )
    if isinstance(value, ProbabilityMapping):
        return (("c_mappings", (identity, value.spec_id, value.event.fingerprint)),)
    if isinstance(value, QuantileOffset):
        return (("c_offsets", (identity, value.spec_id, value.level)),)
    if isinstance(value, CalibrationDriftDiagnostics):
        return (
            (
                "c_drifts",
                (
                    identity,
                    value.spec.fingerprint,
                    value.state_id,
                    value.spec.window_evaluations,
                    value.windows[-1].cutoff_ns,
                ),
            ),
        )
    return ()

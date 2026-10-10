"""Additive SQLite23 health tables and immutable searchable evidence projections."""

from afre.fusion.storage import METADATA as PREVIOUS_METADATA
from afre.fusion.storage import all_statements as previous_statements
from afre.schema import Artifact

METADATA = {
    **PREVIOUS_METADATA,
    "health_store_schema_version": "1.22",
    "health_schema": "1.0",
    "health_engine_version": "0.23.0",
}


def health_schema() -> tuple[str, ...]:
    statements = [
        (
            "CREATE TABLE hlt_artifacts (fingerprint TEXT PRIMARY KEY NOT "
            "NULL, type_name TEXT NOT NULL, schema_version TEXT NOT NULL, "
            "payload TEXT NOT NULL)"
        ),
        (
            "CREATE TABLE hlt_records (fingerprint TEXT PRIMARY KEY NOT NULL, "
            "kind TEXT NOT NULL, spec_id TEXT, reference_id TEXT, target_id "
            "TEXT, horizon_id TEXT, metric_kind TEXT, status TEXT, "
            "reference_window_id TEXT, current_window_id TEXT, cutoff_ns "
            "INTEGER, available_ns INTEGER, test_evaluation_id TEXT, "
            "environment_id TEXT)"
        ),
        (
            "CREATE TABLE hlt_links (fingerprint TEXT NOT NULL, reference_id "
            "TEXT NOT NULL, PRIMARY KEY (fingerprint, reference_id))"
        ),
        "CREATE INDEX hlt_monitored_idx ON hlt_records (reference_id, spec_id)",
        "CREATE INDEX hlt_target_idx ON hlt_records (target_id, horizon_id)",
        "CREATE INDEX hlt_metric_idx ON hlt_records (metric_kind, status)",
        "CREATE INDEX hlt_window_idx ON hlt_records (reference_window_id, current_window_id)",
        "CREATE INDEX hlt_clock_idx ON hlt_records (cutoff_ns, available_ns)",
        "CREATE INDEX hlt_test_idx ON hlt_records (test_evaluation_id)",
        "CREATE INDEX hlt_cohort_idx ON hlt_records (environment_id)",
        "CREATE INDEX hlt_reference_idx ON hlt_links (reference_id, fingerprint)",
    ]
    for table in ("hlt_artifacts", "hlt_records"):
        statements.append(
            f"CREATE TRIGGER immutable_{table}_insert BEFORE INSERT ON {table} "
            f"WHEN EXISTS (SELECT 1 FROM {table} WHERE fingerprint=NEW.fingerprint) "
            "BEGIN SELECT RAISE(ABORT, 'immutable AFRE artifact'); END"
        )
    for table in ("hlt_artifacts", "hlt_records", "hlt_links"):
        for op in ("UPDATE", "DELETE"):
            statements.append(
                f"CREATE TRIGGER immutable_{table}_{op.lower()} BEFORE {op} ON {table} "
                "BEGIN SELECT RAISE(ABORT, 'immutable AFRE artifact'); END"
            )
    return tuple(statements)


def all_statements() -> tuple[str, ...]:
    return (*previous_statements(), *health_schema())


def record_index(value: Artifact) -> tuple[object, ...]:
    window_a, window_b = (
        getattr(value, "reference_window", None),
        getattr(value, "current_window", None),
    )
    kind, status = getattr(value, "kind", None), getattr(value, "status", None)
    return (
        value.fingerprint,
        type(value).__name__,
        getattr(value, "spec_id", None),
        getattr(value, "reference_id", None),
        getattr(value, "target_id", None),
        getattr(value, "horizon_id", None),
        getattr(kind, "value", None),
        getattr(status, "value", None),
        window_a.fingerprint if window_a else getattr(value, "reference_window_id", None),
        window_b.fingerprint if window_b else getattr(value, "current_window_id", None),
        getattr(value, "cutoff_ns", None),
        getattr(value, "available_ns", None),
        getattr(value, "test_evaluation_id", None),
        getattr(value, "environment_id", None),
    )

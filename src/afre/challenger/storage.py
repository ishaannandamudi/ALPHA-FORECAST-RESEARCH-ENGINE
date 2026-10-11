"""Additive SQLite24 immutable artifacts, exact links and searchable advisory projections."""

from afre.health.storage import METADATA as PREVIOUS_METADATA
from afre.health.storage import all_statements as previous_statements
from afre.schema import Artifact

METADATA = {
    **PREVIOUS_METADATA,
    "challenge_store_schema_version": "1.23",
    "challenge_schema": "1.0",
    "challenge_engine_version": "0.24.0",
}


def challenge_schema() -> tuple[str, ...]:
    statements = [
        (
            "CREATE TABLE ch_artifacts (fingerprint TEXT PRIMARY KEY NOT NULL, "
            "type_name TEXT NOT NULL, schema_version TEXT NOT NULL, payload TEXT NOT NULL)"
        ),
        (
            "CREATE TABLE ch_records (fingerprint TEXT PRIMARY KEY NOT NULL, kind TEXT "
            "NOT NULL, "
            "program_id TEXT, participant_id TEXT, target_id TEXT, horizon_id TEXT, "
            "metric_kind TEXT, status TEXT, champion_id TEXT, challenger_id TEXT, "
            "cutoff_ns INTEGER, available_ns INTEGER, test_evaluation_id TEXT, "
            "environment_id TEXT, selection_id TEXT, source_id TEXT, "
            "window_start_ns INTEGER, window_end_ns INTEGER)"
        ),
        (
            "CREATE TABLE ch_links (fingerprint TEXT NOT NULL, reference_id TEXT NOT NULL, "
            "PRIMARY KEY (fingerprint, reference_id))"
        ),
        "CREATE INDEX ch_kind_idx ON ch_records (kind, status, program_id)",
        "CREATE INDEX ch_source_idx ON ch_records (source_id, participant_id)",
        "CREATE INDEX ch_health_idx ON ch_links (reference_id)",
        "CREATE INDEX ch_program_idx ON ch_records (program_id, participant_id)",
        "CREATE INDEX ch_champion_idx ON ch_records (champion_id, challenger_id)",
        "CREATE INDEX ch_target_idx ON ch_records (target_id, horizon_id)",
        "CREATE INDEX ch_metric_idx ON ch_records (metric_kind, status)",
        (
            "CREATE INDEX ch_window_idx ON ch_records "
            "(window_start_ns, window_end_ns, cutoff_ns, available_ns)"
        ),
        "CREATE INDEX ch_test_idx ON ch_records (test_evaluation_id)",
        "CREATE INDEX ch_environment_idx ON ch_records (environment_id)",
        "CREATE INDEX ch_selection_idx ON ch_records (selection_id)",
        "CREATE INDEX ch_reference_idx ON ch_links (reference_id, fingerprint)",
    ]
    for table in ("ch_artifacts", "ch_records"):
        statements.append(
            f"CREATE TRIGGER immutable_{table}_insert BEFORE INSERT ON {table} "
            f"WHEN EXISTS (SELECT 1 FROM {table} WHERE fingerprint=NEW.fingerprint) "
            "BEGIN SELECT RAISE(ABORT, 'immutable AFRE artifact'); END"
        )
    for table in ("ch_artifacts", "ch_records", "ch_links"):
        for op in ("UPDATE", "DELETE"):
            statements.append(
                f"CREATE TRIGGER immutable_{table}_{op.lower()} BEFORE {op} ON {table} "
                "BEGIN SELECT RAISE(ABORT, 'immutable AFRE artifact'); END"
            )
    return tuple(statements)


def all_statements() -> tuple[str, ...]:
    return (*previous_statements(), *challenge_schema())


def record_index(value: Artifact) -> tuple[object, ...]:
    ref = getattr(value, "reference", None)
    kind = getattr(value, "kind", None)
    status = getattr(value, "status", getattr(value, "outcome", None))
    window = getattr(value, "window", None)
    return (
        value.fingerprint,
        type(value).__name__,
        getattr(value, "program_id", None),
        getattr(value, "participant_id", None),
        getattr(value, "target_id", getattr(ref, "target_id", None)),
        getattr(value, "horizon_id", getattr(ref, "horizon_id", None)),
        getattr(kind, "value", None),
        getattr(status, "value", None),
        getattr(value, "champion_id", None),
        getattr(value, "challenger_id", None),
        getattr(value, "cutoff_ns", getattr(window, "cutoff_ns", None)),
        getattr(value, "available_ns", None),
        getattr(value, "test_evaluation_id", None),
        getattr(value, "environment_id", None),
        getattr(value, "selection_result_id", None),
        getattr(value, "source_id", getattr(ref, "artifact_id", None)),
        getattr(window, "start_ns", None),
        getattr(window, "end_ns", None),
    )

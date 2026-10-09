"""Additive SQLite20 tables; existing AFRE metadata, rows and DDL are preserved."""

from afre.costs.storage import METADATA as PREVIOUS_METADATA
from afre.costs.storage import all_statements as previous_statements
from afre.schema import Artifact

METADATA = {
    **PREVIOUS_METADATA,
    "multiple_testing_store_schema_version": "1.19",
    "multiple_testing_schema": "1.0",
    "multiple_testing_engine_version": "0.20.0",
}


def multiple_testing_schema() -> tuple[str, ...]:
    statements = [
        (
            "CREATE TABLE mt_artifacts (fingerprint TEXT PRIMARY KEY NOT NULL, "
            "type_name TEXT NOT NULL, schema_version TEXT NOT NULL, payload TEXT "
            "NOT NULL)"
        ),
        (
            "CREATE TABLE mt_records (fingerprint TEXT PRIMARY KEY NOT NULL, "
            "kind TEXT NOT NULL, family_id TEXT, plan_id TEXT, hypothesis_id "
            "TEXT, source_id TEXT, target_id TEXT, horizon_id TEXT, dataset_id "
            "TEXT, fold_id TEXT, metric TEXT, declared_ns INTEGER, cutoff_ns "
            "INTEGER, available_ns INTEGER, selection_id TEXT)"
        ),
        (
            "CREATE TABLE mt_links (fingerprint TEXT NOT NULL, reference_id TEXT "
            "NOT NULL, PRIMARY KEY (fingerprint, reference_id))"
        ),
        (
            "CREATE TABLE mt_test_uses (fingerprint TEXT NOT NULL, seal_id TEXT "
            "NOT NULL, PRIMARY KEY (fingerprint, seal_id))"
        ),
        "CREATE INDEX mt_family_idx ON mt_records (family_id, hypothesis_id, plan_id)",
        (
            "CREATE UNIQUE INDEX mt_trial_attempt_idx ON mt_records (plan_id) "
            "WHERE kind='ResearchTrial'"
        ),
        "CREATE INDEX mt_source_idx ON mt_records (source_id, kind)",
        "CREATE INDEX mt_target_idx ON mt_records (target_id, horizon_id, dataset_id, fold_id)",
        "CREATE INDEX mt_metric_idx ON mt_records (metric, family_id)",
        "CREATE INDEX mt_time_idx ON mt_records (kind, declared_ns, cutoff_ns, available_ns)",
        "CREATE INDEX mt_selection_idx ON mt_records (selection_id, family_id)",
        "CREATE INDEX mt_reference_idx ON mt_links (reference_id, fingerprint)",
        "CREATE INDEX mt_test_idx ON mt_test_uses (seal_id, fingerprint)",
    ]
    for table in ("mt_artifacts", "mt_records"):
        statements.append(
            f"CREATE TRIGGER immutable_{table}_insert BEFORE INSERT ON {table} "
            f"WHEN EXISTS (SELECT 1 FROM {table} WHERE "
            f"fingerprint=NEW.fingerprint) BEGIN SELECT RAISE(ABORT, 'immutable "
            f"AFRE artifact'); END"
        )
    for table in ("mt_artifacts", "mt_records", "mt_links", "mt_test_uses"):
        for operation in ("UPDATE", "DELETE"):
            statements.append(
                f"CREATE TRIGGER immutable_{table}_{operation.lower()} BEFORE "
                f"{operation} ON {table} BEGIN SELECT RAISE(ABORT, 'immutable AFRE "
                f"artifact'); END"
            )
    return tuple(statements)


def all_statements() -> tuple[str, ...]:
    return (*previous_statements(), *multiple_testing_schema())


def record_index(v: Artifact) -> tuple[object, ...]:
    metric = getattr(v, "metric", None)
    return (
        v.fingerprint,
        type(v).__name__,
        getattr(v, "family_id", None),
        getattr(v, "plan_id", None),
        getattr(v, "hypothesis_id", None),
        getattr(v, "source_artifact_id", None),
        getattr(v, "target_id", None),
        getattr(v, "horizon_id", None),
        getattr(v, "dataset_id", None),
        getattr(v, "fold_id", None),
        getattr(metric, "value", metric),
        getattr(v, "declared_ns", None),
        getattr(
            v,
            "evaluation_cutoff_ns",
            getattr(v, "cutoff_ns", getattr(v, "completion_cutoff_ns", None)),
        ),
        getattr(v, "completed_ns", getattr(v, "available_ns", getattr(v, "declared_ns", None))),
        getattr(v, "event_id", None),
    )

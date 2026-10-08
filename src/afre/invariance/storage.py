"""Additive SQLite18 objects preserving every prior DDL, row and metadata value."""

from afre.invariance.artifacts import EnvironmentMembership, EnvironmentMetric
from afre.invariance.definitions import EnvironmentDefinition, StabilityAnalysisSpec
from afre.orthogonalization.storage import METADATA as PREVIOUS_METADATA
from afre.orthogonalization.storage import all_statements as previous_statements
from afre.schema import Artifact

METADATA = {
    **PREVIOUS_METADATA,
    "invariance_store_schema_version": "1.17",
    "invariance_schema": "1.0",
    "invariance_engine_version": "0.18.0",
}


def invariance_schema() -> tuple[str, ...]:
    statements = [
        (
            "CREATE TABLE inv_artifacts (fingerprint TEXT PRIMARY KEY NOT NULL, "
            "type_name TEXT NOT NULL, schema_version TEXT NOT NULL, payload TEXT "
            "NOT NULL)"
        ),
        (
            "CREATE TABLE inv_records (fingerprint TEXT PRIMARY KEY NOT NULL, "
            "environment_id TEXT, kind TEXT, artifact_id TEXT, metric TEXT, "
            "target_id TEXT, horizon_id TEXT, security_id TEXT, origin_ns INTEGER, "
            "window_start_ns INTEGER, window_end_ns INTEGER, cohort_id TEXT, "
            "fold_id TEXT, cutoff_ns INTEGER, available_ns INTEGER, test_id TEXT)"
        ),
        (
            "CREATE TABLE inv_links (fingerprint TEXT NOT NULL, reference_id TEXT "
            "NOT NULL, PRIMARY KEY (fingerprint, reference_id))"
        ),
        "CREATE INDEX inv_environment_idx ON inv_records (environment_id, kind)",
        "CREATE INDEX inv_artifact_idx ON inv_records (artifact_id, metric)",
        "CREATE INDEX inv_target_idx ON inv_records (target_id, horizon_id)",
        "CREATE INDEX inv_origin_idx ON inv_records (security_id, origin_ns)",
        "CREATE INDEX inv_window_idx ON inv_records (window_start_ns, window_end_ns)",
        "CREATE INDEX inv_cohort_idx ON inv_records (cohort_id, environment_id)",
        "CREATE INDEX inv_evaluation_idx ON inv_records (fold_id, cutoff_ns, test_id)",
        "CREATE INDEX inv_reference_idx ON inv_links (reference_id, fingerprint)",
    ]
    for table in ("inv_artifacts", "inv_records"):
        statements.append(
            f"CREATE TRIGGER immutable_{table}_insert BEFORE INSERT ON {table} "
            f"WHEN EXISTS (SELECT 1 FROM {table} WHERE "
            f"fingerprint=NEW.fingerprint) BEGIN SELECT RAISE(ABORT, 'immutable "
            f"AFRE artifact'); END"
        )
    for table in ("inv_artifacts", "inv_records", "inv_links"):
        for operation in ("UPDATE", "DELETE"):
            statements.append(
                f"CREATE TRIGGER immutable_{table}_{operation.lower()} BEFORE "
                f"{operation} ON {table} BEGIN SELECT RAISE(ABORT, 'immutable "
                f"AFRE artifact'); END"
            )
    return tuple(statements)


def all_statements() -> tuple[str, ...]:
    return (*previous_statements(), *invariance_schema())


def invariance_index(v: Artifact) -> tuple[object, ...]:
    env = kind = artifact = metric = target = horizon = security = origin = start = end = (
        cohort
    ) = fold = cutoff = available = test = None
    if isinstance(v, EnvironmentDefinition):
        env, kind, target, horizon = (
            v.environment_id,
            v.kind.value,
            v.target.fingerprint,
            v.target.horizon.fingerprint,
        )
        start, end = (v.window.start_ns, v.window.end_ns) if v.window else (None, None)
        cohort = v.taxonomy_id or v.group_id or v.universe_definition_id or v.neutral_label
    elif isinstance(v, StabilityAnalysisSpec):
        target, horizon, fold = v.target.fingerprint, v.target.horizon.fingerprint, v.fold_id
    elif isinstance(v, EnvironmentMembership):
        env, artifact, security, origin, available = (
            v.environment_id,
            v.selected_ids[0] if v.selected_ids else None,
            v.origin.instrument.fingerprint,
            v.origin.timestamp_ns,
            v.available_ns,
        )
    elif isinstance(v, EnvironmentMetric):
        env, artifact, metric, target, horizon, cutoff, available, test = (
            v.environment_id,
            v.producer_ids[0],
            v.name.value,
            v.target_id,
            v.horizon_id,
            v.truth_cutoff_ns,
            v.available_ns,
            v.test_evaluation_id,
        )
    else:
        env = getattr(v, "environment_id", None)
        artifact = getattr(v, "feature_reference_id", None)
        cutoff = getattr(v, "cutoff_ns", None)
        available = getattr(v, "available_ns", None)
    return (
        v.fingerprint,
        env,
        kind,
        artifact,
        metric,
        target,
        horizon,
        security,
        origin,
        start,
        end,
        cohort,
        fold,
        cutoff,
        available,
        test,
    )

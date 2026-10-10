"""Additive SQLite22 DDL and searchable immutable fusion projections."""

from afre.schema import Artifact
from afre.selection.storage import METADATA as PREVIOUS_METADATA
from afre.selection.storage import all_statements as previous_statements

METADATA = {
    **PREVIOUS_METADATA,
    "fusion_store_schema_version": "1.21",
    "fusion_schema": "1.0",
    "fusion_engine_version": "0.22.0",
}


def fusion_schema() -> tuple[str, ...]:
    statements = [
        "CREATE TABLE fus_artifacts (fingerprint TEXT PRIMARY KEY NOT NULL, "
        "type_name TEXT NOT NULL, schema_version TEXT NOT NULL, payload "
        "TEXT NOT NULL)",
        "CREATE TABLE fus_records (fingerprint TEXT PRIMARY KEY NOT NULL, "
        "kind TEXT NOT NULL, spec_id TEXT, artifact_id TEXT, source_id "
        "TEXT, sample_id TEXT, security_id TEXT, origin_ns INTEGER, "
        "target_id TEXT, horizon_id TEXT, family TEXT, fit_cutoff_ns "
        "INTEGER, available_ns INTEGER, trial_id TEXT, selection_id TEXT)",
        "CREATE TABLE fus_links (fingerprint TEXT NOT NULL, reference_id "
        "TEXT NOT NULL, PRIMARY KEY (fingerprint, reference_id))",
        "CREATE INDEX fus_spec_idx ON fus_records (spec_id, artifact_id)",
        "CREATE INDEX fus_source_idx ON fus_records (source_id, sample_id)",
        "CREATE INDEX fus_origin_idx ON fus_records (security_id, origin_ns)",
        "CREATE INDEX fus_context_idx ON fus_records (target_id, horizon_id, family)",
        "CREATE INDEX fus_clock_idx ON fus_records (fit_cutoff_ns, available_ns)",
        "CREATE INDEX fus_trial_idx ON fus_records (trial_id, selection_id)",
        "CREATE INDEX fus_reference_idx ON fus_links (reference_id, fingerprint)",
    ]
    for table in ("fus_artifacts", "fus_records"):
        statements.append(
            f"CREATE TRIGGER immutable_{table}_insert BEFORE INSERT ON {table} "
            f"WHEN EXISTS (SELECT 1 FROM {table} WHERE "
            "fingerprint=NEW.fingerprint) BEGIN SELECT RAISE(ABORT, 'immutable "
            "AFRE artifact'); END"
        )
    for table in ("fus_artifacts", "fus_records", "fus_links"):
        for op in ("UPDATE", "DELETE"):
            statements.append(
                f"CREATE TRIGGER immutable_{table}_{op.lower()} BEFORE {op} ON "
                f"{table} BEGIN SELECT RAISE(ABORT, 'immutable AFRE artifact'); END"
            )
    return tuple(statements)


def all_statements() -> tuple[str, ...]:
    return (*previous_statements(), *fusion_schema())


def record_index(v: Artifact) -> tuple[object, ...]:
    security, origin, family = (
        getattr(v, "security", None),
        getattr(v, "origin", None),
        getattr(v, "family", None),
    )
    return (
        v.fingerprint,
        type(v).__name__,
        getattr(v, "spec_id", None),
        getattr(v, "artifact_id", None),
        getattr(v, "source_id", None),
        getattr(v, "sample_id", None),
        security.instrument.fingerprint if security else None,
        origin.timestamp_ns if origin else None,
        getattr(v, "target_id", None),
        getattr(v, "horizon_id", None),
        getattr(family, "value", family),
        getattr(v, "fit_cutoff_ns", None),
        getattr(v, "available_ns", None),
        getattr(v, "trial_pool_id", getattr(v, "family_id", None)),
        getattr(v, "source_selection_result_id", None),
    )

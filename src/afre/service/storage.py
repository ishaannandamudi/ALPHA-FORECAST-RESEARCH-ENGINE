"""Additive SQLite25 immutable payloads, exact projections and reference links."""

from afre.challenger.storage import METADATA as PREVIOUS_METADATA
from afre.challenger.storage import all_statements as previous_statements
from afre.schema import Artifact
from afre.service.queries import PublicationCatalog
from afre.service.registry_entries import RegistryEntry
from afre.service.snapshots import ForecastSnapshot

METADATA = {
    **PREVIOUS_METADATA,
    "service_store_schema_version": "1.24",
    "forecast_service_schema": "1.0",
    "forecast_snapshot_schema": "1.0",
    "registry_schema": "1.0",
    "service_api_version": "1.0",
    "service_engine_version": "0.25.0",
}


def service_schema() -> tuple[str, ...]:
    statements = [
        "CREATE TABLE svc_artifacts (fingerprint TEXT PRIMARY KEY NOT NULL, type_name TEXT "
        "NOT NULL, schema_version TEXT NOT NULL, payload TEXT NOT NULL)",
        "CREATE TABLE svc_records (fingerprint TEXT PRIMARY KEY NOT NULL, kind TEXT NOT NULL, "
        "artifact_id TEXT, producer_id TEXT, target_id TEXT, horizon_id TEXT, origin_id TEXT, "
        "universe_id TEXT, available_ns INTEGER, published_ns INTEGER)",
        "CREATE TABLE svc_links (fingerprint TEXT NOT NULL, reference_id TEXT NOT NULL, "
        "PRIMARY KEY (fingerprint, reference_id))",
        "CREATE INDEX svc_origin_idx ON svc_records (origin_id, producer_id, "
        "target_id, horizon_id)",
        "CREATE INDEX svc_registry_idx ON svc_records (artifact_id, "
        "producer_id, target_id, horizon_id)",
        "CREATE INDEX svc_available_idx ON svc_records (available_ns, published_ns)",
        "CREATE INDEX svc_reference_idx ON svc_links (reference_id, fingerprint)",
    ]
    for table in ("svc_artifacts", "svc_records"):
        statements.append(
            f"CREATE TRIGGER immutable_{table}_insert BEFORE INSERT ON {table} "
            f"WHEN EXISTS (SELECT 1 FROM {table} WHERE fingerprint=NEW.fingerprint) "
            "BEGIN SELECT RAISE(ABORT, 'immutable AFRE artifact'); END"
        )
    for table in ("svc_artifacts", "svc_records", "svc_links"):
        for op in ("UPDATE", "DELETE"):
            statements.append(
                f"CREATE TRIGGER immutable_{table}_{op.lower()} BEFORE {op} ON {table} "
                "BEGIN SELECT RAISE(ABORT, 'immutable AFRE artifact'); END"
            )
    return tuple(statements)


def all_statements() -> tuple[str, ...]:
    return (*previous_statements(), *service_schema())


def record_index(value: Artifact) -> tuple[object, ...]:
    snapshot = value if isinstance(value, ForecastSnapshot) else None
    return (
        value.fingerprint,
        type(value).__name__,
        getattr(value, "artifact_id", None),
        getattr(value, "producer_id", None),
        snapshot.target.fingerprint if snapshot else getattr(value, "target_id", None),
        snapshot.target.horizon.fingerprint if snapshot else getattr(value, "horizon_id", None),
        snapshot.origin.fingerprint if snapshot else None,
        snapshot.universe_id if snapshot else None,
        snapshot.final_available_ns if snapshot else getattr(value, "available_ns", None),
        snapshot.publication.published_ns if snapshot else getattr(value, "as_of_ns", None),
    )


def links(value: Artifact) -> tuple[str, ...]:
    if isinstance(value, RegistryEntry):
        return tuple(
            sorted({value.artifact_id, value.producer_id, value.target_id, value.horizon_id})
        )
    if isinstance(value, ForecastSnapshot):
        return tuple(
            sorted(
                {
                    *value.source_ids,
                    *value.model_ids,
                    *value.registry_entry_ids,
                    value.universe_id,
                    value.target.fingerprint,
                    *(c.artifact_id for c in value.contexts),
                }
            )
        )
    if isinstance(value, PublicationCatalog):
        return tuple(sorted((*value.entry_ids, *value.snapshot_ids)))
    return ()

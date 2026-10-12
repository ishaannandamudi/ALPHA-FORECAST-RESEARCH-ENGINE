"""Re-derive semantic projections, not just hashes, before publication or reuse."""

from typing import TYPE_CHECKING

from afre.schema import Artifact, require
from afre.service.audit import SnapshotAudit, audit_for
from afre.service.queries import PublicationCatalog
from afre.service.registry import registration_for
from afre.service.registry_entries import RegistryEntry
from afre.service.snapshot_builder import build_snapshot
from afre.service.snapshots import ForecastSnapshot

if TYPE_CHECKING:
    from afre.service.repository import ServiceRepository


def validate_service(repo: "ServiceRepository", value: Artifact) -> None:
    b = repo.service_bounds
    if isinstance(value, RegistryEntry):
        require(
            value
            == registration_for(
                repo,
                value.artifact_id,
                value.producer_id,
                value.target_id,
                value.horizon_id,
                value.anchor_source_id,
            ),
            "registry semantic corruption",
        )
    elif isinstance(value, ForecastSnapshot):
        expected, entries = build_snapshot(
            repo, value.publication, engine_version=value.engine_version
        )
        require(value == expected, "snapshot semantic corruption")
        require(
            all(repo.get(RegistryEntry, e.fingerprint) == e for e in entries),
            "snapshot registry contributor corruption",
        )
    elif isinstance(value, PublicationCatalog):
        require(
            len(value.entry_ids) <= b.registry_entries
            and len(value.snapshot_ids) <= b.registry_entries,
            "catalog registry bound",
        )
        for identity in value.entry_ids:
            entry = repo.resolve(RegistryEntry, identity)
            require(entry.available_ns <= value.as_of_ns, "catalog entry as-of availability")
            if entry.artifact_type == "ForecastSnapshot":
                repo.resolve(ForecastSnapshot, entry.artifact_id)
        for identity in value.snapshot_ids:
            snapshot = repo.resolve(ForecastSnapshot, identity)
            require(
                snapshot.publication.published_ns <= value.as_of_ns,
                "catalog snapshot as-of publication",
            )
            entry = registration_for(
                repo,
                snapshot.fingerprint,
                snapshot.producer_id,
                snapshot.target.fingerprint,
                snapshot.target.horizon.fingerprint,
            )
            require(
                entry.fingerprint in value.entry_ids
                and set(snapshot.registry_entry_ids).issubset(value.entry_ids),
                "catalog exact snapshot/model registry links",
            )
    elif isinstance(value, SnapshotAudit):
        snapshot = repo.resolve(ForecastSnapshot, value.snapshot.fingerprint)
        entry = repo.resolve(RegistryEntry, value.snapshot_registry_entry.fingerprint)
        require(value == audit_for(snapshot, entry), "audit semantic corruption")

"""Explicit publication API separate from the consumer's read-only façade."""

from afre.service.audit import SnapshotAudit, audit_for
from afre.service.queries import PublicationCatalog, SnapshotPublication
from afre.service.registry import registration_for
from afre.service.repository import ServiceRepository
from afre.service.snapshot_builder import build_snapshot
from afre.service.snapshots import ForecastSnapshot


class SnapshotPublisher:
    def __init__(self, repository: ServiceRepository) -> None:
        self.repository = repository

    def publish(self, request: SnapshotPublication) -> ForecastSnapshot:
        repo = self.repository
        with repo.request():
            snapshot, entries = build_snapshot(repo, request)
        with repo.transaction(), repo.request():
            for entry in entries:
                repo.put(entry)
            repo.put(snapshot)
            entry = registration_for(
                repo,
                snapshot.fingerprint,
                snapshot.producer_id,
                snapshot.target.fingerprint,
                snapshot.target.horizon.fingerprint,
            )
            repo.put(entry)
        return snapshot

    def catalog(
        self,
        name: str,
        snapshot_ids: tuple[str, ...],
        as_of_ns: int,
        entry_ids: tuple[str, ...] = (),
    ) -> PublicationCatalog:
        repo = self.repository
        with repo.request():
            snapshots = tuple(repo.resolve(ForecastSnapshot, i) for i in snapshot_ids)
            references = set(entry_ids)
            for snapshot in snapshots:
                references.update(snapshot.registry_entry_ids)
                references.add(
                    registration_for(
                        repo,
                        snapshot.fingerprint,
                        snapshot.producer_id,
                        snapshot.target.fingerprint,
                        snapshot.target.horizon.fingerprint,
                    ).fingerprint
                )
            catalog = PublicationCatalog(name, tuple(references), snapshot_ids, as_of_ns)
        with repo.transaction():
            repo.put(catalog)
        return catalog

    def audit(self, snapshot_id: str) -> SnapshotAudit:
        repo = self.repository
        with repo.request():
            snapshot = repo.resolve(ForecastSnapshot, snapshot_id)
            entry = registration_for(
                repo,
                snapshot_id,
                snapshot.producer_id,
                snapshot.target.fingerprint,
                snapshot.target.horizon.fingerprint,
            )
            audit = audit_for(snapshot, repo.resolve(type(entry), entry.fingerprint))
        with repo.transaction():
            repo.put(audit)
        return audit

"""In-process read-only provider-neutral façade with stable public error responses."""

import sqlite3
from collections.abc import Callable
from typing import Protocol

from afre.ids import validate_fingerprint
from afre.schema import ContractError, require
from afre.serialization import canonical_json
from afre.service.audit import SnapshotAudit
from afre.service.context import SnapshotContext
from afre.service.queries import (
    PublicationCatalog,
    RegistryCursor,
    RegistryQuery,
    SnapshotQuery,
)
from afre.service.registry import registration_for
from afre.service.registry_entries import RegistryEntry
from afre.service.repository import ServiceRepository
from afre.service.responses import RegistryPage, ServiceReply
from afre.service.schema import ServiceContextKind, ServiceStatus, SnapshotBundleStatus
from afre.service.snapshots import ForecastSnapshot, MultiHorizonSnapshot
from afre.service.versions import CAPABILITIES, VersionInfo, version_info

Payload = (
    ForecastSnapshot
    | MultiHorizonSnapshot
    | RegistryEntry
    | RegistryPage
    | SnapshotContext
    | VersionInfo
    | SnapshotAudit
    | PublicationCatalog
)


class ForecastServiceProvider(Protocol):
    def get_snapshot(
        self, snapshot_id: str, capabilities: tuple[str, ...] = ()
    ) -> ServiceReply: ...
    def get_snapshot_for_origin(self, query: SnapshotQuery) -> ServiceReply: ...
    def get_multi_horizon_snapshot(
        self, queries: tuple[SnapshotQuery, ...]
    ) -> ServiceReply: ...
    def get_registry_entry(self, entry_id: str) -> ServiceReply: ...
    def get_registry_entry_for_artifact(self, query: RegistryQuery) -> ServiceReply: ...
    def list_registry_entries(
        self, query: RegistryQuery, cursor: RegistryCursor | None = None
    ) -> ServiceReply: ...
    def get_health_metadata(self, snapshot_id: str, artifact_id: str) -> ServiceReply: ...
    def get_challenge_metadata(self, snapshot_id: str, artifact_id: str) -> ServiceReply: ...
    def get_version_info(self) -> ServiceReply: ...
    def get_capability_catalog(self) -> ServiceReply: ...
    def get_audit(self, audit_id: str) -> ServiceReply: ...


class ForecastResearchService:
    def __init__(self, repository: ServiceRepository) -> None:
        self._repository = repository

    def _reply(self, operation: Callable[[], Payload]) -> ServiceReply:
        try:
            with self._repository.request():
                self._repository._validate_layout()
                value = operation()
                require(
                    len(canonical_json(value).encode())
                    <= self._repository.service_bounds.payload_bytes,
                    "BOUNDS_EXCEEDED: public response payload",
                )
            return ServiceReply(ServiceStatus.AVAILABLE, value, "Exact immutable research data")
        except KeyError:
            status = ServiceStatus.NOT_FOUND
        except ContractError as error:
            message = str(error)
            status = ServiceStatus.CORRUPT_ARTIFACT
            for candidate in ServiceStatus:
                if message.startswith(candidate.value + ":"):
                    status = candidate
                    break
            else:
                if "bound" in message:
                    status = ServiceStatus.BOUNDS_EXCEEDED
        except (sqlite3.Error, TypeError, AttributeError):
            status = ServiceStatus.CORRUPT_ARTIFACT
        return ServiceReply(
            status, None, "Request did not produce compatible immutable research data"
        )

    @staticmethod
    def _identity(identity: str, domain: str | None) -> str:
        require(type(identity) is str, "INVALID_REQUEST: exact service identity type")
        try:
            validate_fingerprint(identity, domain)
        except ContractError:
            require(False, "INVALID_REQUEST: exact service identity")
        return identity

    def _snapshot(self, identity: str, capabilities: tuple[str, ...] = ()) -> ForecastSnapshot:
        self._identity(identity, "svc_snapshot")
        require(type(capabilities) is tuple, "INVALID_REQUEST: capability tuple")
        require(len(capabilities) <= len(CAPABILITIES), "BOUNDS_EXCEEDED: capabilities")
        require(
            all(c in CAPABILITIES for c in capabilities), "UNAVAILABLE: requested capability"
        )
        snapshot = self._repository.resolve(ForecastSnapshot, identity)
        expected_entry = registration_for(
            self._repository,
            identity,
            snapshot.producer_id,
            snapshot.target.fingerprint,
            snapshot.target.horizon.fingerprint,
        )
        try:
            actual_entry = self._repository.get(RegistryEntry, expected_entry.fingerprint)
        except KeyError:
            require(False, "snapshot registry linkage corruption")
        else:
            require(actual_entry == expected_entry, "snapshot registry entry corruption")
        actual = {"POINT"} if snapshot.output.point is not None else set()
        law = snapshot.output.probability
        if law:
            actual.add(
                {
                    "GAUSSIAN": "PROBABILISTIC_GAUSSIAN",
                    "EMPIRICAL": "PROBABILISTIC_EMPIRICAL",
                    "MIXTURE": "PROBABILISTIC_MIXTURE",
                    "QUANTILES": "QUANTILE_ONLY",
                }[law.kind]
            )
        if snapshot.output.quantiles and not law:
            actual.add("QUANTILE_ONLY")
        if snapshot.output.calibration.state == "CALIBRATED":
            actual.add("CALIBRATION")
        mapping = {
            ServiceContextKind.RANKING: "RANKING",
            ServiceContextKind.EVENT: "EVENT_CONTEXT",
            ServiceContextKind.REGIME: "REGIME_CONTEXT",
            ServiceContextKind.UNCERTAINTY: "UNCERTAINTY",
            ServiceContextKind.ORTHOGONAL: "ORTHOGONAL_CONTEXT",
            ServiceContextKind.FUSION: "FUSION",
            ServiceContextKind.HEALTH: "HEALTH",
            ServiceContextKind.CHALLENGE: "CHALLENGE_METADATA",
        }
        actual.update(mapping[c.kind] for c in snapshot.contexts)
        require(set(capabilities).issubset(actual), "UNAVAILABLE: absent snapshot capability")
        return snapshot

    def get_snapshot(
        self, snapshot_id: str, capabilities: tuple[str, ...] = ()
    ) -> ServiceReply:
        return self._reply(lambda: self._snapshot(snapshot_id, capabilities))

    def _origin(self, query: SnapshotQuery) -> ForecastSnapshot:
        require(type(query) is SnapshotQuery, "INVALID_REQUEST: snapshot selector type")
        require(query.api_version == "1.0", "VERSION_MISMATCH: snapshot query API")
        catalog = self._repository.resolve(PublicationCatalog, query.catalog_id)
        require(query.as_of_ns <= catalog.as_of_ns, "INCOMPATIBLE: query as-of outside catalog")
        values = []
        for identity in catalog.snapshot_ids:
            snapshot = self._snapshot(identity)
            if (
                snapshot.producer_id,
                snapshot.target.fingerprint,
                snapshot.target.horizon.fingerprint,
                snapshot.origin,
                snapshot.universe_id,
            ) == (
                query.producer_id,
                query.target_id,
                query.horizon_id,
                query.origin,
                query.universe_id,
            ) and snapshot.publication.published_ns <= query.as_of_ns:
                values.append(snapshot)
        require(bool(values), "NOT_FOUND: exact origin selector")
        require(len(values) == 1, "INCOMPATIBLE: ambiguous EXACT_ONE_V1 selector")
        return values[0]

    def get_snapshot_for_origin(self, query: SnapshotQuery) -> ServiceReply:
        return self._reply(lambda: self._origin(query))

    def get_multi_horizon_snapshot(self, queries: tuple[SnapshotQuery, ...]) -> ServiceReply:
        def operation() -> MultiHorizonSnapshot:
            require(
                type(queries) is tuple
                and 0 < len(queries) <= self._repository.service_bounds.horizons
                and all(type(q) is SnapshotQuery for q in queries),
                "INVALID_REQUEST: bounded horizon selectors",
            )
            require(
                len({q.horizon_id for q in queries}) == len(queries),
                "INVALID_REQUEST: duplicate horizon",
            )
            require(
                len({(q.origin, q.universe_id, q.as_of_ns, q.catalog_id) for q in queries})
                == 1,
                "INCOMPATIBLE: multi-horizon query origin/catalog",
            )
            snapshots, missing = [], []
            for q in sorted(queries, key=lambda q: q.horizon_id):
                try:
                    snapshots.append(self._origin(q))
                except ContractError as error:
                    if str(error).startswith("NOT_FOUND:"):
                        missing.append((q.horizon_id, "NOT_FOUND"))
                    else:
                        raise
            status = (
                SnapshotBundleStatus.COMPLETE
                if not missing
                else (
                    SnapshotBundleStatus.PARTIAL
                    if snapshots
                    else SnapshotBundleStatus.UNAVAILABLE
                )
            )
            return MultiHorizonSnapshot(
                tuple(q.horizon_id for q in queries), tuple(snapshots), tuple(missing), status
            )

        return self._reply(operation)

    def _entry(self, identity: str) -> RegistryEntry:
        entry = self._repository.resolve(
            RegistryEntry, self._identity(identity, "svc_registry_entry")
        )
        if entry.artifact_type == "ForecastSnapshot":
            self._snapshot(entry.artifact_id)
        return entry

    def get_registry_entry(self, entry_id: str) -> ServiceReply:
        return self._reply(lambda: self._entry(entry_id))

    def list_registry_entries(
        self, query: RegistryQuery, cursor: RegistryCursor | None = None
    ) -> ServiceReply:
        def operation() -> RegistryPage:
            require(type(query) is RegistryQuery, "INVALID_REQUEST: registry query")
            require(query.api_version == "1.0", "VERSION_MISMATCH: registry API")
            require(
                query.page_size <= self._repository.service_bounds.page_size,
                "BOUNDS_EXCEEDED: registry page size",
            )
            catalog = self._repository.resolve(PublicationCatalog, query.catalog_id)
            entries = tuple(self._entry(i) for i in catalog.entry_ids)
            entries = tuple(
                e
                for e in entries
                if all(
                    v is None or getattr(e, k) == v
                    for k, v in (
                        ("artifact_id", query.artifact_id),
                        ("producer_id", query.producer_id),
                        ("target_id", query.target_id),
                        ("horizon_id", query.horizon_id),
                    )
                )
            )
            if cursor is not None:
                require(
                    type(cursor) is RegistryCursor
                    and cursor.query_id == query.fingerprint
                    and cursor.after_entry_id in {e.fingerprint for e in entries},
                    "INVALID_REQUEST: cursor exact frozen query",
                )
                entries = tuple(e for e in entries if e.fingerprint > cursor.after_entry_id)
            page = entries[: query.page_size]
            next_cursor = (
                RegistryCursor(query.fingerprint, page[-1].fingerprint)
                if len(entries) > query.page_size
                else None
            )
            return RegistryPage(catalog.fingerprint, query.fingerprint, page, next_cursor)

        return self._reply(operation)

    def get_registry_entry_for_artifact(self, query: RegistryQuery) -> ServiceReply:
        def operation() -> RegistryEntry:
            require(type(query) is RegistryQuery, "INVALID_REQUEST: registry query")
            require(
                query.artifact_id is not None, "INVALID_REQUEST: exact registry artifact ID"
            )
            reply = self.list_registry_entries(query)
            require(
                reply.status is ServiceStatus.AVAILABLE, reply.status.value + ": registry query"
            )
            assert isinstance(reply.value, RegistryPage)
            require(bool(reply.value.entries), "NOT_FOUND: registry artifact")
            require(
                len(reply.value.entries) == 1 and reply.value.next_cursor is None,
                "INCOMPATIBLE: ambiguous registry artifact query",
            )
            return reply.value.entries[0]

        return self._reply(operation)

    def _context(
        self, snapshot_id: str, artifact_id: str, kind: ServiceContextKind
    ) -> SnapshotContext:
        self._identity(artifact_id, None)
        snapshot = self._snapshot(snapshot_id)
        context = next(
            (c for c in snapshot.contexts if c.kind is kind and c.artifact_id == artifact_id),
            None,
        )
        require(context is not None, "UNAVAILABLE: context not pinned into snapshot")
        assert context is not None
        return context

    def get_health_metadata(self, snapshot_id: str, artifact_id: str) -> ServiceReply:
        return self._reply(
            lambda: self._context(snapshot_id, artifact_id, ServiceContextKind.HEALTH)
        )

    def get_challenge_metadata(self, snapshot_id: str, artifact_id: str) -> ServiceReply:
        return self._reply(
            lambda: self._context(snapshot_id, artifact_id, ServiceContextKind.CHALLENGE)
        )

    def get_audit(self, audit_id: str) -> ServiceReply:
        return self._reply(
            lambda: self._repository.resolve(
                SnapshotAudit, self._identity(audit_id, "svc_audit")
            )
        )

    def get_version_info(self) -> ServiceReply:
        return self._reply(version_info)

    def get_capability_catalog(self) -> ServiceReply:
        return self.get_version_info()


AFREService = ForecastResearchService

"""Safe typed responses and deterministic registry pages."""

from dataclasses import dataclass

from afre.schema import Artifact, contract, require
from afre.service.audit import SnapshotAudit
from afre.service.context import SnapshotContext
from afre.service.queries import PublicationCatalog, RegistryCursor
from afre.service.registry_entries import RegistryEntry
from afre.service.schema import ServiceStatus
from afre.service.snapshots import ForecastSnapshot, MultiHorizonSnapshot
from afre.service.versions import VersionInfo


@contract("svc_registry_page")
@dataclass(frozen=True, slots=True)
class RegistryPage(Artifact):
    catalog_id: str
    query_id: str
    entries: tuple[RegistryEntry, ...]
    next_cursor: RegistryCursor | None

    def _normalize(self) -> None:
        self.ordered("entries", "fingerprint")

    def _validate(self) -> None:
        require(len(self.entries) <= 100, "registry page bound")


@contract("svc_reply")
@dataclass(frozen=True, slots=True)
class ServiceReply(Artifact):
    status: ServiceStatus
    value: (
        ForecastSnapshot
        | MultiHorizonSnapshot
        | RegistryEntry
        | RegistryPage
        | SnapshotContext
        | VersionInfo
        | SnapshotAudit
        | PublicationCatalog
        | None
    )
    message: str
    api_version: str = "1.0"
    service_schema: str = "1.0"
    engine_version: str = "0.25.0"
    store_version: str = "1.24"
    sqlite_user_version: int = 25
    snapshot_schema: str = "1.0"
    registry_schema: str = "1.0"

    def _validate(self) -> None:
        require(
            (self.status is ServiceStatus.AVAILABLE) == (self.value is not None)
            and self.api_version
            == self.service_schema
            == self.snapshot_schema
            == self.registry_schema
            == "1.0"
            and self.engine_version == "0.25.0"
            and self.store_version == "1.24"
            and self.sqlite_user_version == 25,
            "public response boundary",
        )

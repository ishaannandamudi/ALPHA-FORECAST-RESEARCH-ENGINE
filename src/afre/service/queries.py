"""Explicit frozen catalogs and immutable selectors; no hidden latest policy."""

from dataclasses import dataclass

from afre.forecast import ForecastOrigin
from afre.ids import validate_fingerprint
from afre.schema import Artifact, contract, require
from afre.service.bounds import ids
from afre.service.context import ContextRequest


@contract("svc_publication")
@dataclass(frozen=True, slots=True)
class SnapshotPublication(Artifact):
    source_id: str
    publication_version: str
    published_ns: int
    contexts: tuple[ContextRequest, ...] = ()

    def _normalize(self) -> None:
        self.ordered("contexts", "fingerprint")

    def _validate(self) -> None:
        validate_fingerprint(self.source_id)
        require(
            len(self.contexts) <= 8
            and len({c.kind for c in self.contexts}) == len(self.contexts),
            "publication context count/duplicates",
        )


@contract("svc_catalog")
@dataclass(frozen=True, slots=True)
class PublicationCatalog(Artifact):
    name: str
    entry_ids: tuple[str, ...]
    snapshot_ids: tuple[str, ...]
    as_of_ns: int
    version: str = "1.0"

    def _normalize(self) -> None:
        ids(self, "entry_ids", "snapshot_ids")

    def _validate(self) -> None:
        require(
            len(self.entry_ids) <= 10000
            and len(self.snapshot_ids) <= 10000
            and self.version == "1.0",
            "catalog bounds/version",
        )


@contract("svc_snapshot_query")
@dataclass(frozen=True, slots=True)
class SnapshotQuery(Artifact):
    catalog_id: str
    producer_id: str
    target_id: str
    horizon_id: str
    origin: ForecastOrigin
    universe_id: str
    as_of_ns: int
    policy: str = "EXACT_ONE_V1"
    api_version: str = "1.0"

    def _validate(self) -> None:
        for i in (
            self.catalog_id,
            self.producer_id,
            self.target_id,
            self.horizon_id,
            self.universe_id,
        ):
            validate_fingerprint(i)
        require(self.policy == "EXACT_ONE_V1", "unsupported snapshot selection policy")


@contract("svc_registry_query")
@dataclass(frozen=True, slots=True)
class RegistryQuery(Artifact):
    catalog_id: str
    artifact_id: str | None = None
    producer_id: str | None = None
    target_id: str | None = None
    horizon_id: str | None = None
    page_size: int = 100
    api_version: str = "1.0"

    def _validate(self) -> None:
        for i in (
            self.catalog_id,
            self.artifact_id,
            self.producer_id,
            self.target_id,
            self.horizon_id,
        ):
            if i is not None:
                validate_fingerprint(i)
        require(0 < self.page_size <= 100, "registry page size bound")


@contract("svc_cursor")
@dataclass(frozen=True, slots=True)
class RegistryCursor(Artifact):
    query_id: str
    after_entry_id: str

    def _validate(self) -> None:
        validate_fingerprint(self.query_id, "svc_registry_query")
        validate_fingerprint(self.after_entry_id, "svc_registry_entry")

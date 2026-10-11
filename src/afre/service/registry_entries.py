"""Immutable descriptive registrations, not a model deployment lifecycle."""

from dataclasses import dataclass

from afre.ids import validate_fingerprint
from afre.schema import Artifact, contract, require
from afre.service.schema import RegistryCategory


@contract("svc_registry_entry")
@dataclass(frozen=True, slots=True)
class RegistryEntry(Artifact):
    artifact_id: str
    artifact_type: str
    category: RegistryCategory
    producer_id: str
    producer_family: str
    version: str
    target_id: str
    horizon_id: str
    created_ns: int
    fit_cutoff_ns: int | None
    available_ns: int
    anchor_source_id: str
    artifact_schema: str = "1.0"
    lifecycle: str = "AVAILABLE"
    compatibility: str = "exact-target-horizon-producer-v1"

    def _validate(self) -> None:
        for i in (
            self.artifact_id,
            self.producer_id,
            self.target_id,
            self.horizon_id,
            self.anchor_source_id,
        ):
            validate_fingerprint(i)
        require(
            self.lifecycle == "AVAILABLE"
            and self.artifact_schema == "1.0"
            and self.compatibility == "exact-target-horizon-producer-v1",
            "registry descriptive schema/lifecycle",
        )

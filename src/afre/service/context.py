"""Versioned scalar projections; no executable/native class payloads cross the API."""

from dataclasses import dataclass

from afre.ids import validate_fingerprint
from afre.schema import Artifact, contract, require
from afre.service.schema import ServiceContextKind


@contract("svc_context_field")
@dataclass(frozen=True, slots=True)
class ContextField(Artifact):
    path: str
    value: str | float | int | bool | None


@contract("svc_context_request")
@dataclass(frozen=True, slots=True)
class ContextRequest(Artifact):
    kind: ServiceContextKind
    artifact_id: str
    historical_evaluation: bool = False

    def _validate(self) -> None:
        validate_fingerprint(self.artifact_id)
        require(
            self.historical_evaluation
            == (self.kind in (ServiceContextKind.HEALTH, ServiceContextKind.CHALLENGE)),
            "health/challenge require explicit historical evaluation metadata",
        )


@contract("svc_context")
@dataclass(frozen=True, slots=True)
class SnapshotContext(Artifact):
    kind: ServiceContextKind
    artifact_id: str
    fields: tuple[ContextField, ...]
    available_ns: int
    cutoff_ns: int | None
    historical_evaluation: bool
    action: str
    projection_version: str = "1.0"

    def _normalize(self) -> None:
        self.ordered("fields", "path")

    def _validate(self) -> None:
        require(
            len(self.fields) <= 4096 and self.projection_version == "1.0",
            "context field bound/version",
        )
        require(
            self.action
            == (
                "NONE_DESCRIPTIVE_ONLY"
                if self.kind is ServiceContextKind.HEALTH
                else "MANUAL_ONLY"
                if self.kind is ServiceContextKind.CHALLENGE
                else "RESEARCH_ONLY"
            ),
            "context action boundary",
        )
        require(
            self.historical_evaluation
            == (self.kind in (ServiceContextKind.HEALTH, ServiceContextKind.CHALLENGE)),
            "context historical metadata boundary",
        )

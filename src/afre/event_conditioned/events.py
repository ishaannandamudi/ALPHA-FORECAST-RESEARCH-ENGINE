"""Neutral, versioned event information with existing six-clock evidence."""

from dataclasses import dataclass
from typing import Protocol

from afre.cross_sectional.definitions import GroupPolicy
from afre.cross_sectional.schema import SignalQuality
from afre.event_conditioned.schema import EventClass, EventScope
from afre.feature_store.models import AvailabilityEvidence, SourceReference
from afre.ids import validate_fingerprint
from afre.schema import Artifact, contract, require
from afre.universe.identity import StableIssuerId, StableSecurityId


@contract("ec_value")
@dataclass(frozen=True, slots=True)
class EventValue(Artifact):
    value: float
    unit: str
    method: str
    version: str
    provider: str
    information_cutoff_ns: int
    clocks: AvailabilityEvidence
    source: SourceReference
    lower: float | None = None
    upper: float | None = None

    def _validate(self) -> None:
        require(self.source.provenance.system == self.provider, "event value provider")
        proof = self.clocks.historical_delivery
        require(
            proof is None or proof.source_id == self.source.fingerprint,
            "event value historical source binding",
        )
        require(
            self.information_cutoff_ns <= self.clocks.final_available_ns,
            "event value future information cutoff",
        )
        require(
            (self.lower is None or self.value >= self.lower)
            and (self.upper is None or self.value <= self.upper),
            "event value scale",
        )
        require(
            self.lower is None or self.upper is None or self.lower < self.upper,
            "event value scale interval",
        )

    @property
    def semantic_key(self) -> tuple[str, str, str, str]:
        import json

        return (
            self.provider,
            self.method,
            self.version,
            json.dumps((self.unit, self.lower, self.upper), separators=(",", ":")),
        )


@contract("ec_surprise")
@dataclass(frozen=True, slots=True)
class EventSurprise(Artifact):
    actual: EventValue
    expected: EventValue
    normalization: float
    method_version: str
    computed_ns: int
    available_ns: int

    def _validate(self) -> None:
        require(
            self.actual.unit == self.expected.unit
            and self.normalization > 0
            and self.method_version == "actual-minus-expectation-v1",
            "surprise definition",
        )
        require(
            self.computed_ns
            >= max(
                self.actual.clocks.final_available_ns, self.expected.clocks.final_available_ns
            )
            and self.available_ns >= self.computed_ns,
            "surprise before both actual and expectation",
        )

    @property
    def value(self) -> float:
        from afre.statistical_models.linear_algebra import finite

        return finite((self.actual.value - self.expected.value) / self.normalization)

    @property
    def semantic_key(self) -> tuple[str, str, str, str]:
        import json

        return (
            self.actual.unit,
            self.method_version,
            json.dumps(self.actual.semantic_key, separators=(",", ":")),
            json.dumps((self.expected.semantic_key, self.normalization), separators=(",", ":")),
        )


@contract("ec_subject")
@dataclass(frozen=True, slots=True)
class EventSubject(Artifact):
    scope: EventScope
    security: StableSecurityId | None = None
    issuer: StableIssuerId | None = None
    group_policy: GroupPolicy | None = None
    group_id: str | None = None
    universe_definition_id: str | None = None
    custom_entity: str | None = None

    def _validate(self) -> None:
        require(
            (self.security is not None) == (self.scope is EventScope.SECURITY),
            "event security scope",
        )
        require(
            (self.issuer is not None) == (self.scope is EventScope.ISSUER), "event issuer scope"
        )
        require(
            (self.group_policy is not None) == (self.scope is EventScope.SECTOR)
            and (self.group_id is not None) == (self.scope is EventScope.SECTOR),
            "event group scope",
        )
        require(
            (self.universe_definition_id is not None) == (self.scope is EventScope.MARKET),
            "event market scope",
        )
        if self.universe_definition_id is not None:
            validate_fingerprint(self.universe_definition_id, "u_definition")
        require(
            (self.custom_entity is not None) == (self.scope is EventScope.CUSTOM),
            "event custom scope",
        )


@contract("ec_reference")
@dataclass(frozen=True, slots=True)
class EventReference(Artifact):
    event_id: str
    revision: str
    event_schema: str
    provider: str
    provider_version: str
    event_class: EventClass
    subtype: str
    tags: tuple[str, ...]
    subject: EventSubject
    occurrence_ns: int | None
    clocks: AvailabilityEvidence
    source: SourceReference
    quality: SignalQuality = SignalQuality.VALID
    materiality: EventValue | None = None
    novelty: EventValue | None = None
    surprise: EventSurprise | None = None

    def _normalize(self) -> None:
        require(len(set(self.tags)) == len(self.tags), "duplicate event tags")
        object.__setattr__(self, "tags", tuple(sorted(self.tags)))

    def _validate(self) -> None:
        require(
            self.source.provenance.system == self.provider
            and self.source.provenance.source_version == self.provider_version,
            "event source/provider identity",
        )
        require(self.clocks.upstream_publication_ns is not None, "event publication required")
        proof = self.clocks.historical_delivery
        require(
            proof is None or proof.source_id == self.source.fingerprint,
            "event historical source binding",
        )


class EventReferenceProvider(Protocol):
    def events_as_of(self, cutoff_ns: int) -> tuple[EventReference, ...]: ...

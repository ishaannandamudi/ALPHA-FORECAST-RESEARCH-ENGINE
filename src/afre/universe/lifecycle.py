"""Lifecycle/tradability/relationships preserve original historical identities."""

from dataclasses import dataclass

from afre.schema import Artifact, contract, require
from afre.universe.evidence import UniverseEvidence
from afre.universe.identity import ListingId, StableIssuerId, StableSecurityId
from afre.universe.schema import LifecycleKind, RelationshipKind, TradabilityState


@contract("u_lifecycle")
@dataclass(frozen=True, slots=True)
class LifecycleEvent(Artifact):
    security: StableSecurityId
    event_id: str
    kind: LifecycleKind
    description: str
    evidence: UniverseEvidence

    def _validate(self) -> None:
        require(
            self.evidence.entity == self.security.instrument,
            "lifecycle evidence entity mismatch",
        )


@contract("u_tradability")
@dataclass(frozen=True, slots=True)
class TradabilityRecord(Artifact):
    listing: ListingId
    security: StableSecurityId
    state: TradabilityState
    evidence: UniverseEvidence

    def _validate(self) -> None:
        require(
            self.evidence.entity == self.security.instrument,
            "tradability evidence entity mismatch",
        )


@contract("u_relationship")
@dataclass(frozen=True, slots=True)
class SecurityRelationship(Artifact):
    security: StableSecurityId
    kind: RelationshipKind
    related_security: StableSecurityId | None
    issuer: StableIssuerId | None
    listing: ListingId | None
    evidence: UniverseEvidence

    def _validate(self) -> None:
        require(
            self.evidence.entity == self.security.instrument,
            "relationship evidence entity mismatch",
        )
        require(
            sum(
                value is not None
                for value in (self.related_security, self.issuer, self.listing)
            )
            == 1,
            "relationship requires exactly one related identity",
        )
        require(
            (self.kind is RelationshipKind.SECURITY_ISSUED_BY) == (self.issuer is not None),
            "issuer relationship kind mismatch",
        )
        require(
            (self.kind is RelationshipKind.PRIMARY_LISTING_OF) == (self.listing is not None),
            "listing relationship kind mismatch",
        )
        require(
            self.related_security != self.security, "self relationship is not an identity link"
        )

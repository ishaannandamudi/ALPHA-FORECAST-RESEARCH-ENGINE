"""Immutable issuer/security master and temporal supplied identifiers."""

from dataclasses import dataclass

from afre.schema import Artifact, contract, require
from afre.universe.evidence import UniverseEvidence
from afre.universe.identity import StableIssuerId, StableSecurityId
from afre.universe.schema import ExternalIdentifierKind, SecurityType


@contract("u_issuer")
@dataclass(frozen=True, slots=True)
class IssuerRecord(Artifact):
    issuer: StableIssuerId
    jurisdiction: str
    evidence: UniverseEvidence

    def _validate(self) -> None:
        require(
            self.evidence.entity == self.issuer.instrument, "issuer evidence entity mismatch"
        )
        require(
            self.evidence.predecessor_id is None,
            "immutable issuer identity cannot be overwritten",
        )


@contract("u_security")
@dataclass(frozen=True, slots=True)
class SecurityRecord(Artifact):
    security: StableSecurityId
    issuer: StableIssuerId
    security_type: SecurityType
    share_class: str
    asset_class: str
    currency: str
    country: str
    evidence: UniverseEvidence

    def _validate(self) -> None:
        require(
            self.security.instrument != self.issuer.instrument,
            "security and issuer identities must differ",
        )
        require(
            self.evidence.entity == self.security.instrument,
            "security evidence entity mismatch",
        )
        require(
            self.evidence.predecessor_id is None,
            "immutable security identity cannot be overwritten",
        )


@contract("u_identifier")
@dataclass(frozen=True, slots=True)
class ExternalIdentifier(Artifact):
    security: StableSecurityId
    kind: ExternalIdentifierKind
    authority: str
    value: str
    evidence: UniverseEvidence

    def _validate(self) -> None:
        require(
            self.evidence.entity == self.security.instrument,
            "identifier evidence entity mismatch",
        )

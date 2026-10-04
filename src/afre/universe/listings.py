"""Separate listing identity and exact historical symbol assignments."""

from dataclasses import dataclass

from afre.schema import Artifact, contract, require
from afre.universe.evidence import UniverseEvidence
from afre.universe.identity import ListingId, StableSecurityId


@contract("u_listing")
@dataclass(frozen=True, slots=True)
class ListingRecord(Artifact):
    listing: ListingId
    security: StableSecurityId
    venue: str
    currency: str
    primary: bool
    calendar_id: str
    evidence: UniverseEvidence

    def _validate(self) -> None:
        require(
            self.evidence.entity == self.security.instrument, "listing evidence entity mismatch"
        )


@contract("u_symbol")
@dataclass(frozen=True, slots=True)
class SymbolAssignment(Artifact):
    listing: ListingId
    security: StableSecurityId
    symbol: str
    venue: str
    evidence: UniverseEvidence

    def _validate(self) -> None:
        require(
            self.evidence.entity == self.security.instrument, "symbol evidence entity mismatch"
        )

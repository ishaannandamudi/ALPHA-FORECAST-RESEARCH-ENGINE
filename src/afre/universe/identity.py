"""Typed stable identities; display symbols and names never establish identity."""

from dataclasses import dataclass

from afre.ids import InstrumentId
from afre.schema import Artifact, contract


@contract("u_security_id")
@dataclass(frozen=True, slots=True)
class StableSecurityId(Artifact):
    namespace: str
    value: str

    @property
    def instrument(self) -> InstrumentId:
        return InstrumentId(self.namespace, self.value)

    def _validate(self) -> None:
        _ = self.instrument


@contract("u_issuer_id")
@dataclass(frozen=True, slots=True)
class StableIssuerId(Artifact):
    namespace: str
    value: str

    @property
    def instrument(self) -> InstrumentId:
        return InstrumentId(self.namespace, self.value)

    def _validate(self) -> None:
        _ = self.instrument


@contract("u_listing_id")
@dataclass(frozen=True, slots=True)
class ListingId(Artifact):
    namespace: str
    value: str

    def _validate(self) -> None:
        InstrumentId(self.namespace, self.value)

"""Bitemporal evidence with physical clocks and explicit qualified reconstruction."""

from dataclasses import dataclass

from afre.feature_store.models import AvailabilityEvidence, SourceReference
from afre.ids import InstrumentId, validate_fingerprint
from afre.schema import Artifact, contract, require
from afre.time import MAX_TIMESTAMP_NS, TimeRange


@contract("u_evidence")
@dataclass(frozen=True, slots=True)
class UniverseEvidence(Artifact):
    validity: TimeRange
    entity: InstrumentId
    source: SourceReference
    clocks: AvailabilityEvidence
    knowledge_until_ns: int = MAX_TIMESTAMP_NS
    predecessor_id: str | None = None

    def _validate(self) -> None:
        require(
            self.clocks.final_available_ns < self.knowledge_until_ns,
            "empty universe knowledge interval",
        )
        proof = self.clocks.historical_delivery
        if proof is not None:
            require(
                proof.source_id == self.source.fingerprint and proof.entity == self.entity,
                "universe qualified delivery source/entity mismatch",
            )
        if self.predecessor_id is not None:
            validate_fingerprint(self.predecessor_id)
            require(
                self.predecessor_id.startswith("afre.u_"),
                "universe predecessor family required",
            )

    def known(self, cutoff_ns: int) -> bool:
        return self.clocks.final_available_ns <= cutoff_ns < self.knowledge_until_ns

"""Versioned historical classifications using existing delivery clocks."""

from dataclasses import dataclass

from afre.cross_sectional.definitions import GroupPolicy
from afre.cross_sectional.schema import GroupType
from afre.feature_store.models import AvailabilityEvidence, SourceReference
from afre.schema import Artifact, contract, require
from afre.time import TimeRange
from afre.universe.identity import StableSecurityId


@contract("cs_group")
@dataclass(frozen=True, slots=True)
class GroupMembership(Artifact):
    security: StableSecurityId
    group_type: GroupType
    group_id: str
    provider: str
    taxonomy: str
    version: str
    validity: TimeRange
    clocks: AvailabilityEvidence
    source: SourceReference

    def _validate(self) -> None:
        require(self.source.provenance.system == self.provider, "group provider provenance")
        delivery = self.clocks.historical_delivery
        require(
            delivery is None
            or (
                delivery.source_id == self.source.fingerprint
                and delivery.entity == self.security.instrument
            ),
            "group delivery evidence",
        )

    def matches(self, policy: GroupPolicy, at_ns: int, cutoff_ns: int) -> bool:
        return (
            (self.group_type, self.provider, self.taxonomy, self.version)
            == (policy.group_type, policy.provider, policy.taxonomy, policy.version)
            and self.validity.start_ns <= at_ns < self.validity.end_ns
            and self.clocks.final_available_ns <= cutoff_ns
        )

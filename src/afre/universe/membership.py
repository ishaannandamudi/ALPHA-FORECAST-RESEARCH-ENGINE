"""Bitemporal constituent vintages and explicit closed-world coverage evidence."""

from dataclasses import dataclass

from afre.ids import validate_fingerprint
from afre.schema import Artifact, contract, require
from afre.universe.evidence import UniverseEvidence
from afre.universe.identity import StableSecurityId
from afre.universe.schema import MembershipState, SnapshotCompleteness


@contract("u_membership")
@dataclass(frozen=True, slots=True)
class UniverseMembershipVintage(Artifact):
    definition_id: str
    security: StableSecurityId
    state: MembershipState
    evidence: UniverseEvidence

    def _validate(self) -> None:
        validate_fingerprint(self.definition_id, "u_definition")
        require(
            self.evidence.entity == self.security.instrument,
            "membership evidence entity mismatch",
        )


@contract("u_coverage")
@dataclass(frozen=True, slots=True)
class ConstituentCoverage(Artifact):
    definition_id: str
    securities: tuple[StableSecurityId, ...]
    completeness: SnapshotCompleteness
    evidence: UniverseEvidence

    def _normalize(self) -> None:
        self.ordered("securities", "fingerprint")

    def _validate(self) -> None:
        validate_fingerprint(self.definition_id, "u_definition")


@contract("u_membership_selection")
@dataclass(frozen=True, slots=True)
class MembershipSelection(Artifact):
    definition_id: str
    input_build_id: str
    security: StableSecurityId
    valid_at_ns: int
    known_as_of_ns: int
    state: MembershipState
    record_ids: tuple[str, ...]
    future_record_ids: tuple[str, ...]
    coverage_id: str | None

    def _normalize(self) -> None:
        for name in ("record_ids", "future_record_ids"):
            values = getattr(self, name)
            require(len(set(values)) == len(values), "duplicate membership selection")
            object.__setattr__(self, name, tuple(sorted(values)))

    def _validate(self) -> None:
        validate_fingerprint(self.definition_id, "u_definition")
        validate_fingerprint(self.input_build_id, "u_input_build")
        for value in (*self.record_ids, *self.future_record_ids):
            validate_fingerprint(value, "u_membership")
        if self.coverage_id is not None:
            validate_fingerprint(self.coverage_id, "u_coverage")

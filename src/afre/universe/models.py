"""Frozen evidence builds, eligibility results, snapshots and exact audit metadata."""

from dataclasses import dataclass

from afre.feature_store.schema import QueryPolicy
from afre.ids import validate_fingerprint
from afre.schema import Artifact, contract, require
from afre.universe.definitions import UniverseDefinition
from afre.universe.identity import ListingId, StableSecurityId
from afre.universe.membership import MembershipSelection
from afre.universe.schema import (
    UNIVERSE_BUILDER_VERSION,
    EligibilityReason,
    EligibilityState,
    SnapshotCompleteness,
)
from afre.version import ENGINE_VERSION


@contract("u_input_build")
@dataclass(frozen=True, slots=True)
class UniverseInputBuild(Artifact):
    record_ids: tuple[str, ...]
    feature_ids: tuple[str, ...]
    known_as_of_ns: int
    constructed_ns: int
    query_policy: QueryPolicy = QueryPolicy()

    def _normalize(self) -> None:
        for name in ("record_ids", "feature_ids"):
            values = getattr(self, name)
            require(len(set(values)) == len(values), "duplicate universe build input")
            object.__setattr__(self, name, tuple(sorted(values)))

    def _validate(self) -> None:
        require(
            self.constructed_ns >= self.known_as_of_ns,
            "universe build constructed before cutoff",
        )
        for value in self.record_ids:
            validate_fingerprint(value)
            require(value.startswith("afre.u_"), "universe record input required")
        for value in self.feature_ids:
            validate_fingerprint(value, "fs_vintage")


@contract("u_eligibility_result")
@dataclass(frozen=True, slots=True)
class EligibilityResult(Artifact):
    membership: MembershipSelection
    state: EligibilityState
    reasons: tuple[EligibilityReason, ...]
    listing: ListingId | None
    record_ids: tuple[str, ...]
    market_ids: tuple[str, ...]
    price: float | None
    share_volume: float | None
    mean_dollar_volume: float | None
    data_observations: int
    completed_listing_sessions: int

    def _normalize(self) -> None:
        require(len(set(self.reasons)) == len(self.reasons), "duplicate eligibility reason")
        object.__setattr__(self, "reasons", tuple(sorted(self.reasons, key=lambda x: x.value)))
        for name in ("record_ids", "market_ids"):
            values = getattr(self, name)
            require(len(set(values)) == len(values), "duplicate eligibility evidence")
            object.__setattr__(self, name, tuple(sorted(values)))

    def _validate(self) -> None:
        require(bool(self.reasons), "eligibility must explain its decision")
        require(
            (self.state is EligibilityState.ELIGIBLE)
            == (self.reasons == (EligibilityReason.PASSED,)),
            "eligibility reason/state mismatch",
        )
        require(
            self.data_observations >= 0 and self.completed_listing_sessions >= 0,
            "negative eligibility count",
        )
        for value in self.record_ids:
            validate_fingerprint(value)
            require(value.startswith("afre.u_"), "universe eligibility evidence required")
        for value in self.market_ids:
            validate_fingerprint(value, "fs_vintage")


@contract("u_snapshot")
@dataclass(frozen=True, slots=True)
class UniverseSnapshot(Artifact):
    definition: UniverseDefinition
    input_build_id: str
    valid_at_ns: int
    known_as_of_ns: int
    constructed_ns: int
    coverage_id: str | None
    completeness: SnapshotCompleteness
    memberships: tuple[MembershipSelection, ...]
    eligibility: tuple[EligibilityResult, ...]
    builder_version: str = UNIVERSE_BUILDER_VERSION
    engine_version: str = ENGINE_VERSION

    def _normalize(self) -> None:
        self.ordered("memberships", "fingerprint")
        self.ordered("eligibility", "fingerprint")
        object.__setattr__(
            self,
            "memberships",
            tuple(sorted(self.memberships, key=lambda x: x.security.fingerprint)),
        )
        object.__setattr__(
            self,
            "eligibility",
            tuple(sorted(self.eligibility, key=lambda x: x.membership.security.fingerprint)),
        )

    def _validate(self) -> None:
        validate_fingerprint(self.input_build_id, "u_input_build")
        require(
            self.constructed_ns >= self.known_as_of_ns,
            "snapshot physical reconstruction precedes cutoff",
        )
        require(
            self.builder_version == self.definition.implementation_version,
            "snapshot builder mismatch",
        )
        require(
            len(self.memberships) == len(self.eligibility)
            and len({x.security for x in self.memberships}) == len(self.memberships),
            "snapshot security grid mismatch",
        )
        require(
            tuple(x.membership for x in self.eligibility) == self.memberships,
            "snapshot eligibility/membership mismatch",
        )
        require(
            all(
                x.definition_id == self.definition.fingerprint
                and x.input_build_id == self.input_build_id
                and x.valid_at_ns == self.valid_at_ns
                and x.known_as_of_ns == self.known_as_of_ns
                for x in self.memberships
            ),
            "snapshot membership context mismatch",
        )
        if self.coverage_id is not None:
            validate_fingerprint(self.coverage_id, "u_coverage")


@contract("u_resolution")
@dataclass(frozen=True, slots=True)
class SecurityResolution(Artifact):
    symbol: str
    venue: str
    valid_at_ns: int
    known_as_of_ns: int
    security: StableSecurityId | None
    listing: ListingId | None
    assignment_ids: tuple[str, ...]
    conflicted: bool

    def _normalize(self) -> None:
        require(
            len(set(self.assignment_ids)) == len(self.assignment_ids),
            "duplicate resolution evidence",
        )
        object.__setattr__(self, "assignment_ids", tuple(sorted(self.assignment_ids)))

    def _validate(self) -> None:
        require(
            (self.security is not None) == (self.listing is not None),
            "partial security/listing resolution",
        )
        require(
            not self.conflicted or self.security is None, "conflicting symbol cannot resolve"
        )
        for value in self.assignment_ids:
            validate_fingerprint(value, "u_symbol")


@contract("u_audit")
@dataclass(frozen=True, slots=True)
class UniverseAudit(Artifact):
    snapshot_id: str
    security: StableSecurityId
    eligibility: EligibilityResult
    lineage_ids: tuple[str, ...]

    def _normalize(self) -> None:
        require(
            len(set(self.lineage_ids)) == len(self.lineage_ids),
            "duplicate universe audit lineage",
        )
        object.__setattr__(self, "lineage_ids", tuple(sorted(self.lineage_ids)))

    def _validate(self) -> None:
        validate_fingerprint(self.snapshot_id, "u_snapshot")
        require(
            self.security == self.eligibility.membership.security, "audit security mismatch"
        )

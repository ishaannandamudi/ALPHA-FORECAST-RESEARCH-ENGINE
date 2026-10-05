"""Neutral provider identities, ordered taxonomies and six-clock state evidence."""

from dataclasses import dataclass
from typing import Protocol

from afre.cross_sectional.definitions import GroupPolicy
from afre.feature_store.models import AvailabilityEvidence, SourceReference
from afre.ids import InstrumentId, validate_fingerprint
from afre.regime_conditioned.memberships import RegimeMembership
from afre.regime_conditioned.schema import (
    REGIME_IMPLEMENTATION,
    RegimeCategory,
    RegimeQuality,
    RegimeScope,
    RegimeStateSemantics,
)
from afre.schema import Artifact, contract, require
from afre.universe.identity import StableSecurityId


@contract("rc_provider")
@dataclass(frozen=True, slots=True)
class RegimeProviderReference(Artifact):
    provider: str
    provider_version: str
    provider_schema: str
    taxonomy_id: str
    taxonomy_version: str
    source: SourceReference
    method_id: str | None = None

    def _validate(self) -> None:
        require(self.source.provenance.system == self.provider, "regime provider source")


@contract("rc_taxonomy")
@dataclass(frozen=True, slots=True)
class RegimeTaxonomy(Artifact):
    provider: RegimeProviderReference
    states: tuple[str, ...]
    labels: tuple[str, ...]
    descriptions: tuple[str, ...]
    category: RegimeCategory
    dimensionality: int
    implementation_version: str = REGIME_IMPLEMENTATION

    def _validate(self) -> None:
        require(
            bool(self.states)
            and len(set(self.states)) == len(self.states)
            and len(self.states)
            == len(self.labels)
            == len(self.descriptions)
            == self.dimensionality,
            "taxonomy ordered dimensionality",
        )
        require(self.implementation_version == REGIME_IMPLEMENTATION, "taxonomy implementation")


@contract("rc_subject")
@dataclass(frozen=True, slots=True)
class RegimeSubject(Artifact):
    scope: RegimeScope
    entity: InstrumentId
    security: StableSecurityId | None = None
    universe_definition_id: str | None = None
    group_policy: GroupPolicy | None = None
    group_id: str | None = None

    def _validate(self) -> None:
        require(
            (self.security is not None) == (self.scope is RegimeScope.SECURITY),
            "regime security scope",
        )
        require(
            (self.universe_definition_id is not None) == (self.scope is RegimeScope.MARKET),
            "regime market scope",
        )
        require(
            (self.group_policy is not None and self.group_id is not None)
            == (self.scope is RegimeScope.SECTOR),
            "regime sector scope",
        )
        require(
            self.scope is RegimeScope.SECTOR
            or self.group_policy is None
            and self.group_id is None,
            "regime group evidence",
        )
        if self.security:
            require(self.entity == self.security.instrument, "regime entity/security mismatch")
        if self.universe_definition_id:
            validate_fingerprint(self.universe_definition_id, "u_definition")


@contract("rc_snapshot")
@dataclass(frozen=True, slots=True)
class RegimeSnapshot(Artifact):
    taxonomy: RegimeTaxonomy
    subject: RegimeSubject
    as_of_ns: int
    clocks: AvailabilityEvidence
    membership: RegimeMembership
    semantics: RegimeStateSemantics
    quality: RegimeQuality
    source: SourceReference
    revision: str = "1"

    def _validate(self) -> None:
        require(self.membership.states == self.taxonomy.states, "regime taxonomy membership")
        require(
            self.source.provenance.system == self.taxonomy.provider.provider,
            "regime snapshot provider",
        )
        require(self.as_of_ns <= self.clocks.final_available_ns, "regime future observation")
        proof = self.clocks.historical_delivery
        require(
            proof is None
            or proof.source_id == self.source.fingerprint
            and proof.entity == self.subject.entity,
            "regime historical source/entity binding",
        )


class RegimeProvider(Protocol):
    def snapshots(
        self, taxonomy: RegimeTaxonomy, subject: RegimeSubject, cutoff_ns: int
    ) -> tuple[RegimeSnapshot, ...]: ...

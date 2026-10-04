"""Immutable definitions, evidence, vintages, scopes and feature-set manifests."""

import re
from dataclasses import dataclass

from afre.datasets import AdjustmentPolicy
from afre.feature_store.freshness import FreshnessPolicy
from afre.feature_store.schema import (
    AvailabilityMode,
    DeliveryEvidenceKind,
    StoreScope,
    ValidityRule,
)
from afre.features import (
    AvailabilityRule,
    DataQuality,
    FeatureDefinition,
    FeatureScope,
    FeatureValue,
    MissingState,
)
from afre.ids import InstrumentId, validate_fingerprint
from afre.lineage import FeatureDependency, FeatureLineage, Parameter, ProvenanceRef, Scalar
from afre.providers import EventSnapshotRef
from afre.schema import Artifact, contract, require
from afre.time import TimeRange

FORBIDDEN_DOMAINS = (
    "afre.target_",
    "afre.experiment_",
    "afre.metric_",
    "afre.model_",
    "afre.evaluation_",
    "target.",
    "label.",
    "evaluation.",
    "future_return.",
)


def exclude_target_reference(identity: str) -> None:
    require(
        not identity.lower().startswith(FORBIDDEN_DOMAINS),
        "target/evaluation provenance is forbidden in features",
    )


@contract("fs_source")
@dataclass(frozen=True, slots=True)
class SourceReference(Artifact):
    provenance: ProvenanceRef
    dataset_id: str
    parent_source_ids: tuple[str, ...] = ()
    uncertainty_categories: tuple[str, ...] = ()
    event_snapshot: EventSnapshotRef | None = None

    def _normalize(self) -> None:
        for name in ("parent_source_ids", "uncertainty_categories"):
            values = getattr(self, name)
            require(len(set(values)) == len(values), "duplicate source reference")
            object.__setattr__(self, name, tuple(sorted(values)))

    def _validate(self) -> None:
        exclude_target_reference(self.provenance.artifact_id)
        exclude_target_reference(self.dataset_id)
        validate_fingerprint(self.dataset_id)
        if self.event_snapshot is not None:
            for component in self.event_snapshot.components:
                exclude_target_reference(component.artifact_id)
        for parent in self.parent_source_ids:
            exclude_target_reference(parent)
            validate_fingerprint(parent, "fs_source")


@contract("fs_delivery_contract")
@dataclass(frozen=True, slots=True)
class QualifiedHistoricalDelivery(Artifact):
    source_id: str
    entity: InstrumentId
    kind: DeliveryEvidenceKind
    historical_received_ns: int
    historical_ingested_ns: int
    historical_computed_ns: int
    qualified_ns: int
    attestor: str
    delivery_channel: str
    qualification_version: str
    evidence: ProvenanceRef

    def _validate(self) -> None:
        validate_fingerprint(self.source_id, "fs_source")
        exclude_target_reference(self.evidence.artifact_id)
        require(
            self.historical_received_ns
            <= self.historical_ingested_ns
            <= self.historical_computed_ns
            <= self.qualified_ns,
            "invalid historical delivery/computation ordering",
        )


@contract("fs_availability")
@dataclass(frozen=True, slots=True)
class AvailabilityEvidence(Artifact):
    afre_received_ns: int
    afre_ingested_ns: int
    afre_computed_ns: int
    final_available_ns: int
    upstream_publication_ns: int | None = None
    upstream_available_ns: int | None = None
    mode: AvailabilityMode = AvailabilityMode.LIVE
    historical_delivery: QualifiedHistoricalDelivery | None = None

    def _validate(self) -> None:
        require(
            self.afre_received_ns <= self.afre_ingested_ns <= self.afre_computed_ns,
            "AFRE receipt/ingestion/computation ordering",
        )
        if self.upstream_publication_ns is not None and self.upstream_available_ns is not None:
            require(
                self.upstream_publication_ns <= self.upstream_available_ns,
                "source availability before publication",
            )
        if self.upstream_available_ns is not None:
            require(
                self.upstream_available_ns <= self.afre_received_ns,
                "AFRE receipt before upstream source availability",
            )
        if self.upstream_publication_ns is not None:
            require(
                self.upstream_publication_ns <= self.afre_received_ns,
                "AFRE receipt before publication",
            )
        if self.historical_delivery is not None:
            require(
                self.mode is AvailabilityMode.RECONSTRUCTED,
                "live ingestion cannot claim historical delivery",
            )
            require(
                self.historical_delivery.qualified_ns <= self.afre_computed_ns,
                "qualification after reconstruction computation",
            )
            require(
                self.historical_delivery.historical_received_ns
                >= max(self.upstream_publication_ns or 0, self.upstream_available_ns or 0),
                "historical delivery precedes upstream evidence",
            )
        require(
            self.final_available_ns >= self.availability_floor_ns,
            "feature backdated before receipt/processing/delivery evidence",
        )

    @property
    def availability_floor_ns(self) -> int:
        processing = self.afre_computed_ns
        if self.historical_delivery is not None:
            processing = self.historical_delivery.historical_computed_ns
        return max(
            processing, self.upstream_publication_ns or 0, self.upstream_available_ns or 0
        )


@contract("fs_definition")
@dataclass(frozen=True, slots=True)
class RegisteredFeatureDefinition(Artifact):
    definition: FeatureDefinition
    scope: StoreScope
    freshness: FreshnessPolicy
    validity_rule: ValidityRule
    calendar_id: str
    build_context: str
    adjustment: AdjustmentPolicy
    source_dataset_ids: tuple[str, ...]
    parameters: tuple[Parameter, ...] = ()

    def _normalize(self) -> None:
        self.ordered("parameters", "name")
        require(
            len(set(self.source_dataset_ids)) == len(self.source_dataset_ids),
            "duplicate datasets",
        )
        object.__setattr__(self, "source_dataset_ids", tuple(sorted(self.source_dataset_ids)))

    def _validate(self) -> None:
        require(
            bool(
                re.fullmatch(
                    r"(?:market|eie|mce|options|microstructure|fundamental|macro|derived)\."
                    r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*",
                    self.definition.name,
                )
            ),
            "feature name must use a validated semantic namespace",
        )
        require(
            (self.definition.scope is FeatureScope.INSTRUMENT)
            == (self.scope is StoreScope.SECURITY),
            "foundation/store scope mismatch",
        )
        require(bool(self.source_dataset_ids), "source dataset identity required")
        for identity in self.source_dataset_ids:
            exclude_target_reference(identity)
            validate_fingerprint(identity)
        if self.adjustment.source_dataset_id is not None:
            require(
                self.adjustment.source_dataset_id in self.source_dataset_ids,
                "adjustment source not declared",
            )


@contract("fs_feature_set")
@dataclass(frozen=True, slots=True)
class FeatureSetManifest(Artifact):
    definitions: tuple[RegisteredFeatureDefinition, ...]

    def _normalize(self) -> None:
        self.ordered("definitions", "fingerprint")

    def _validate(self) -> None:
        require(bool(self.definitions), "empty feature-store feature set")
        names = [(item.definition.name, item.definition.version) for item in self.definitions]
        require(len(set(names)) == len(names), "conflicting feature definition revisions")


@contract("fs_scope_binding")
@dataclass(frozen=True, slots=True)
class ScopeBinding(Artifact):
    scope: StoreScope
    entity: InstrumentId
    security: InstrumentId
    validity: TimeRange
    known_ns: int
    evidence: ProvenanceRef

    def _validate(self) -> None:
        require(self.scope is not StoreScope.SECURITY, "security scope needs no broadcast")
        exclude_target_reference(self.evidence.artifact_id)


@contract("fs_vintage")
@dataclass(frozen=True, slots=True)
class FeatureVintage(Artifact):
    feature: RegisteredFeatureDefinition
    entity: InstrumentId
    effective_ns: int
    clocks: AvailabilityEvidence
    source: SourceReference
    value: Scalar | None
    state: MissingState
    quality: DataQuality
    valid_until_ns: int | None = None
    predecessor_id: str | None = None
    input_ids: tuple[str, ...] = ()
    dependency_refs: tuple[FeatureDependency, ...] = ()
    computation_spec_id: str | None = None
    normalization_state_id: str | None = None

    def _normalize(self) -> None:
        self.ordered("dependency_refs", "definition_id")
        require(len(set(self.input_ids)) == len(self.input_ids), "duplicate vintage inputs")
        object.__setattr__(self, "input_ids", tuple(sorted(self.input_ids)))

    def _validate(self) -> None:
        if self.valid_until_ns is not None:
            require(self.effective_ns < self.valid_until_ns, "empty vintage validity interval")
        if self.feature.validity_rule is ValidityRule.INTERVAL:
            require(self.valid_until_ns is not None, "interval feature requires end boundary")
        require(
            self.source.dataset_id in self.feature.source_dataset_ids,
            "vintage source dataset incompatible with definition",
        )
        require(
            self.clocks.final_available_ns >= self.feature.adjustment.known_as_of_ns,
            "future adjustment information",
        )
        if self.source.event_snapshot is not None:
            snapshot = self.source.event_snapshot
            require(
                snapshot.instrument == self.entity
                and snapshot.available_ns <= self.clocks.final_available_ns,
                "EIE snapshot security/availability mismatch",
            )
        delivery = self.clocks.historical_delivery
        if delivery is not None:
            require(
                delivery.source_id == self.source.fingerprint
                and delivery.entity == self.entity,
                "historical delivery evidence not bound to exact source/entity",
            )
        for identity, domain in (
            (self.predecessor_id, "fs_vintage"),
            (self.computation_spec_id, "fs_computation_spec"),
            (self.normalization_state_id, "fs_normalization_state"),
        ):
            if identity is not None:
                exclude_target_reference(identity)
                validate_fingerprint(identity, domain)
        for identity in self.input_ids:
            exclude_target_reference(identity)
            validate_fingerprint(identity, "fs_vintage")
        computed = self.feature.definition.availability_rule is AvailabilityRule.COMPUTED
        require(
            computed == (self.computation_spec_id is not None),
            "computed/source vintage mismatch",
        )
        require(
            computed or not self.input_ids, "source vintage cannot have computed feature inputs"
        )
        # AFRE-0's value/type/missing/dependency invariants remain authoritative.
        self.to_feature_value(self.entity, self.state, "vintage-validation")

    def to_feature_value(
        self, security: InstrumentId, state: MissingState, policy_id: str
    ) -> FeatureValue:
        from afre.hashing import bytes_digest
        from afre.serialization import canonical_json

        # A content reference to this vintage pins all physical and historical clocks.
        reference = ProvenanceRef(
            "AFRE-feature-store",
            self.fingerprint,
            "1.0",
            bytes_digest(canonical_json(self).encode()),
        )
        lineage = FeatureLineage(
            (reference,),
            self.dependency_refs,
            self.feature.definition.transformation_version,
            (
                Parameter("query_policy", policy_id),
                Parameter("freshness", self.feature.freshness.fingerprint),
            ),
            self.feature.build_context,
            "afre-feature-store-v1",
            self.clocks.final_available_ns if self.computation_spec_id else None,
        )
        return FeatureValue(
            self.feature.definition,
            security,
            self.effective_ns,
            self.clocks.upstream_available_ns
            if self.clocks.upstream_available_ns is not None
            else (
                self.clocks.upstream_publication_ns
                if self.clocks.upstream_publication_ns is not None
                else self.clocks.availability_floor_ns
            ),
            self.clocks.final_available_ns,
            self.value if state is MissingState.PRESENT else None,
            state,
            self.source.provenance.system,
            self.source.provenance.source_version,
            self.quality,
            lineage,
        )

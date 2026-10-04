"""Explicit upstream compatibility, research grid and missing-data contracts."""

from dataclasses import dataclass

from afre.datasets import AdjustmentPolicy
from afre.feature_store.models import FeatureSetManifest, exclude_target_reference
from afre.feature_store.schema import QueryPolicy
from afre.ids import validate_fingerprint
from afre.research_datasets.schema import BUILDER_VERSION, DatasetMissingPolicy, PurgeScope
from afre.schema import Artifact, contract, require
from afre.target_engine.definitions import TargetSetManifest
from afre.time import TimeRange
from afre.universe.identity import StableSecurityId


@contract("r_compatibility")
@dataclass(frozen=True, slots=True)
class DatasetCompatibility(Artifact):
    source_dataset_ids: tuple[str, ...]
    calendar_id: str
    universe_calendar_ids: tuple[str, ...]
    target_calendar_ids: tuple[str, ...]
    feature_adjustment: AdjustmentPolicy
    target_adjustment_ids: tuple[str, ...]
    intentional_adjustment_difference: bool = False

    def _normalize(self) -> None:
        for name in (
            "source_dataset_ids",
            "universe_calendar_ids",
            "target_calendar_ids",
            "target_adjustment_ids",
        ):
            values = getattr(self, name)
            require(
                bool(values) and len(set(values)) == len(values),
                "explicit unique compatibility identities required",
            )
            object.__setattr__(self, name, tuple(sorted(values)))

    def _validate(self) -> None:
        for identity in self.source_dataset_ids:
            exclude_target_reference(identity)
            validate_fingerprint(identity)
        for name, domain in (
            ("universe_calendar_ids", "u_calendar"),
            ("target_calendar_ids", "target_calendar"),
            ("target_adjustment_ids", "adjustment_policy"),
        ):
            for identity in getattr(self, name):
                validate_fingerprint(identity, domain)


@contract("r_group_binding")
@dataclass(frozen=True, slots=True)
class ResearchGroupBinding(Artifact):
    security: StableSecurityId
    scope: PurgeScope
    group: str
    validity: TimeRange
    known_ns: int
    source_id: str

    def _validate(self) -> None:
        require(
            self.scope in (PurgeScope.ISSUER, PurgeScope.SECTOR, PurgeScope.MARKET),
            "explicit group scope required",
        )
        exclude_target_reference(self.source_id)
        validate_fingerprint(self.source_id)


@contract("r_dataset_definition")
@dataclass(frozen=True, slots=True)
class ResearchDatasetDefinition(Artifact):
    name: str
    version: str
    feature_set: FeatureSetManifest
    target_set: TargetSetManifest
    compatibility: DatasetCompatibility
    missing_policy: DatasetMissingPolicy = DatasetMissingPolicy.PRESERVE_MISSING
    query_policy: QueryPolicy = QueryPolicy()
    group_bindings: tuple[ResearchGroupBinding, ...] = ()
    implementation_version: str = BUILDER_VERSION

    def _normalize(self) -> None:
        self.ordered("group_bindings", "fingerprint")

    def _validate(self) -> None:
        require(self.name.startswith("research."), "research dataset namespace required")
        require(
            self.missing_policy is not DatasetMissingPolicy.IMPUTE_TRAIN_ONLY,
            "train-only imputation is reserved and not implemented",
        )
        compatibility = self.compatibility
        for feature in self.feature_set.definitions:
            require(
                feature.calendar_id == compatibility.calendar_id
                and feature.adjustment == compatibility.feature_adjustment,
                "feature calendar/adjustment mismatch",
            )
            require(
                set(feature.source_dataset_ids) <= set(compatibility.source_dataset_ids),
                "feature source outside compatibility contract",
            )
        for target in self.target_set.definitions:
            require(
                target.calendar_id == compatibility.calendar_id
                and target.adjustment.fingerprint in compatibility.target_adjustment_ids,
                "target calendar/adjustment outside compatibility contract",
            )
            require(
                target.adjustment == compatibility.feature_adjustment
                or compatibility.intentional_adjustment_difference,
                "undeclared feature/target adjustment difference",
            )
            require(
                set(target.source_dataset_ids) <= set(compatibility.source_dataset_ids),
                "target source outside compatibility contract",
            )


@contract("r_origin_request")
@dataclass(frozen=True, slots=True)
class ResearchOriginRequest(Artifact):
    snapshot_id: str
    market_session_id: str
    build_context: str
    target_dataset_id: str | None
    securities: tuple[StableSecurityId, ...] = ()

    def _normalize(self) -> None:
        self.ordered("securities", "fingerprint")

    def _validate(self) -> None:
        validate_fingerprint(self.snapshot_id, "u_snapshot")
        if self.target_dataset_id is not None:
            validate_fingerprint(self.target_dataset_id, "target_dataset")

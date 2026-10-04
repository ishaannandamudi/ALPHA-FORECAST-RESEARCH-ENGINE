"""Dataset/universe identity contracts; no materialization or PIT feature store."""

from dataclasses import dataclass
from enum import Enum

from afre.features import FeatureSet, FeatureValue, MissingPolicy, validate_feature_availability
from afre.forecast import ForecastOrigin
from afre.ids import InstrumentId, validate_fingerprint
from afre.schema import Artifact, contract, enum, require
from afre.targets import TargetSpec
from afre.time import TimeRange, validate_timestamp
from afre.version import ENGINE_VERSION


@enum
class UniversePolicy(Enum):
    POINT_IN_TIME = "point_in_time"
    FIXED_COHORT = "fixed_cohort"
    CURRENT_CONSTITUENTS = "current_constituents"


@contract("universe_membership")
@dataclass(frozen=True, slots=True)
class UniverseMembership(Artifact):
    instrument: InstrumentId
    validity: TimeRange
    known_ns: int
    source: str


@contract("universe_manifest")
@dataclass(frozen=True, slots=True)
class UniverseManifest(Artifact):
    name: str
    membership_source: str
    selection_version: str
    policy: UniversePolicy
    memberships: tuple[UniverseMembership, ...]

    def _normalize(self) -> None:
        self.ordered("memberships", "fingerprint")

    def _validate(self) -> None:
        require(
            self.policy is not UniversePolicy.CURRENT_CONSTITUENTS,
            "current constituents cannot reconstruct historical universes",
        )
        require(bool(self.memberships), "empty universe")

    def eligible(self, origin: ForecastOrigin) -> bool:
        require(origin.universe_id == self.fingerprint, "origin universe mismatch")
        return any(
            member.instrument == origin.instrument
            and member.validity.contains(origin.timestamp_ns)
            and member.known_ns <= origin.availability_cutoff_ns
            for member in self.memberships
        )


@contract("symbol_mapping")
@dataclass(frozen=True, slots=True)
class SymbolMapping(Artifact):
    symbol: str
    venue: str
    instrument: InstrumentId
    validity: TimeRange
    known_ns: int


def resolve_symbol(
    mappings: tuple[SymbolMapping, ...],
    symbol: str,
    venue: str,
    valid_ns: int,
    known_as_of_ns: int,
) -> InstrumentId:
    validate_timestamp(valid_ns)
    validate_timestamp(known_as_of_ns)
    matches = {
        item.instrument
        for item in mappings
        if item.symbol == symbol
        and item.venue == venue
        and item.validity.contains(valid_ns)
        and item.known_ns <= known_as_of_ns
    }
    require(len(matches) == 1, "missing or ambiguous historical symbol")
    return next(iter(matches))


@enum
class AdjustmentBasis(Enum):
    RAW = "raw"
    SPLIT_ADJUSTED = "split_adjusted"
    TOTAL_RETURN = "total_return"
    EXPLICIT_ADJUSTMENT_STREAM = "explicit_adjustment_stream"


@contract("adjustment_policy")
@dataclass(frozen=True, slots=True)
class AdjustmentPolicy(Artifact):
    basis: AdjustmentBasis
    known_as_of_ns: int
    source_dataset_id: str | None = None

    def _validate(self) -> None:
        require(
            (self.source_dataset_id is not None) == (self.basis is not AdjustmentBasis.RAW),
            "adjustment source required exactly for non-raw data",
        )
        if self.source_dataset_id is not None:
            validate_fingerprint(self.source_dataset_id)


@contract("dataset_manifest")
@dataclass(frozen=True, slots=True)
class DatasetManifest(Artifact):
    name: str
    origins: TimeRange
    universe: UniverseManifest
    feature_set: FeatureSet
    targets: tuple[TargetSpec, ...]
    source_dataset_ids: tuple[str, ...]
    calendar_id: str
    adjustment: AdjustmentPolicy
    missing_policy: MissingPolicy
    processing_version: str
    engine_version: str = ENGINE_VERSION

    def _normalize(self) -> None:
        self.ordered("targets", "fingerprint")
        object.__setattr__(self, "source_dataset_ids", tuple(sorted(self.source_dataset_ids)))

    def _validate(self) -> None:
        require(
            bool(self.targets) and bool(self.source_dataset_ids),
            "dataset requires inputs/targets",
        )
        require(
            len(set(self.source_dataset_ids)) == len(self.source_dataset_ids),
            "duplicate sources",
        )
        for source in self.source_dataset_ids:
            validate_fingerprint(source)
        require(
            self.adjustment.known_as_of_ns <= self.origins.start_ns,
            "future adjustment vintage in historical dataset",
        )
        for target in self.targets:
            if target.horizon.calendar_id is not None:
                require(
                    target.horizon.calendar_id == self.calendar_id, "target calendar mismatch"
                )
        if self.adjustment.source_dataset_id is not None:
            require(
                self.adjustment.source_dataset_id in self.source_dataset_ids,
                "adjustment source missing from dataset lineage",
            )
        if self.missing_policy is MissingPolicy.REJECT:
            require(
                all(
                    item.missing_policy is MissingPolicy.REJECT
                    for item in self.feature_set.definitions
                ),
                "missing policy mismatch",
            )


@contract("feature_row")
@dataclass(frozen=True, slots=True)
class ForecastFeatureRow(Artifact):
    origin: ForecastOrigin
    dataset: DatasetManifest
    features: tuple[FeatureValue, ...]

    def _normalize(self) -> None:
        self.ordered("features", "fingerprint")

    def _validate(self) -> None:
        require(
            self.dataset.origins.contains(self.origin.timestamp_ns), "origin outside dataset"
        )
        require(
            self.dataset.universe.eligible(self.origin), "historical universe excludes security"
        )
        expected = {item.fingerprint for item in self.dataset.feature_set.definitions}
        actual = [item.definition.fingerprint for item in self.features]
        require(
            len(actual) == len(expected) and set(actual) == expected,
            "feature definitions mismatch",
        )
        for feature in self.features:
            validate_feature_availability(feature, self.origin)

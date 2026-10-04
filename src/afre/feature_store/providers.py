"""Offline market/EIE extraction and provider-neutral receipt-aware boundaries."""

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from afre.datasets import AdjustmentPolicy
from afre.feature_store.models import (
    AvailabilityEvidence,
    FeatureVintage,
    RegisteredFeatureDefinition,
    SourceReference,
)
from afre.features import DataQuality, MissingState
from afre.hashing import bytes_digest
from afre.ids import InstrumentId
from afre.lineage import ProvenanceRef
from afre.providers import EventSnapshotRef
from afre.schema import Artifact, contract, enum, require
from afre.serialization import canonical_json
from afre.time import TimeRange


@enum
class BarTimestampConvention(Enum):
    OPEN = "open"
    CLOSE = "close"
    END_EXCLUSIVE = "end_exclusive"


@contract("fs_market_bar")
@dataclass(frozen=True, slots=True)
class MarketBar(Artifact):
    instrument: InstrumentId
    period: TimeRange
    timestamp_ns: int
    timestamp_convention: BarTimestampConvention
    close: float
    volume: float
    clocks: AvailabilityEvidence
    source: SourceReference
    adjustment: AdjustmentPolicy
    calendar_id: str
    build_context: str

    def _validate(self) -> None:
        require(self.close > 0 and self.volume >= 0, "invalid market bar price/volume")
        expected = (
            self.period.start_ns
            if self.timestamp_convention is BarTimestampConvention.OPEN
            else self.period.end_ns
        )
        require(self.timestamp_ns == expected, "ambiguous bar timestamp convention")
        require(
            self.clocks.final_available_ns >= self.period.end_ns,
            "bar close cannot be available before bar completion",
        )
        require(
            self.adjustment.known_as_of_ns <= self.clocks.final_available_ns,
            "bar uses future corporate-action vintage",
        )


class MarketFeatureAdapter:
    def extract(self, bar: MarketBar, feature: RegisteredFeatureDefinition) -> FeatureVintage:
        require(
            feature.definition.name in ("market.close", "market.volume"),
            "offline bar adapter supports only close and volume source features",
        )
        require(
            feature.adjustment == bar.adjustment
            and feature.calendar_id == bar.calendar_id
            and feature.build_context == bar.build_context,
            "bar/feature context mismatch",
        )
        require(
            feature.definition.unit
            == ("currency" if feature.definition.name == "market.close" else "shares"),
            "bar feature unit mismatch",
        )
        source = SourceReference(
            ProvenanceRef(
                "AFRE-market-bar",
                bar.fingerprint,
                "1.0",
                bytes_digest(canonical_json(bar).encode()),
            ),
            bar.source.dataset_id,
            (bar.source.fingerprint,),
        )
        return FeatureVintage(
            feature,
            bar.instrument,
            bar.period.end_ns,
            bar.clocks,
            source,
            bar.close if feature.definition.name == "market.close" else bar.volume,
            MissingState.PRESENT,
            DataQuality.VERIFIED,
        )


@contract("fs_eie_features")
@dataclass(frozen=True, slots=True)
class SuppliedEIEFeatures(Artifact):
    snapshot: EventSnapshotRef
    effective_ns: int
    materiality: float | None
    information_surprise: float | None
    novelty: float | None
    uncertainty_categories: tuple[str, ...]

    def _normalize(self) -> None:
        require(
            len(set(self.uncertainty_categories)) == len(self.uncertainty_categories),
            "duplicate uncertainty category",
        )
        object.__setattr__(
            self, "uncertainty_categories", tuple(sorted(self.uncertainty_categories))
        )


class EIEFeatureAdapter:
    def extract(
        self,
        supplied: SuppliedEIEFeatures,
        feature: RegisteredFeatureDefinition,
        clocks: AvailabilityEvidence,
        source_dataset_id: str,
    ) -> FeatureVintage:
        values = {
            "eie.event_materiality": supplied.materiality,
            "eie.information_surprise": supplied.information_surprise,
            "eie.event_novelty": supplied.novelty,
        }
        require(feature.definition.name in values, "unsupported neutral EIE feature")
        require(feature.definition.unit == "ratio", "EIE feature unit mismatch")
        require(
            clocks.upstream_available_ns is not None
            and clocks.upstream_available_ns >= supplied.snapshot.available_ns,
            "EIE availability must constrain AFRE availability",
        )
        source = SourceReference(
            ProvenanceRef(
                "EIE",
                supplied.snapshot.snapshot_id,
                supplied.snapshot.engine_version,
                bytes_digest(canonical_json(supplied).encode()),
            ),
            source_dataset_id,
            uncertainty_categories=supplied.uncertainty_categories,
            event_snapshot=supplied.snapshot,
        )
        value = values[feature.definition.name]
        return FeatureVintage(
            feature,
            supplied.snapshot.instrument,
            supplied.effective_ns,
            clocks,
            source,
            value,
            MissingState.PRESENT if value is not None else MissingState.UNKNOWN,
            DataQuality.VERIFIED,
        )


class SourceVintageProvider(Protocol):
    def get_vintages(
        self, instrument: InstrumentId, known_as_of_ns: int
    ) -> tuple[FeatureVintage, ...]: ...


class MarketVintageProvider(SourceVintageProvider, Protocol):
    """External prices/bars retain receipt, completion, adjustment and revision clocks."""


class EIEVintageProvider(SourceVintageProvider, Protocol):
    """Neutral final-snapshot feature delivery; no EIE internal access."""


class MarketContextVintageProvider(SourceVintageProvider, Protocol):
    """Neutral MCE feature delivery, with conservative AFRE receipt/processing clocks."""


class OptionsVintageProvider(SourceVintageProvider, Protocol):
    """Neutral options feature delivery."""


class MicrostructureVintageProvider(SourceVintageProvider, Protocol):
    """Neutral AME/microstructure feature delivery."""

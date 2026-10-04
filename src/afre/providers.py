"""Provider-neutral as-of protocols. AFRE imports no upstream implementation."""

from dataclasses import dataclass
from typing import Protocol

from afre.features import FeatureDefinition, FeatureValue
from afre.ids import InstrumentId
from afre.lineage import ProvenanceRef
from afre.schema import Artifact, contract, require


@contract("event_snapshot_ref")
@dataclass(frozen=True, slots=True)
class EventSnapshotRef(Artifact):
    instrument: InstrumentId
    snapshot_id: str
    known_as_of_ns: int
    available_ns: int
    engine_version: str
    schema_versions: tuple[str, ...]
    components: tuple[ProvenanceRef, ...]

    def _normalize(self) -> None:
        self.ordered("components", "fingerprint")
        object.__setattr__(self, "schema_versions", tuple(sorted(self.schema_versions)))

    def _validate(self) -> None:
        require(self.available_ns <= self.known_as_of_ns, "EIE snapshot after requested cutoff")
        require(
            bool(self.components) and bool(self.schema_versions), "snapshot lineage incomplete"
        )
        require(
            len(set(self.schema_versions)) == len(self.schema_versions), "duplicate schemas"
        )


class FeatureProvider(Protocol):
    def get_features(
        self,
        instrument: InstrumentId,
        definitions: tuple[FeatureDefinition, ...],
        known_as_of_ns: int,
    ) -> tuple[FeatureValue, ...]: ...


class MarketDataProvider(FeatureProvider, Protocol):
    """Prices/features must preserve observation, action and publication vintages."""


class EventIntelligenceProvider(Protocol):
    def get_event_snapshot(
        self, instrument: InstrumentId, known_as_of_ns: int
    ) -> EventSnapshotRef | None: ...


class MarketContextProvider(FeatureProvider, Protocol):
    """Optional regime, breadth, correlation and market state boundary."""


class OptionsFeatureProvider(FeatureProvider, Protocol):
    """Optional volatility, skew and surface feature boundary."""


class MicrostructureFeatureProvider(FeatureProvider, Protocol):
    """Optional order flow, spread, depth and queue feature boundary."""

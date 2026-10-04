"""Provider-neutral data contracts; deterministic offline records, no network adapters."""

from dataclasses import dataclass
from typing import Protocol, TypeVar

from afre.feature_store.models import FeatureVintage
from afre.schema import Artifact, require
from afre.time import validate_timestamp
from afre.universe.lifecycle import LifecycleEvent, TradabilityRecord
from afre.universe.listings import ListingRecord, SymbolAssignment
from afre.universe.membership import ConstituentCoverage, UniverseMembershipVintage
from afre.universe.repository import RECORD_TYPES, evidence_of
from afre.universe.securities import IssuerRecord, SecurityRecord

R = TypeVar("R", bound=Artifact)


class UniverseEvidenceProvider(Protocol):
    def records_known_by(self, cutoff_ns: int) -> tuple[Artifact, ...]: ...


class SecurityMasterProvider(Protocol):
    def security_records_known_by(
        self, cutoff_ns: int
    ) -> tuple[IssuerRecord | SecurityRecord, ...]: ...


class ListingProvider(Protocol):
    def listings_known_by(self, cutoff_ns: int) -> tuple[ListingRecord, ...]: ...


class SymbolHistoryProvider(Protocol):
    def symbols_known_by(self, cutoff_ns: int) -> tuple[SymbolAssignment, ...]: ...


class LifecycleProvider(Protocol):
    def lifecycle_known_by(self, cutoff_ns: int) -> tuple[LifecycleEvent, ...]: ...


class ConstituentProvider(Protocol):
    def constituents_known_by(
        self, cutoff_ns: int
    ) -> tuple[ConstituentCoverage | UniverseMembershipVintage, ...]: ...


class TradabilityProvider(Protocol):
    def tradability_known_by(self, cutoff_ns: int) -> tuple[TradabilityRecord, ...]: ...


class EligibilityMarketDataProvider(Protocol):
    def market_features_known_by(self, cutoff_ns: int) -> tuple[FeatureVintage, ...]: ...


@dataclass(frozen=True, slots=True)
class OfflineUniverseProvider:
    records: tuple[Artifact, ...]

    def __post_init__(self) -> None:
        require(
            type(self.records) is tuple
            and all(type(value) in RECORD_TYPES for value in self.records),
            "offline source requires typed universe evidence records",
        )

    def records_known_by(self, cutoff_ns: int) -> tuple[Artifact, ...]:
        validate_timestamp(cutoff_ns)
        return tuple(
            sorted(
                (value for value in self.records if evidence_of(value).known(cutoff_ns)),
                key=lambda x: x.fingerprint,
            )
        )

    def _typed(self, cls: type[R], cutoff_ns: int) -> tuple[R, ...]:
        return tuple(
            value for value in self.records_known_by(cutoff_ns) if isinstance(value, cls)
        )

    def security_records_known_by(
        self, cutoff_ns: int
    ) -> tuple[IssuerRecord | SecurityRecord, ...]:
        return tuple(
            value
            for value in self.records_known_by(cutoff_ns)
            if isinstance(value, (IssuerRecord, SecurityRecord))
        )

    def listings_known_by(self, cutoff_ns: int) -> tuple[ListingRecord, ...]:
        return self._typed(ListingRecord, cutoff_ns)

    def symbols_known_by(self, cutoff_ns: int) -> tuple[SymbolAssignment, ...]:
        return self._typed(SymbolAssignment, cutoff_ns)

    def lifecycle_known_by(self, cutoff_ns: int) -> tuple[LifecycleEvent, ...]:
        return self._typed(LifecycleEvent, cutoff_ns)

    def constituents_known_by(
        self, cutoff_ns: int
    ) -> tuple[ConstituentCoverage | UniverseMembershipVintage, ...]:
        return tuple(
            value
            for value in self.records_known_by(cutoff_ns)
            if isinstance(value, (ConstituentCoverage, UniverseMembershipVintage))
        )

    def tradability_known_by(self, cutoff_ns: int) -> tuple[TradabilityRecord, ...]:
        return self._typed(TradabilityRecord, cutoff_ns)


@dataclass(frozen=True, slots=True)
class OfflineEligibilityMarketProvider:
    vintages: tuple[FeatureVintage, ...]

    def __post_init__(self) -> None:
        require(
            type(self.vintages) is tuple
            and all(type(value) is FeatureVintage for value in self.vintages),
            "market source requires immutable feature vintages",
        )

    def market_features_known_by(self, cutoff_ns: int) -> tuple[FeatureVintage, ...]:
        validate_timestamp(cutoff_ns)
        return tuple(
            sorted(
                (
                    value
                    for value in self.vintages
                    if value.clocks.final_available_ns <= cutoff_ns
                ),
                key=lambda x: x.fingerprint,
            )
        )

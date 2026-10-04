"""Target-only completed observations and compact frozen source manifests."""

from dataclasses import dataclass
from typing import Protocol

from afre.datasets import AdjustmentBasis
from afre.feature_store.models import AvailabilityEvidence, SourceReference
from afre.feature_store.providers import BarTimestampConvention
from afre.features import DataQuality
from afre.ids import InstrumentId, validate_fingerprint
from afre.schema import Artifact, contract, require
from afre.target_engine.corporate_actions import TargetActionStream
from afre.target_engine.schema import TargetObservationState
from afre.target_engine.windows import TargetCalendar
from afre.time import TimeRange


@contract("target_market_source")
@dataclass(frozen=True, slots=True)
class TargetMarketSource(Artifact):
    upstream: SourceReference
    build_version: str
    calendar_id: str
    bar_definition: str
    interval_ns: int
    price_unit: str
    input_basis: AdjustmentBasis = AdjustmentBasis.RAW

    def _validate(self) -> None:
        require(self.interval_ns > 0, "positive target bar interval required")
        require(
            self.input_basis is AdjustmentBasis.RAW,
            "initial target adapter accepts raw inputs; adjustment is explicit target-side",
        )


@contract("target_bar")
@dataclass(frozen=True, slots=True)
class TargetBar(Artifact):
    instrument: InstrumentId
    period: TimeRange
    timestamp_ns: int
    timestamp_convention: BarTimestampConvention
    session_id: str
    close: float | None
    state: TargetObservationState
    quality: DataQuality
    source: TargetMarketSource
    clocks: AvailabilityEvidence
    predecessor_id: str | None = None

    def _validate(self) -> None:
        expected = (
            self.period.start_ns
            if self.timestamp_convention is BarTimestampConvention.OPEN
            else self.period.end_ns
        )
        require(self.timestamp_ns == expected, "ambiguous target bar timestamp convention")
        require(
            self.period.end_ns - self.period.start_ns == self.source.interval_ns,
            "bar period/stream interval mismatch",
        )
        require(
            self.clocks.final_available_ns >= self.period.end_ns,
            "target observation available before completion",
        )
        if self.state is TargetObservationState.VALID:
            require(
                self.close is not None
                and self.close > 0
                and self.quality is not DataQuality.INVALID,
                "invalid/nonpositive valid target price",
            )
        elif self.state is TargetObservationState.NONPOSITIVE_PRICE:
            require(
                self.close is not None
                and self.close <= 0
                and self.quality is DataQuality.INVALID,
                "nonpositive-price state requires invalid raw evidence",
            )
        else:
            require(self.close is None, "absent target print cannot carry a price")
        delivery = self.clocks.historical_delivery
        if delivery is not None:
            require(
                delivery.source_id == self.source.upstream.fingerprint
                and delivery.entity == self.instrument,
                "target bar delivery evidence source/entity mismatch",
            )
        if self.predecessor_id is not None:
            validate_fingerprint(self.predecessor_id, "target_bar")


@contract("target_source_build")
@dataclass(frozen=True, slots=True)
class TargetSourceBuild(Artifact):
    source: TargetMarketSource
    calendar: TargetCalendar
    known_as_of_ns: int
    bar_ids: tuple[str, ...]
    action_stream: TargetActionStream | None = None
    benchmark_ids: tuple[str, ...] = ()

    def _normalize(self) -> None:
        for name in ("bar_ids", "benchmark_ids"):
            values = getattr(self, name)
            require(len(set(values)) == len(values), "duplicate target source vintage")
            object.__setattr__(self, name, tuple(sorted(values)))

    def _validate(self) -> None:
        require(
            self.source.calendar_id == self.calendar.calendar_id, "source/calendar mismatch"
        )
        require(
            self.calendar.clocks.final_available_ns <= self.known_as_of_ns,
            "future source calendar",
        )
        for identity in self.bar_ids:
            validate_fingerprint(identity, "target_bar")
        for identity in self.benchmark_ids:
            validate_fingerprint(identity, "target_benchmark_return")
        if self.action_stream is not None:
            require(
                self.action_stream.clocks.final_available_ns <= self.known_as_of_ns,
                "future action stream in frozen source build",
            )


class TargetMarketDataProvider(Protocol):
    def get_observations(
        self, instrument: InstrumentId, known_as_of_ns: int
    ) -> tuple[TargetBar, ...]: ...

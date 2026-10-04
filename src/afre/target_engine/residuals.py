"""Supplied neutral benchmark returns; no factor estimation."""

from dataclasses import dataclass

from afre.feature_store.models import AvailabilityEvidence
from afre.ids import InstrumentId, validate_fingerprint
from afre.lineage import ProvenanceRef
from afre.schema import Artifact, contract, require
from afre.time import TimeRange


@contract("target_benchmark")
@dataclass(frozen=True, slots=True)
class BenchmarkReference(Artifact):
    instrument: InstrumentId
    dataset_id: str
    name: str
    implementation_version: str

    def _validate(self) -> None:
        validate_fingerprint(self.dataset_id)


@contract("target_benchmark_return")
@dataclass(frozen=True, slots=True)
class SuppliedBenchmarkReturn(Artifact):
    benchmark: BenchmarkReference
    window: TimeRange
    origin_price_ns: int
    endpoint_price_ns: int
    value: float
    clocks: AvailabilityEvidence
    source: ProvenanceRef
    predecessor_id: str | None = None

    def _validate(self) -> None:
        require(self.origin_price_ns < self.endpoint_price_ns, "empty benchmark price interval")
        require(
            self.clocks.final_available_ns >= max(self.window.end_ns, self.endpoint_price_ns),
            "benchmark available before completion",
        )
        require(
            self.clocks.historical_delivery is None,
            "benchmark historical backdating requires a future qualified target contract",
        )
        if self.predecessor_id is not None:
            validate_fingerprint(self.predecessor_id, "target_benchmark_return")

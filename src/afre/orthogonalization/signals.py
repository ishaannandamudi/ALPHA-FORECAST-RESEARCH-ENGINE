"""Receipt-aware neutral scalar evidence and exact origin-bound source observations."""

from dataclasses import dataclass

from afre.feature_store.models import AvailabilityEvidence, SourceReference
from afre.forecast import ForecastOrigin
from afre.ids import validate_fingerprint
from afre.orthogonalization.definitions import SignalReference
from afre.orthogonalization.schema import OrthogonalQuality
from afre.schema import Artifact, contract, require


@contract("ort_generic")
@dataclass(frozen=True, slots=True)
class GenericSignalSource(Artifact):
    reference: SignalReference
    origin: ForecastOrigin
    clocks: AvailabilityEvidence
    source: SourceReference
    value: float | None
    quality: OrthogonalQuality
    revision: str = "1"

    def _validate(self) -> None:
        from afre.orthogonalization.schema import SignalSourceType

        require(
            self.reference.source_type is SignalSourceType.GENERIC,
            "generic scalar definition required",
        )
        require(
            (self.value is not None) == (self.quality is OrthogonalQuality.AVAILABLE),
            "generic quality/value mismatch",
        )
        require(
            self.source.provenance.system == self.reference.provider
            and self.source.provenance.source_version == self.reference.provider_version,
            "generic provider version mismatch",
        )
        if self.clocks.historical_delivery:
            proof = self.clocks.historical_delivery
            require(
                proof.source_id == self.source.fingerprint
                and proof.entity == self.origin.instrument,
                "generic historical delivery exact source/entity",
            )


@contract("ort_observation")
@dataclass(frozen=True, slots=True)
class SignalObservation(Artifact):
    reference_id: str
    source_id: str
    sample_id: str
    origin: ForecastOrigin
    value: float | None
    quality: OrthogonalQuality
    available_ns: int
    approved_attestors: tuple[str, ...] = ()

    def _normalize(self) -> None:
        require(
            len(set(self.approved_attestors)) == len(self.approved_attestors),
            "duplicate attestors",
        )
        object.__setattr__(self, "approved_attestors", tuple(sorted(self.approved_attestors)))

    def _validate(self) -> None:
        validate_fingerprint(self.reference_id, "ort_reference")
        validate_fingerprint(self.source_id)
        validate_fingerprint(self.sample_id, "r_sample")
        require(
            (self.value is not None) == (self.quality is OrthogonalQuality.AVAILABLE),
            "signal quality/value",
        )
        require(
            self.available_ns <= self.origin.availability_cutoff_ns,
            "signal unavailable at origin",
        )

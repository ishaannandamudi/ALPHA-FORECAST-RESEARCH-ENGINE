"""Versioned expert producers and exact native or neutral external forecast bindings."""

from dataclasses import dataclass

from afre.feature_store.models import AvailabilityEvidence, SourceReference
from afre.forecast import ForecastOrigin
from afre.ids import validate_fingerprint
from afre.mixture.schema import ExpertKind, ExpertOutput, ExpertQuality
from afre.probabilistic.artifacts import DistributionParameters
from afre.schema import Artifact, contract, require
from afre.target_engine.definitions import TargetDefinition


@contract("mix_expert")
@dataclass(frozen=True, slots=True)
class ExpertReference(Artifact):
    expert_id: str
    kind: ExpertKind
    provider: str
    provider_version: str
    provider_schema: str
    target: TargetDefinition
    model_id: str
    output: ExpertOutput
    available_ns: int
    source: SourceReference
    quality: ExpertQuality = ExpertQuality.VALID

    def _validate(self) -> None:
        validate_fingerprint(self.model_id)
        require(
            self.output is not ExpertOutput.CALIBRATED_PROBABILISTIC,
            "calibrated marginal expert composition unsupported",
        )
        if self.kind is ExpertKind.AFRE_POINT:
            require(self.output is ExpertOutput.POINT, "point expert output mismatch")
        if self.kind is ExpertKind.AFRE_PROBABILISTIC:
            require(
                self.output is ExpertOutput.PROBABILISTIC, "probability expert output mismatch"
            )


@contract("mix_external_forecast")
@dataclass(frozen=True, slots=True)
class ExternalExpertForecast(Artifact):
    expert: ExpertReference
    origin: ForecastOrigin
    as_of_ns: int
    clocks: AvailabilityEvidence
    source: SourceReference
    quality: ExpertQuality
    point: float | None = None
    distribution: DistributionParameters | None = None
    revision: str = "1"

    def _validate(self) -> None:
        require(self.expert.kind.value.startswith("external_"), "external expert kind required")
        require(self.as_of_ns <= self.origin.timestamp_ns, "external forecast future as-of")
        require(
            self.clocks.final_available_ns >= self.as_of_ns,
            "external availability before as-of",
        )
        if self.clocks.historical_delivery:
            proof = self.clocks.historical_delivery
            require(
                proof.source_id == self.source.fingerprint
                and proof.entity == self.origin.instrument,
                "external reconstruction source/entity mismatch",
            )
        present = self.quality is ExpertQuality.VALID
        require(
            (self.point is not None) == (present and self.expert.output is ExpertOutput.POINT)
            and (self.distribution is not None)
            == (present and self.expert.output is ExpertOutput.PROBABILISTIC),
            "external quality/output payload mismatch",
        )


@contract("mix_binding")
@dataclass(frozen=True, slots=True)
class ExpertForecastBinding(Artifact):
    expert_id: str
    forecast_id: str
    origin: ForecastOrigin
    target_definition_id: str
    available_ns: int
    quality: ExpertQuality
    point: float | None
    distribution: DistributionParameters | None
    sample_id: str | None = None
    as_of_ns: int = 0

    def _validate(self) -> None:
        validate_fingerprint(self.expert_id, "mix_expert")
        validate_fingerprint(self.forecast_id)
        validate_fingerprint(self.target_definition_id, "target_definition")
        if self.sample_id:
            validate_fingerprint(self.sample_id, "r_sample")


@contract("mix_gating_feature")
@dataclass(frozen=True, slots=True)
class GatingFeatureReference(Artifact):
    feature_id: str
    source_id: str
    origin: ForecastOrigin
    available_ns: int
    value: float

    def _validate(self) -> None:
        validate_fingerprint(self.source_id)
        require(
            self.source_id.startswith(
                ("afre.fs_vintage:", "afre.cs_external_signal:", "afre.rc_snapshot:")
            ),
            "gating source must be causal feature/signal/filtered regime data",
        )
        require(
            self.available_ns <= self.origin.availability_cutoff_ns,
            "gating feature unavailable at origin",
        )

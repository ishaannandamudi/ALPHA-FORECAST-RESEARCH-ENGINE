"""Frozen numeric witnesses and outputs; no executable model payloads."""

from dataclasses import dataclass

from afre.forecast import ForecastOrigin
from afre.fusion.probabilistic import FusionDistribution, Law
from afre.fusion.schema import FusionStatus
from afre.ids import validate_fingerprint
from afre.research_datasets.schema import Partition
from afre.schema import Artifact, contract, require
from afre.statistical_models.artifacts import unique_ids
from afre.universe.identity import StableSecurityId


@contract("fus_observation")
@dataclass(frozen=True, slots=True)
class FusionObservation(Artifact):
    source_id: str
    output_id: str
    sample_id: str
    origin: ForecastOrigin
    value: float | None
    law: Law | None
    available_ns: int
    approved_attestors: tuple[str, ...] = ()

    def _normalize(self) -> None:
        object.__setattr__(self, "approved_attestors", tuple(sorted(self.approved_attestors)))

    def _validate(self) -> None:
        for i in (self.source_id, self.output_id, self.sample_id):
            validate_fingerprint(i)
        require(
            self.available_ns <= self.origin.availability_cutoff_ns,
            "fusion source unavailable at origin",
        )


@contract("fus_train_row")
@dataclass(frozen=True, slots=True)
class FusionTrainingRow(Artifact):
    sample_id: str
    observation_ids: tuple[str, ...]
    target_id: str | None
    response: float | None
    values: tuple[float, ...]
    data_available_ns: int

    def _validate(self) -> None:
        validate_fingerprint(self.sample_id, "r_sample")
        unique_ids(self.observation_ids, "fus_observation")
        require(
            0 < len(self.values) == len(self.observation_ids) <= 16, "fusion TRAIN dimensions"
        )
        require((self.target_id is None) == (self.response is None), "TRAIN response witness")
        if self.target_id:
            validate_fingerprint(self.target_id, "target_vintage")


@contract("fus_artifact")
@dataclass(frozen=True, slots=True)
class FusionArtifact(Artifact):
    spec_id: str
    source_ids: tuple[str, ...]
    weights: tuple[tuple[str, float], ...]
    intercept: float
    centers: tuple[float, ...]
    scales: tuple[float, ...]
    rows: tuple[FusionTrainingRow, ...]
    rank: int
    condition_proxy: float | None
    fit_cutoff_ns: int
    computed_ns: int
    available_ns: int
    assumptions: str

    def _normalize(self) -> None:
        self.ordered("rows", "sample_id")

    def _validate(self) -> None:
        validate_fingerprint(self.spec_id, "fus_spec")
        require(
            self.source_ids == tuple(sorted(set(self.source_ids)))
            and tuple(i for i, _ in self.weights) == self.source_ids
            and len(self.centers) == len(self.scales) == len(self.source_ids)
            and all(s > 0 for s in self.scales)
            and len(self.rows) <= 2000,
            "fusion fitted state dimensions",
        )
        require(
            self.fit_cutoff_ns <= self.computed_ns <= self.available_ns
            and all(r.data_available_ns <= self.fit_cutoff_ns for r in self.rows),
            "fusion fitting/availability clocks",
        )


@contract("fus_contribution")
@dataclass(frozen=True, slots=True)
class FusionContribution(Artifact):
    source_id: str
    observation_id: str | None
    output_id: str | None
    original_weight: float
    effective_weight: float
    value: float | None
    weighted_value: float | None
    reason: str

    def _validate(self) -> None:
        require(
            (self.value is None) == (self.weighted_value is None), "contribution missingness"
        )
        require(
            self.value is not None or self.effective_weight == 0.0,
            "missing source cannot contribute",
        )
        if self.value is not None:
            require(
                self.weighted_value == self.effective_weight * self.value,
                "fusion contribution arithmetic",
            )


@contract("fus_forecast")
@dataclass(frozen=True, slots=True)
class FusedForecast(Artifact):
    artifact_id: str
    sample_id: str
    security: StableSecurityId
    origin: ForecastOrigin
    target_id: str
    horizon_id: str
    unit: str
    fold_id: str
    partition: Partition
    observation_ids: tuple[str, ...]
    fallback_observation_id: str | None
    contributions: tuple[FusionContribution, ...]
    intercept_used: float
    status: FusionStatus
    reason: str
    value: float | None
    law: FusionDistribution | None
    computed_ns: int
    available_ns: int

    def _normalize(self) -> None:
        self.ordered("contributions", "source_id")
        unique_ids(self.observation_ids, "fus_observation")
        object.__setattr__(self, "observation_ids", tuple(sorted(self.observation_ids)))

    def _validate(self) -> None:
        for i in (
            self.artifact_id,
            self.sample_id,
            self.target_id,
            self.horizon_id,
            self.fold_id,
        ):
            validate_fingerprint(i)
        require(
            (self.value is not None) == (self.status is FusionStatus.AVAILABLE)
            and (self.law is None or self.value is not None),
            "fused output status",
        )
        require(
            self.security.instrument == self.origin.instrument
            and self.origin.timestamp_ns
            <= self.computed_ns
            <= self.available_ns
            <= self.origin.availability_cutoff_ns,
            "causal fused output clocks/security",
        )


@contract("fus_test_choice")
@dataclass(frozen=True, slots=True)
class FrozenFusionTestChoice(Artifact):
    artifact_id: str
    declared_ns: int
    rationale: str
    selection_policy: str = "single-predeclared-artifact-no-candidate-selection-v1"

    def _validate(self) -> None:
        validate_fingerprint(self.artifact_id, "fus_artifact")
        require(
            self.selection_policy == "single-predeclared-artifact-no-candidate-selection-v1",
            "fusion candidate selection requires explicit AFRE20 adapter (unsupported)",
        )

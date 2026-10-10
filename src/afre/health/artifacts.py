"""Frozen admitted evidence, scalar diagnostics and append-only descriptive snapshots."""

from dataclasses import dataclass

from afre.health.schema import HealthDiagnostic, HealthStatus, ids
from afre.ids import validate_fingerprint
from afre.research_datasets.schema import Partition
from afre.schema import Artifact, contract, require


@contract("hlt_observation")
@dataclass(frozen=True, slots=True)
class HealthObservation(Artifact):
    reference_id: str
    source_id: str
    valid_ns: int
    available_ns: int
    values: tuple[tuple[str, float | None], ...]
    unit: str
    quality: tuple[str, ...]
    sample_id: str | None = None
    security_id: str | None = None
    partition: Partition | None = None
    constructed_ns: int = 0

    def _normalize(self) -> None:
        object.__setattr__(self, "values", tuple(sorted(self.values)))
        object.__setattr__(self, "quality", tuple(sorted(set(self.quality))))

    def _validate(self) -> None:
        for i in (self.reference_id, self.source_id, self.sample_id, self.security_id):
            if i is not None:
                validate_fingerprint(i)
        require(
            len(self.values) <= 256 and len({k for k, _ in self.values}) == len(self.values),
            "health observation columns/duplicates",
        )
        require(
            self.available_ns <= self.constructed_ns,
            "health honest later observation construction",
        )


@contract("hlt_metric")
@dataclass(frozen=True, slots=True)
class HealthMetric(Artifact):
    spec_id: str
    request_id: str
    kind: HealthDiagnostic
    rule_id: str | None
    reference_window_id: str
    current_window_id: str
    reference_observation_ids: tuple[str, ...]
    current_observation_ids: tuple[str, ...]
    reference_sample_ids: tuple[str, ...]
    current_sample_ids: tuple[str, ...]
    reference_count: int
    current_count: int
    reference_value: float | None
    current_value: float | None
    delta: float | None
    ratio: float | None
    score: float | None
    status: HealthStatus
    reason: str
    exclusions: tuple[tuple[str, str], ...]
    quality_states: tuple[str, ...]
    truth_ids: tuple[str, ...]
    details: tuple[tuple[str, float | None], ...]
    cutoff_ns: int
    available_ns: int
    test_evaluation_id: str | None = None
    orientation: str = "descriptive-change-only"

    def _normalize(self) -> None:
        ids(
            self,
            "reference_observation_ids",
            "current_observation_ids",
            "reference_sample_ids",
            "current_sample_ids",
            "truth_ids",
        )
        object.__setattr__(self, "exclusions", tuple(sorted(self.exclusions)))
        object.__setattr__(self, "quality_states", tuple(sorted(set(self.quality_states))))
        object.__setattr__(self, "details", tuple(sorted(self.details)))

    def _validate(self) -> None:
        for i in (
            self.spec_id,
            self.request_id,
            self.reference_window_id,
            self.current_window_id,
            self.rule_id,
            self.test_evaluation_id,
        ):
            if i is not None:
                validate_fingerprint(i)
        require(
            0 <= self.reference_count <= 2000 and 0 <= self.current_count <= 2000,
            "health metric counts",
        )
        require(self.cutoff_ns <= self.available_ns, "health metric computation availability")
        require(len(self.details) <= 2048, "health detail bound")


@contract("hlt_snapshot")
@dataclass(frozen=True, slots=True)
class ModelHealthSnapshot(Artifact):
    spec_id: str
    reference_id: str
    metric_ids: tuple[str, ...]
    rule_ids: tuple[str, ...]
    status: HealthStatus
    cutoff_ns: int
    available_ns: int
    reason: str
    action: str = "NONE_DESCRIPTIVE_ONLY"

    def _normalize(self) -> None:
        ids(self, "metric_ids", "rule_ids")

    def _validate(self) -> None:
        require(
            1 <= len(self.metric_ids) <= 128 and self.cutoff_ns <= self.available_ns,
            "health snapshot bounds/clocks",
        )
        require(self.action == "NONE_DESCRIPTIVE_ONLY", "health has no lifecycle action")


@contract("hlt_trend")
@dataclass(frozen=True, slots=True)
class HealthDecayTrend(Artifact):
    metric_ids: tuple[str, ...]
    slope_per_ns: float | None
    increasing_fraction: float | None
    status: HealthStatus
    reason: str
    available_ns: int

    def _validate(self) -> None:
        require(
            2 <= len(self.metric_ids) <= 64
            and len(set(self.metric_ids)) == len(self.metric_ids),
            "health trend windows bound",
        )

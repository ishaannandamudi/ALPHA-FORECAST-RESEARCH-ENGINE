"""Immutable descriptive evidence and results, each with exact replay inputs."""

from dataclasses import dataclass

from afre.feature_store.models import AvailabilityEvidence, SourceReference
from afre.forecast import ForecastOrigin
from afre.ids import validate_fingerprint
from afre.invariance.schema import (
    ComparabilityStatus,
    EnvironmentState,
    SampleIntersectionPolicy,
    StabilityMetricName,
    canonical_ids,
)
from afre.schema import Artifact, contract, require
from afre.time import TimeRange


@contract("inv_label")
@dataclass(frozen=True, slots=True)
class NeutralEnvironmentLabel(Artifact):
    sample_id: str
    origin: ForecastOrigin
    provider: str
    label: str
    version: str
    validity: TimeRange
    clocks: AvailabilityEvidence
    source: SourceReference

    def _validate(self) -> None:
        validate_fingerprint(self.sample_id, "r_sample")
        require(self.source.provenance.system == self.provider, "label provider/source")
        proof = self.clocks.historical_delivery
        require(
            proof is None
            or proof.source_id == self.source.fingerprint
            and proof.entity == self.origin.instrument,
            "label qualified source/entity",
        )


@contract("inv_membership")
@dataclass(frozen=True, slots=True)
class EnvironmentMembership(Artifact):
    environment_id: str
    sample_id: str
    origin: ForecastOrigin
    source_ids: tuple[str, ...]
    mapping_ids: tuple[str, ...]
    selected_ids: tuple[str, ...]
    state: EnvironmentState
    weight: float
    soft: bool
    reason: str
    evidence_available_ns: int
    constructed_ns: int
    available_ns: int

    def _normalize(self) -> None:
        canonical_ids(self, "source_ids", "mapping_ids", "selected_ids")

    def _validate(self) -> None:
        validate_fingerprint(self.environment_id, "inv_environment")
        validate_fingerprint(self.sample_id, "r_sample")
        require(
            0 <= self.weight <= 1
            and (self.weight > 0) == (self.state is EnvironmentState.INCLUDED),
            "membership weight/state",
        )
        require(self.soft or self.weight in (0.0, 1.0), "hard membership weight")
        require(
            set(self.selected_ids) <= set(self.source_ids) | set(self.mapping_ids),
            "selected exact evidence",
        )
        require(
            self.evidence_available_ns <= self.origin.availability_cutoff_ns
            and self.available_ns >= max(self.constructed_ns, self.evidence_available_ns),
            "membership source/actual construction clocks",
        )


@contract("inv_counts")
@dataclass(frozen=True, slots=True)
class EnvironmentCounts(Artifact):
    eligible: int
    selected: int
    included: int
    excluded: int
    missing: int
    truth_available: int
    effective_count: float

    def _validate(self) -> None:
        require(
            0 <= self.included <= self.selected <= self.eligible
            and self.excluded == self.eligible - self.included
            and 0 <= self.missing <= self.selected
            and 0 <= self.truth_available <= self.selected
            and 0 <= self.effective_count <= self.included + 1e-9,
            "environment counts",
        )


@contract("inv_metric")
@dataclass(frozen=True, slots=True)
class EnvironmentMetric(Artifact):
    spec_id: str
    environment_id: str
    membership_ids: tuple[str, ...]
    comparison_environment_ids: tuple[str, ...]
    name: StabilityMetricName
    value: float | None
    status: ComparabilityStatus
    reason: str
    sample_ids: tuple[str, ...]
    forecast_ids: tuple[str, ...]
    target_ids: tuple[str, ...]
    weights: tuple[tuple[str, float], ...]
    counts: EnvironmentCounts
    target_id: str
    horizon_id: str
    producer_ids: tuple[str, ...]
    minimum_count: int
    truth_cutoff_ns: int
    available_ns: int
    test_evaluation_id: str | None = None
    reliability: tuple[tuple[float, float, int, float | None, float | None], ...] = ()

    def _normalize(self) -> None:
        canonical_ids(
            self,
            "membership_ids",
            "comparison_environment_ids",
            "sample_ids",
            "forecast_ids",
            "target_ids",
            "producer_ids",
        )
        object.__setattr__(self, "weights", tuple(sorted(self.weights)))

    def _validate(self) -> None:
        validate_fingerprint(self.spec_id, "inv_spec")
        validate_fingerprint(self.environment_id, "inv_environment")
        validate_fingerprint(self.target_id, "target_definition")
        validate_fingerprint(self.horizon_id)
        if self.test_evaluation_id:
            validate_fingerprint(self.test_evaluation_id, "r_test_evaluation")
        require(
            (self.value is not None)
            == (
                self.status
                in (ComparabilityStatus.COMPARABLE, ComparabilityStatus.PARTIALLY_COMPARABLE)
            ),
            "metric value/state",
        )
        require(
            tuple(s for s, _ in self.weights) == self.sample_ids
            and len(self.sample_ids) == len(self.forecast_ids) == self.counts.included
            and all(0 < w <= 1 for _, w in self.weights),
            "metric exact intersection/weights",
        )
        require(
            self.minimum_count >= 1 and self.available_ns >= self.truth_cutoff_ns,
            "metric count/availability",
        )


@contract("inv_comparison")
@dataclass(frozen=True, slots=True)
class StabilityComparison(Artifact):
    left_metric_id: str
    right_metric_id: str
    left_spec_id: str
    right_spec_id: str
    environment_ids: tuple[str, str]
    name: StabilityMetricName
    intersection: SampleIntersectionPolicy
    cross_model: bool
    status: ComparabilityStatus
    reason: str
    delta: float | None
    relative_delta: float | None
    available_ns: int

    def _validate(self) -> None:
        for identity in (self.left_metric_id, self.right_metric_id):
            validate_fingerprint(identity, "inv_metric")
        for identity in (self.left_spec_id, self.right_spec_id):
            validate_fingerprint(identity, "inv_spec")
        require(
            (self.delta is not None)
            == (
                self.status
                in (ComparabilityStatus.COMPARABLE, ComparabilityStatus.PARTIALLY_COMPARABLE)
            )
            and (self.delta is not None or self.relative_delta is None),
            "comparison value/status",
        )


@contract("inv_degradation")
@dataclass(frozen=True, slots=True)
class ForecastDegradation(Artifact):
    comparison_id: str
    baseline_environment_id: str
    environment_id: str
    metric: StabilityMetricName
    delta: float | None
    orientation: str
    status: ComparabilityStatus
    available_ns: int

    def _validate(self) -> None:
        validate_fingerprint(self.comparison_id, "inv_comparison")
        require(
            self.orientation in ("higher-is-worse", "lower-is-worse", "descriptive-only"),
            "degradation score orientation",
        )


@contract("inv_distribution")
@dataclass(frozen=True, slots=True)
class DistributionSummary(Artifact):
    sample_ids: tuple[str, ...]
    values: tuple[tuple[str, float | None], ...]
    mean: float | None
    std: float | None
    quantiles: tuple[tuple[float, float | None], ...]
    missing_fraction: float

    def _normalize(self) -> None:
        canonical_ids(self, "sample_ids")
        object.__setattr__(self, "values", tuple(sorted(self.values)))

    def _validate(self) -> None:
        require(
            tuple(s for s, _ in self.values) == self.sample_ids
            and 0 <= self.missing_fraction <= 1
            and (self.mean is None) == (self.std is None),
            "distribution exact samples/missingness",
        )


@contract("inv_shift")
@dataclass(frozen=True, slots=True)
class FeatureShiftDiagnostic(Artifact):
    spec_id: str
    feature_reference_id: str
    environment_ids: tuple[str, str]
    membership_ids: tuple[str, ...]
    observation_ids: tuple[str, ...]
    left: DistributionSummary
    right: DistributionSummary
    status: ComparabilityStatus
    reason: str
    mean_shift: float | None
    std_shift: float | None
    quantile_shifts: tuple[tuple[float, float | None], ...]
    missing_fraction_shift: float
    standardized_mean_difference: float | None
    ks_distance: float | None
    quantile_distance: float | None
    cutoff_ns: int
    available_ns: int

    def _normalize(self) -> None:
        canonical_ids(self, "membership_ids", "observation_ids")

    def _validate(self) -> None:
        validate_fingerprint(self.spec_id, "inv_spec")
        validate_fingerprint(self.feature_reference_id, "ort_reference")
        require(self.available_ns >= self.cutoff_ns, "shift actual availability")


@contract("inv_parameter_record")
@dataclass(frozen=True, slots=True)
class StabilityParameterRecord(Artifact):
    environment_id: str
    artifact_id: str
    family: str
    semantic_key: str
    values: tuple[tuple[str, float], ...]
    status: ComparabilityStatus
    reason: str

    def _normalize(self) -> None:
        require(
            len({n for n, _ in self.values}) == len(self.values), "duplicate parameter name"
        )
        object.__setattr__(self, "values", tuple(sorted(self.values)))


@contract("inv_parameter_summary")
@dataclass(frozen=True, slots=True)
class StabilityParameterSummary(Artifact):
    name: str
    minimum: float
    maximum: float
    mean: float
    median: float
    negative_fraction: float
    zero_fraction: float
    positive_fraction: float
    sign_consistency: float


@contract("inv_model_stability")
@dataclass(frozen=True, slots=True)
class ModelStabilityDiagnostic(Artifact):
    spec_id: str
    assignments: tuple[tuple[str, str], ...]
    raw_scale: bool
    records: tuple[StabilityParameterRecord, ...]
    summaries: tuple[StabilityParameterSummary, ...]
    correlations: tuple[tuple[str, str, float | None], ...]
    status: ComparabilityStatus
    reason: str
    cutoff_ns: int
    available_ns: int

    def _normalize(self) -> None:
        require(
            len(set(self.assignments)) == len(self.assignments),
            "duplicate supplied model assignment",
        )
        object.__setattr__(self, "assignments", tuple(sorted(self.assignments)))
        self.ordered("records", "fingerprint")
        self.ordered("summaries", "name")


@contract("inv_prediction_comparison")
@dataclass(frozen=True, slots=True)
class PredictionStabilityDiagnostic(Artifact):
    left_spec_id: str
    right_spec_id: str
    membership_ids: tuple[str, ...]
    environment_id: str
    sample_ids: tuple[str, ...]
    left_forecast_ids: tuple[str, ...]
    right_forecast_ids: tuple[str, ...]
    pearson: float | None
    spearman: float | None
    mean_absolute_difference: float | None
    sign_agreement: float | None
    top_k_overlap: float | None
    mean_rank_displacement: float | None
    status: ComparabilityStatus
    reason: str
    cutoff_ns: int
    available_ns: int

    def _normalize(self) -> None:
        canonical_ids(
            self, "membership_ids", "sample_ids", "left_forecast_ids", "right_forecast_ids"
        )


@contract("inv_trend")
@dataclass(frozen=True, slots=True)
class StabilityTrend(Artifact):
    spec_id: str
    metric_ids: tuple[str, ...]
    chronological_environment_ids: tuple[str, ...]
    slope_per_nanosecond: float | None
    monotonic: str
    status: ComparabilityStatus
    reason: str
    available_ns: int


@contract("inv_audit")
@dataclass(frozen=True, slots=True)
class StabilityAudit(Artifact):
    root_id: str
    node_ids: tuple[str, ...]
    declarations: tuple[str, ...]

    def _normalize(self) -> None:
        canonical_ids(self, "node_ids")
        object.__setattr__(self, "declarations", tuple(sorted(self.declarations)))

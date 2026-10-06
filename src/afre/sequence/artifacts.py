"""Immutable temporal evidence, fitted state and truth-free forecast outputs."""

from dataclasses import dataclass

from afre.forecast import ForecastOrigin
from afre.ids import InstrumentId, validate_fingerprint
from afre.nonlinear.artifacts import NonlinearProbabilityView
from afre.probabilistic.artifacts import ProbabilityScore
from afre.probabilistic.definitions import ThresholdRequest
from afre.research_datasets.schema import Partition
from afre.schema import Artifact, contract, require
from afre.sequence.schema import (
    SequenceCompleteness,
    SequenceFamily,
    SequenceObservationQuality,
)
from afre.statistical_models.artifacts import PointMetric
from afre.universe.identity import StableSecurityId


def unique_ids(ids: tuple[str, ...], domain: str | None = None) -> None:
    require(len(set(ids)) == len(ids), "duplicate sequence identity")
    for identity in ids:
        validate_fingerprint(identity, domain)


@contract("sq_observation")
@dataclass(frozen=True, slots=True)
class SequenceObservation(Artifact):
    feature_id: str
    source_id: str
    security: InstrumentId
    observation_ns: int
    available_ns: int
    value: float | None
    missing: bool
    revision_id: str
    afre_ready_ns: int
    quality_state: SequenceObservationQuality = SequenceObservationQuality.PRESENT

    def _validate(self) -> None:
        validate_fingerprint(self.feature_id, "sq_feature")
        require(
            self.source_id.startswith(("afre.nl_scalar:", "afre.nl_value:")),
            "closed sequence observation source",
        )
        validate_fingerprint(self.source_id)
        require(self.missing == (self.value is None), "missing observation differs from zero")
        require(
            self.missing == (self.quality_state is not SequenceObservationQuality.PRESENT),
            "sequence observation quality/value agreement",
        )
        validate_fingerprint(self.revision_id)


@contract("sq_snapshot")
@dataclass(frozen=True, slots=True)
class SequenceSnapshot(Artifact):
    origin: ForecastOrigin
    feature_ids: tuple[str, ...]
    window_id: str
    candidate_ids: tuple[str, ...]
    observation_ids: tuple[tuple[str | None, ...], ...]
    observation_times: tuple[int | None, ...]
    values: tuple[tuple[float | None, ...], ...]
    mask: tuple[tuple[bool, ...], ...]
    time_encoding: tuple[float | None, ...]
    completeness: SequenceCompleteness
    exclusions: tuple[tuple[str, str], ...]
    effective_counts: tuple[int, ...]
    oldest_age_seconds: float | None
    newest_age_seconds: float | None
    gap_seconds: tuple[float, ...]
    masked_fraction: float
    computed_ns: int
    available_ns: int

    def _normalize(self) -> None:
        object.__setattr__(self, "candidate_ids", tuple(sorted(self.candidate_ids)))
        object.__setattr__(self, "exclusions", tuple(sorted(self.exclusions)))

    def _validate(self) -> None:
        unique_ids(self.feature_ids, "sq_feature")
        require(self.feature_ids == tuple(sorted(self.feature_ids)), "canonical feature order")
        unique_ids(self.candidate_ids, "sq_observation")
        validate_fingerprint(self.window_id, "sq_window")
        n, p = len(self.values), len(self.feature_ids)
        require(
            1 <= n <= 128
            and 1 <= p <= 16
            and n
            == len(self.observation_times)
            == len(self.mask)
            == len(self.observation_ids)
            == len(self.time_encoding)
            and len(self.effective_counts) == p,
            "sequence snapshot dimensions",
        )
        for values, mask, identities in zip(
            self.values, self.mask, self.observation_ids, strict=True
        ):
            require(
                len(values) == len(mask) == len(identities) == p, "per-feature mask dimensions"
            )
            require(
                all(m == (v is not None) for m, v in zip(mask, values, strict=True)),
                "padding/missing masks are explicit",
            )
            for identity in identities:
                if identity:
                    validate_fingerprint(identity, "sq_observation")
        times = tuple(t for t in self.observation_times if t is not None)
        require(
            all(a < b for a, b in zip(times, times[1:], strict=False))
            and all(0 <= t <= self.origin.availability_cutoff_ns for t in times),
            "sequence temporal order/cutoff",
        )
        require(
            0 <= self.masked_fraction <= 1 and self.available_ns >= self.computed_ns,
            "sequence snapshot availability/diagnostics",
        )


@contract("sq_transform")
@dataclass(frozen=True, slots=True)
class SequenceTransformArtifact(Artifact):
    spec_id: str
    train_bindings: tuple[tuple[str, str], ...]
    centers: tuple[float, ...]
    scales: tuple[float, ...]
    counts: tuple[int, ...]
    cutoff_ns: int
    started_ns: int
    completed_ns: int
    available_ns: int

    def _normalize(self) -> None:
        object.__setattr__(self, "train_bindings", tuple(sorted(self.train_bindings)))

    def _validate(self) -> None:
        validate_fingerprint(self.spec_id, "sq_spec")
        require(
            bool(self.train_bindings)
            and 1 <= len(self.centers) == len(self.scales) == len(self.counts) <= 16
            and all(s > 0 for s in self.scales)
            and all(n > 0 for n in self.counts),
            "sequence fitted transform dimensions",
        )
        require(
            self.cutoff_ns <= self.started_ns <= self.completed_ns <= self.available_ns,
            "sequence transform fit clocks",
        )


@contract("sq_training_row")
@dataclass(frozen=True, slots=True)
class SequenceTrainingRow(Artifact):
    spec_id: str
    sample_id: str
    snapshot_id: str
    target_id: str
    response: float
    available_ns: int

    def _validate(self) -> None:
        for identity, domain in (
            (self.spec_id, "sq_spec"),
            (self.sample_id, "r_sample"),
            (self.snapshot_id, "sq_snapshot"),
            (self.target_id, "target_vintage"),
        ):
            validate_fingerprint(identity, domain)


@contract("sq_dataset")
@dataclass(frozen=True, slots=True)
class SequenceDataset(Artifact):
    spec_id: str
    transform_id: str
    rows: tuple[SequenceTrainingRow, ...]
    fold_id: str
    feature_ids: tuple[str, ...]
    target_id: str
    horizon_id: str
    cutoff_ns: int
    computed_ns: int

    def _normalize(self) -> None:
        self.ordered("rows", "sample_id")

    def _validate(self) -> None:
        for identity, domain in (
            (self.spec_id, "sq_spec"),
            (self.transform_id, "sq_transform"),
            (self.fold_id, "r_fold"),
            (self.target_id, "target_definition"),
        ):
            validate_fingerprint(identity, domain)
        require(
            bool(self.rows)
            and self.cutoff_ns <= self.computed_ns
            and all(r.available_ns <= self.computed_ns for r in self.rows),
            "sequence dataset availability",
        )


@contract("sq_model")
@dataclass(frozen=True, slots=True)
class SequenceModelArtifact(Artifact):
    spec_id: str
    dataset_id: str
    transform_id: str
    train_sample_ids: tuple[str, ...]
    family: SequenceFamily
    intercept: float
    coefficients: tuple[float, ...]
    training_squared_error: float
    qr_rank: int
    condition_proxy: float
    iterations: int
    convergence: str
    cutoff_ns: int
    started_ns: int
    completed_ns: int
    available_ns: int

    def _normalize(self) -> None:
        object.__setattr__(self, "train_sample_ids", tuple(sorted(self.train_sample_ids)))

    def _validate(self) -> None:
        unique_ids(self.train_sample_ids, "r_sample")
        for identity, domain in (
            (self.spec_id, "sq_spec"),
            (self.dataset_id, "sq_dataset"),
            (self.transform_id, "sq_transform"),
        ):
            validate_fingerprint(identity, domain)
        require(
            1 <= len(self.coefficients) <= 16
            and self.training_squared_error >= 0
            and self.qr_rank >= 1
            and self.condition_proxy >= 1
            and self.iterations == 1
            and self.convergence == "direct-QR-solved",
            "bounded direct readout fit",
        )
        require(
            self.cutoff_ns <= self.started_ns <= self.completed_ns <= self.available_ns,
            "sequence model clocks",
        )


@contract("sq_contribution")
@dataclass(frozen=True, slots=True)
class SequenceContribution(Artifact):
    feature_id: str
    observation_id: str
    transformed_value: float
    temporal_weight: float
    readout_coefficient: float
    contribution: float


@contract("sq_forecast")
@dataclass(frozen=True, slots=True)
class SequenceForecast(Artifact):
    model_id: str
    spec_id: str
    snapshot_id: str
    sample_id: str
    origin: ForecastOrigin
    security: StableSecurityId
    target_definition_id: str
    partition: Partition
    value: float
    aggregates: tuple[float, ...]
    contributions: tuple[SequenceContribution, ...]
    state_trajectory: tuple[tuple[float, ...], ...]
    probability: NonlinearProbabilityView | None
    computed_ns: int
    available_ns: int

    def _validate(self) -> None:
        for identity, domain in (
            (self.model_id, "sq_model"),
            (self.spec_id, "sq_spec"),
            (self.snapshot_id, "sq_snapshot"),
            (self.sample_id, "r_sample"),
            (self.target_definition_id, "target_definition"),
        ):
            validate_fingerprint(identity, domain)
        require(
            self.partition in (Partition.VALIDATION, Partition.TEST)
            and self.origin.timestamp_ns
            <= self.computed_ns
            <= self.available_ns
            <= self.origin.availability_cutoff_ns,
            "sequence held-out forecast clocks",
        )


@contract("sq_pair")
@dataclass(frozen=True, slots=True)
class SequenceEvaluationPair(Artifact):
    forecast_id: str
    sample_id: str
    target_id: str
    prediction: float
    truth: float
    baseline_id: str | None
    baseline: float | None
    scores: tuple[ProbabilityScore, ...]


@contract("sq_evaluation")
@dataclass(frozen=True, slots=True)
class SequenceEvaluation(Artifact):
    model_id: str
    forecast_ids: tuple[str, ...]
    pairs: tuple[SequenceEvaluationPair, ...]
    metrics: tuple[PointMetric, ...]
    baseline_metrics: tuple[PointMetric, ...]
    deltas: tuple[PointMetric, ...]
    cohorts: tuple[tuple[str, tuple[PointMetric, ...]], ...]
    proper_scores: tuple[ProbabilityScore, ...]
    thresholds: tuple[ThresholdRequest, ...]
    cutoff_ns: int
    available_ns: int
    test_evaluation_id: str | None

    def _normalize(self) -> None:
        object.__setattr__(self, "forecast_ids", tuple(sorted(self.forecast_ids)))
        self.ordered("pairs", "forecast_id")

    def _validate(self) -> None:
        unique_ids(self.forecast_ids, "sq_forecast")
        require(
            bool(self.forecast_ids) and self.available_ns >= self.cutoff_ns,
            "sequence evaluation clocks",
        )


@contract("sq_stability")
@dataclass(frozen=True, slots=True)
class SequenceStability(Artifact):
    model_ids: tuple[str, ...]
    coefficient_ranges: tuple[tuple[str, float], ...]
    available_ns: int
    policy: str = "descriptive-compatible-fits-no-auto-refit-v1"

    def _normalize(self) -> None:
        object.__setattr__(self, "model_ids", tuple(sorted(self.model_ids)))

    def _validate(self) -> None:
        unique_ids(self.model_ids, "sq_model")
        require(
            len(self.model_ids) >= 2
            and self.policy == "descriptive-compatible-fits-no-auto-refit-v1",
            "sequence stability policy",
        )


@contract("sq_coverage")
@dataclass(frozen=True, slots=True)
class SequenceCoverage(Artifact):
    snapshot_ids: tuple[str, ...]
    counts: tuple[tuple[str, int], ...]
    exclusions: tuple[tuple[str, int], ...]
    available_ns: int

    def _normalize(self) -> None:
        object.__setattr__(self, "snapshot_ids", tuple(sorted(self.snapshot_ids)))


@contract("sq_calibration")
@dataclass(frozen=True, slots=True)
class SequenceCalibrationAssessment(Artifact):
    forecast_id: str
    observation_ids: tuple[str, ...]
    cutoff_ns: int
    minimum_count: int
    proposed_state_id: str | None
    status: str

    def _normalize(self) -> None:
        object.__setattr__(self, "observation_ids", tuple(sorted(self.observation_ids)))

    def _validate(self) -> None:
        unique_ids(self.observation_ids, "sq_forecast")
        require(
            self.minimum_count > 0
            and self.status in ("incompatible", "insufficient", "unavailable"),
            "sequence calibration compatibility state",
        )


@contract("sq_ranking")
@dataclass(frozen=True, slots=True)
class SequenceRanking(Artifact):
    ranking_id: str
    forecast_ids: tuple[str, ...]
    signal_ids: tuple[str, ...]

    def _normalize(self) -> None:
        for field in ("forecast_ids", "signal_ids"):
            object.__setattr__(self, field, tuple(sorted(getattr(self, field))))


@contract("sq_rank_evaluation")
@dataclass(frozen=True, slots=True)
class SequenceRankEvaluation(Artifact):
    ranking_id: str
    matched_id: str
    cross_section_id: str


@contract("sq_audit")
@dataclass(frozen=True, slots=True)
class SequenceAudit(Artifact):
    root_id: str
    node_ids: tuple[str, ...]
    checks: tuple[str, ...]

    def _normalize(self) -> None:
        object.__setattr__(self, "node_ids", tuple(sorted(self.node_ids)))

    def _validate(self) -> None:
        unique_ids(self.node_ids)
        require(self.root_id in self.node_ids, "sequence lineage root")

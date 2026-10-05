"""Immutable matching, independent TRAIN effects, forecasts and matched evaluation."""

from dataclasses import dataclass

from afre.event_conditioned.schema import EventCalibrationStatus
from afre.forecast import ForecastOrigin
from afre.ids import validate_fingerprint
from afre.probabilistic.artifacts import (
    DistributionParameters,
    ProbabilityScore,
    QuantileValue,
    ThresholdProbability,
)
from afre.schema import Artifact, contract, require
from afre.statistical_models.artifacts import PointMetric, unique_ids
from afre.statistical_models.schema import PredictionScope
from afre.universe.identity import StableSecurityId


@contract("ec_matches")
@dataclass(frozen=True, slots=True)
class EventMatchSet(Artifact):
    spec_id: str
    sample_id: str
    event_ids: tuple[str, ...]
    reaction_ids: tuple[str, ...]
    mapping_ids: tuple[str, ...]
    selected_ids: tuple[str, ...]
    excluded: tuple[tuple[str, str], ...]
    distances: tuple[tuple[str, int], ...]
    values: tuple[tuple[str, tuple[tuple[str, float], ...]], ...]
    reaction_refs: tuple[tuple[str, tuple[str, ...]], ...]

    def _normalize(self) -> None:
        for key in (
            "event_ids",
            "reaction_ids",
            "mapping_ids",
            "selected_ids",
            "excluded",
            "distances",
            "values",
            "reaction_refs",
        ):
            object.__setattr__(self, key, tuple(sorted(getattr(self, key))))

    def _validate(self) -> None:
        validate_fingerprint(self.spec_id, "ec_spec")
        validate_fingerprint(self.sample_id, "r_sample")
        unique_ids(self.event_ids, "ec_reference")
        unique_ids(self.selected_ids, "ec_reference")
        unique_ids(self.reaction_ids, "cs_external_signal")
        unique_ids(self.mapping_ids)
        require(set(self.selected_ids) <= set(self.event_ids), "event selection subset")


@contract("ec_observation")
@dataclass(frozen=True, slots=True)
class EventConditionedObservation(Artifact):
    matches_id: str
    spec_id: str
    sample_id: str
    security: StableSecurityId
    origin: ForecastOrigin
    snapshot_id: str
    event_id: str | None
    distance: int | None
    values: tuple[tuple[str, float], ...]
    reaction_ids: tuple[str, ...]
    target_id: str | None
    target_available_ns: int | None
    scope: PredictionScope
    state: str

    def _validate(self) -> None:
        for key, domain in (
            (self.matches_id, "ec_matches"),
            (self.spec_id, "ec_spec"),
            (self.sample_id, "r_sample"),
            (self.snapshot_id, "u_snapshot"),
        ):
            validate_fingerprint(key, domain)
        if self.event_id is not None:
            validate_fingerprint(self.event_id, "ec_reference")
        if self.target_id is not None:
            validate_fingerprint(self.target_id, "target_vintage")
        require(
            self.origin.instrument == self.security.instrument
            and self.state in ("affected", "unaffected"),
            "event observation state",
        )
        require(
            (self.event_id is not None) == (self.state == "affected"),
            "event observation relation",
        )


@contract("ec_model")
@dataclass(frozen=True, slots=True)
class EventConditionedModel(Artifact):
    spec_id: str
    matrix_id: str
    observation_ids: tuple[str, ...]
    excluded_ids: tuple[str, ...]
    feature_keys: tuple[str, ...]
    coefficients: tuple[float, ...]
    class_values: tuple[tuple[str, float, int], ...]
    cutoff_ns: int
    fit_started_ns: int
    fit_completed_ns: int
    available_ns: int
    distinct_sample_count: int

    def _normalize(self) -> None:
        for key in ("observation_ids", "excluded_ids", "class_values"):
            object.__setattr__(self, key, tuple(sorted(getattr(self, key))))

    def _validate(self) -> None:
        validate_fingerprint(self.spec_id, "ec_spec")
        validate_fingerprint(self.matrix_id, "m_matrix")
        unique_ids(self.observation_ids, "ec_observation")
        require(
            self.cutoff_ns <= self.fit_started_ns <= self.fit_completed_ns <= self.available_ns,
            "event fit clocks",
        )
        require(
            not self.coefficients or len(self.coefficients) == len(self.feature_keys) + 1,
            "event coefficient shape",
        )


@contract("ec_forecast")
@dataclass(frozen=True, slots=True)
class EventConditionedForecast(Artifact):
    spec_id: str
    model_id: str
    observation_id: str
    base_forecast_id: str
    origin: ForecastOrigin
    security: StableSecurityId
    target_definition_id: str
    event_ids: tuple[str, ...]
    reaction_ids: tuple[str, ...]
    value: float
    base_value: float
    shift: float
    state: str
    base_probability_id: str | None
    distribution: DistributionParameters | None
    quantiles: tuple[QuantileValue, ...]
    probabilities: tuple[ThresholdProbability, ...]
    computed_ns: int
    available_ns: int
    historical_admissible: bool

    def _validate(self) -> None:
        for key, domain in (
            (self.spec_id, "ec_spec"),
            (self.model_id, "ec_model"),
            (self.observation_id, "ec_observation"),
            (self.base_forecast_id, "m_point_forecast"),
            (self.target_definition_id, "target_definition"),
        ):
            validate_fingerprint(key, domain)
        require(
            self.available_ns >= self.computed_ns >= self.origin.timestamp_ns
            and self.historical_admissible
            and self.available_ns <= self.origin.availability_cutoff_ns,
            "event forecast causal availability",
        )
        require(
            self.state in ("conditioned", "unaffected", "insufficient-class-data"),
            "event forecast state",
        )


@contract("ec_evaluation_pair")
@dataclass(frozen=True, slots=True)
class EventEvaluationPair(Artifact):
    forecast_id: str
    sample_id: str
    target_id: str
    base: float
    conditioned: float
    truth: float


@contract("ec_group_metric")
@dataclass(frozen=True, slots=True)
class EventGroupMetric(Artifact):
    key: str
    sample_ids: tuple[str, ...]
    count: int
    base_metrics: tuple[PointMetric, ...]
    conditioned_metrics: tuple[PointMetric, ...]
    state: str


@contract("ec_evaluation")
@dataclass(frozen=True, slots=True)
class EventConditionedEvaluation(Artifact):
    model_id: str
    forecast_ids: tuple[str, ...]
    pairs: tuple[EventEvaluationPair, ...]
    exclusions: tuple[tuple[str, str], ...]
    base_metrics: tuple[PointMetric, ...]
    conditioned_metrics: tuple[PointMetric, ...]
    deltas: tuple[PointMetric, ...]
    groups: tuple[EventGroupMetric, ...]
    probability_scores: tuple[
        tuple[str, tuple[ProbabilityScore, ...], tuple[ProbabilityScore, ...]], ...
    ]
    test_evaluation_id: str | None
    cutoff_ns: int
    available_ns: int
    affected_count: int
    eligible_count: int
    coverage: float

    def _normalize(self) -> None:
        object.__setattr__(self, "forecast_ids", tuple(sorted(self.forecast_ids)))

    def _validate(self) -> None:
        unique_ids(self.forecast_ids, "ec_forecast")
        require(
            self.available_ns >= self.cutoff_ns
            and self.eligible_count == len(self.forecast_ids)
            and self.coverage
            == (self.affected_count / self.eligible_count if self.eligible_count else 0.0),
            "event evaluation counts/clocks",
        )


@contract("ec_calibration")
@dataclass(frozen=True, slots=True)
class EventCalibrationAssessment(Artifact):
    forecast_id: str
    observation_forecast_ids: tuple[str, ...]
    cutoff_ns: int
    minimum_count: int
    status: EventCalibrationStatus
    reason: str

    def _validate(self) -> None:
        require(
            self.minimum_count >= 2 and self.status is not EventCalibrationStatus.SUPPORTED,
            "event-conditioned calibration fitting unsupported",
        )


@contract("ec_ranking")
@dataclass(frozen=True, slots=True)
class EventRanking(Artifact):
    ranking_id: str
    forecast_ids: tuple[str, ...]
    signal_ids: tuple[str, ...]
    affected_ids: tuple[str, ...]
    unaffected_ids: tuple[str, ...]


@contract("ec_rank_evaluation")
@dataclass(frozen=True, slots=True)
class EventRankEvaluation(Artifact):
    event_ranking_id: str
    matched_evaluation_id: str
    cross_section_evaluation_id: str


@contract("ec_audit")
@dataclass(frozen=True, slots=True)
class EventAudit(Artifact):
    root_id: str
    evidence_ids: tuple[str, ...]
    checks: tuple[str, ...]

    def _normalize(self) -> None:
        object.__setattr__(self, "evidence_ids", tuple(sorted(self.evidence_ids)))

    def _validate(self) -> None:
        unique_ids(self.evidence_ids)
        require(self.root_id in self.evidence_ids, "event audit root")

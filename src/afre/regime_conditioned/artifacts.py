"""Immutable exact matches, TRAIN statistics, transitions and research results."""

from dataclasses import dataclass

from afre.forecast import ForecastOrigin
from afre.ids import validate_fingerprint
from afre.probabilistic.artifacts import (
    DistributionParameters,
    ProbabilityScore,
    QuantileValue,
    ThresholdProbability,
)
from afre.regime_conditioned.memberships import RegimeMembership
from afre.regime_conditioned.schema import RegimeCalibrationStatus
from afre.schema import Artifact, contract, require
from afre.statistical_models.artifacts import PointMetric, unique_ids
from afre.statistical_models.schema import PredictionScope
from afre.universe.identity import StableSecurityId


@contract("rc_matches")
@dataclass(frozen=True, slots=True)
class RegimeMatchSet(Artifact):
    spec_id: str
    sample_id: str
    candidate_ids: tuple[str, ...]
    mapping_ids: tuple[str, ...]
    selected_id: str | None
    admissible_ids: tuple[str, ...]
    exclusions: tuple[tuple[str, str], ...]
    state: str

    def _normalize(self) -> None:
        for key in ("candidate_ids", "mapping_ids", "admissible_ids", "exclusions"):
            object.__setattr__(self, key, tuple(sorted(getattr(self, key))))

    def _validate(self) -> None:
        validate_fingerprint(self.spec_id, "rc_spec")
        validate_fingerprint(self.sample_id, "r_sample")
        unique_ids(self.candidate_ids, "rc_snapshot")
        unique_ids(self.mapping_ids)
        unique_ids(self.admissible_ids, "rc_snapshot")
        require(
            set(self.admissible_ids) <= set(self.candidate_ids)
            and (self.selected_id is None or self.selected_id in self.admissible_ids),
            "regime selection subset",
        )


@contract("rc_transition")
@dataclass(frozen=True, slots=True)
class RegimeTransition(Artifact):
    previous_id: str
    current_id: str
    taxonomy_id: str
    previous: RegimeMembership
    current: RegimeMembership
    transition_ns: int
    available_ns: int
    changed: bool
    probability_mass_change: float

    def _validate(self) -> None:
        for identity in (self.previous_id, self.current_id):
            validate_fingerprint(identity, "rc_snapshot")
        validate_fingerprint(self.taxonomy_id, "rc_taxonomy")
        require(
            self.previous.states == self.current.states
            and self.transition_ns <= self.available_ns
            and self.changed
            == (
                self.previous.kind != self.current.kind
                or self.previous.weights != self.current.weights
            ),
            "regime transition semantics",
        )


@contract("rc_observation")
@dataclass(frozen=True, slots=True)
class RegimeConditionedSample(Artifact):
    matches_id: str
    spec_id: str
    sample_id: str
    security: StableSecurityId
    origin: ForecastOrigin
    universe_snapshot_id: str
    regime_snapshot_id: str | None
    membership: RegimeMembership | None
    target_id: str | None
    target_available_ns: int | None
    scope: PredictionScope
    state: str
    transition_ids: tuple[str, ...]
    elapsed_observed_state_ns: int | None
    transition_status: str

    def _validate(self) -> None:
        for identity, domain in (
            (self.matches_id, "rc_matches"),
            (self.spec_id, "rc_spec"),
            (self.sample_id, "r_sample"),
            (self.universe_snapshot_id, "u_snapshot"),
        ):
            validate_fingerprint(identity, domain)
        unique_ids(self.transition_ids, "rc_transition")
        require(
            (self.regime_snapshot_id is None) == (self.membership is None)
            and self.security.instrument == self.origin.instrument,
            "regime sample binding",
        )
        if self.regime_snapshot_id:
            validate_fingerprint(self.regime_snapshot_id, "rc_snapshot")
        if self.target_id:
            validate_fingerprint(self.target_id, "target_vintage")


@contract("rc_state_fit")
@dataclass(frozen=True, slots=True)
class RegimeStateFit(Artifact):
    state_id: str
    sample_ids: tuple[str, ...]
    weights: tuple[float, ...]
    count: int
    weight_sum: float
    effective_support: float
    value: float | None
    status: str

    def _validate(self) -> None:
        unique_ids(self.sample_ids, "r_sample")
        require(
            self.count == len(self.sample_ids) == len(self.weights)
            and all(w > 0 for w in self.weights),
            "regime state support",
        )


@contract("rc_model")
@dataclass(frozen=True, slots=True)
class RegimeConditionedModel(Artifact):
    spec_id: str
    matrix_id: str
    observation_ids: tuple[str, ...]
    excluded_ids: tuple[str, ...]
    state_fits: tuple[RegimeStateFit, ...]
    global_offset: float
    distinct_sample_count: int
    cutoff_ns: int
    fit_started_ns: int
    fit_completed_ns: int
    available_ns: int

    def _normalize(self) -> None:
        for key in ("observation_ids", "excluded_ids"):
            object.__setattr__(self, key, tuple(sorted(getattr(self, key))))

    def _validate(self) -> None:
        validate_fingerprint(self.spec_id, "rc_spec")
        validate_fingerprint(self.matrix_id, "m_matrix")
        unique_ids(self.observation_ids, "rc_observation")
        require(
            self.cutoff_ns <= self.fit_started_ns <= self.fit_completed_ns <= self.available_ns,
            "regime fit clocks",
        )


@contract("rc_forecast")
@dataclass(frozen=True, slots=True)
class RegimeConditionedForecast(Artifact):
    spec_id: str
    model_id: str
    observation_id: str
    base_forecast_id: str
    origin: ForecastOrigin
    security: StableSecurityId
    target_definition_id: str
    regime_snapshot_id: str | None
    membership: RegimeMembership | None
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
    composition_order: str

    def _validate(self) -> None:
        for identity, domain in (
            (self.spec_id, "rc_spec"),
            (self.model_id, "rc_model"),
            (self.observation_id, "rc_observation"),
            (self.target_definition_id, "target_definition"),
        ):
            validate_fingerprint(identity, domain)
        validate_fingerprint(self.base_forecast_id)
        require(
            self.available_ns >= self.computed_ns >= self.origin.timestamp_ns
            and self.available_ns <= self.origin.availability_cutoff_ns
            and self.historical_admissible,
            "regime forecast causal availability",
        )


@contract("rc_pair")
@dataclass(frozen=True, slots=True)
class RegimeEvaluationPair(Artifact):
    forecast_id: str
    sample_id: str
    target_id: str
    base: float
    conditioned: float
    truth: float


@contract("rc_group")
@dataclass(frozen=True, slots=True)
class RegimeGroupMetric(Artifact):
    key: str
    sample_ids: tuple[str, ...]
    count: int
    base_metrics: tuple[PointMetric, ...]
    conditioned_metrics: tuple[PointMetric, ...]
    state: str


@contract("rc_soft_diagnostic")
@dataclass(frozen=True, slots=True)
class RegimeSoftDiagnostic(Artifact):
    state_id: str
    count: int
    mean_probability: float
    effective_support: float
    weighted_base_mae: float | None
    weighted_conditioned_mae: float | None
    status: str


@contract("rc_evaluation")
@dataclass(frozen=True, slots=True)
class RegimeConditionedEvaluation(Artifact):
    model_id: str
    forecast_ids: tuple[str, ...]
    pairs: tuple[RegimeEvaluationPair, ...]
    exclusions: tuple[tuple[str, str], ...]
    base_metrics: tuple[PointMetric, ...]
    conditioned_metrics: tuple[PointMetric, ...]
    deltas: tuple[PointMetric, ...]
    groups: tuple[RegimeGroupMetric, ...]
    probability_scores: tuple[
        tuple[str, tuple[ProbabilityScore, ...], tuple[ProbabilityScore, ...]], ...
    ]
    soft_diagnostics: tuple[RegimeSoftDiagnostic, ...]
    low_confidence_count: int
    mean_entropy: float | None
    coverage_counts: tuple[tuple[str, int], ...]
    test_evaluation_id: str | None
    cutoff_ns: int
    available_ns: int

    def _normalize(self) -> None:
        object.__setattr__(self, "forecast_ids", tuple(sorted(self.forecast_ids)))

    def _validate(self) -> None:
        unique_ids(self.forecast_ids, "rc_forecast")
        require(self.available_ns >= self.cutoff_ns, "regime evaluation clocks")


@contract("rc_calibration")
@dataclass(frozen=True, slots=True)
class RegimeCalibrationAssessment(Artifact):
    forecast_id: str
    observation_forecast_ids: tuple[str, ...]
    cutoff_ns: int
    minimum_count: int
    status: RegimeCalibrationStatus
    reason: str
    proposed_global_state_id: str | None

    def _validate(self) -> None:
        require(
            self.minimum_count >= 2 and self.status is not RegimeCalibrationStatus.SUPPORTED,
            "regime calibration fitting unsupported",
        )


@contract("rc_drift")
@dataclass(frozen=True, slots=True)
class RegimeDriftDiagnostic(Artifact):
    reference_evaluation_id: str
    current_evaluation_id: str
    state_probability_deltas: tuple[tuple[str, float], ...]
    state_error_deltas: tuple[tuple[str, float | None], ...]
    transition_frequency_delta: float | None
    cutoff_ns: int
    minimum_count: int
    status: str
    policy: str = "descriptive-no-refit-v1"

    def _validate(self) -> None:
        require(
            self.minimum_count >= 2 and self.policy == "descriptive-no-refit-v1",
            "regime drift fixed policy",
        )


@contract("rc_ranking")
@dataclass(frozen=True, slots=True)
class RegimeRanking(Artifact):
    ranking_id: str
    forecast_ids: tuple[str, ...]
    signal_ids: tuple[str, ...]
    matched_ids: tuple[str, ...]
    unmatched_ids: tuple[str, ...]


@contract("rc_rank_evaluation")
@dataclass(frozen=True, slots=True)
class RegimeRankEvaluation(Artifact):
    regime_ranking_id: str
    matched_evaluation_id: str
    cross_section_evaluation_id: str


@contract("rc_audit")
@dataclass(frozen=True, slots=True)
class RegimeAudit(Artifact):
    root_id: str
    evidence_ids: tuple[str, ...]
    checks: tuple[str, ...]

    def _normalize(self) -> None:
        object.__setattr__(self, "evidence_ids", tuple(sorted(self.evidence_ids)))

    def _validate(self) -> None:
        unique_ids(self.evidence_ids)
        require(self.root_id in self.evidence_ids, "regime audit root")

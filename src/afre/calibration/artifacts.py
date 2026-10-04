"""Frozen calibration evidence, transformations, applications and diagnostics."""

from dataclasses import dataclass

from afre.calibration.definitions import CalibrationDriftSpec, CalibrationRequest
from afre.calibration.schema import CalibrationMethod, CalibrationOverlapStatus, DriftState
from afre.forecast import ForecastOrigin
from afre.ids import validate_fingerprint
from afre.probabilistic.artifacts import (
    ProbabilityScore,
    QuantileValue,
    ThresholdProbability,
    validate_quantile_values,
)
from afre.probabilistic.definitions import ProbabilisticEvaluationProtocol, ThresholdRequest
from afre.schema import Artifact, contract, require
from afre.statistical_models.artifacts import MatrixExclusion, PredictionInput, unique_ids


@contract("c_interval_value")
@dataclass(frozen=True, slots=True)
class IntervalValue(Artifact):
    lower_level: float
    upper_level: float
    lower: float
    upper: float

    def _validate(self) -> None:
        require(
            0 < self.lower_level < self.upper_level < 1 and self.lower <= self.upper,
            "invalid calibrated interval",
        )


@contract("c_observation")
@dataclass(frozen=True, slots=True)
class CalibrationObservation(Artifact):
    raw_forecast_id: str
    sample_id: str
    target_id: str
    origin: ForecastOrigin
    target_definition_id: str
    truth: float
    truth_available_ns: int
    raw_available_ns: int
    cutoff_ns: int
    quantiles: tuple[QuantileValue, ...]
    probabilities: tuple[ThresholdProbability, ...]
    median: float
    interval: IntervalValue | None

    def _validate(self) -> None:
        for identity, domain in (
            (self.raw_forecast_id, "p_forecast"),
            (self.sample_id, "r_sample"),
            (self.target_id, "target_vintage"),
            (self.target_definition_id, "target_definition"),
        ):
            validate_fingerprint(identity, domain)
        validate_quantile_values(self.quantiles)
        require(
            self.raw_available_ns <= self.origin.timestamp_ns < self.cutoff_ns
            and self.truth_available_ns <= self.cutoff_ns,
            "noncausal calibration observation",
        )


@contract("c_observations")
@dataclass(frozen=True, slots=True)
class CalibrationObservationSet(Artifact):
    spec_id: str
    requests: tuple[CalibrationRequest, ...]
    rows: tuple[CalibrationObservation, ...]
    exclusions: tuple[MatrixExclusion, ...]

    def _normalize(self) -> None:
        self.ordered("requests", "raw_forecast_id")
        object.__setattr__(
            self,
            "rows",
            tuple(
                sorted(
                    self.rows,
                    key=lambda r: (
                        r.origin.timestamp_ns,
                        r.origin.instrument.fingerprint,
                        r.sample_id,
                    ),
                )
            ),
        )
        self.ordered("exclusions", "sample_id")

    def _validate(self) -> None:
        validate_fingerprint(self.spec_id, "c_spec")
        unique_ids(tuple(r.raw_forecast_id for r in self.requests), "p_forecast")
        unique_ids(tuple(r.sample_id for r in self.rows), "r_sample")
        require(bool(self.rows), "empty calibration evidence")


@contract("c_block")
@dataclass(frozen=True, slots=True)
class IsotonicBlock(Artifact):
    lower: float
    upper: float
    count: int
    successes: int
    probability: float
    observation_ids: tuple[str, ...]

    def _validate(self) -> None:
        require(
            0 <= self.lower <= self.upper <= 1
            and self.count > 0
            and 0 <= self.successes <= self.count
            and self.probability == self.successes / self.count,
            "invalid PAV block",
        )
        unique_ids(self.observation_ids, "c_observation")
        require(self.count == len(self.observation_ids), "PAV weight/evidence mismatch")


@contract("c_bin_value")
@dataclass(frozen=True, slots=True)
class ProbabilityBin(Artifact):
    lower: float
    upper: float
    count: int
    mean_probability: float | None
    observed_frequency: float | None
    calibrated_probability: float | None
    observation_ids: tuple[str, ...]

    def _validate(self) -> None:
        require(0 <= self.lower < self.upper <= 1 and self.count >= 0, "invalid bin bounds")
        unique_ids(self.observation_ids, "c_observation")
        require(self.count == len(self.observation_ids), "bin evidence mismatch")
        for value in (
            self.mean_probability,
            self.observed_frequency,
            self.calibrated_probability,
        ):
            require(value is None or 0 <= value <= 1, "invalid bin probability")
        require(
            (self.mean_probability is None) == (self.count == 0)
            and (self.observed_frequency is None) == (self.count == 0),
            "empty bin statistics",
        )


@contract("c_mapping")
@dataclass(frozen=True, slots=True)
class ProbabilityMapping(Artifact):
    spec_id: str
    observations_id: str
    event: ThresholdRequest
    method: CalibrationMethod
    blocks: tuple[IsotonicBlock, ...] = ()
    bins: tuple[ProbabilityBin, ...] = ()

    def _validate(self) -> None:
        validate_fingerprint(self.spec_id, "c_spec")
        validate_fingerprint(self.observations_id, "c_observations")
        require(
            (
                self.method is CalibrationMethod.ISOTONIC_PROBABILITY
                and bool(self.blocks)
                and not self.bins
            )
            or (
                self.method is CalibrationMethod.BINNED_PROBABILITY
                and bool(self.bins)
                and not self.blocks
            ),
            "mapping representation/method mismatch",
        )
        require(
            all(
                a.upper < b.lower and a.probability <= b.probability
                for a, b in zip(self.blocks, self.blocks[1:], strict=False)
            ),
            "nonmonotone PAV blocks",
        )
        require(
            not self.bins
            or self.bins[0].lower == 0
            and self.bins[-1].upper == 1
            and all(a.upper == b.lower for a, b in zip(self.bins, self.bins[1:], strict=False)),
            "bin map gaps",
        )


@contract("c_offset")
@dataclass(frozen=True, slots=True)
class QuantileOffset(Artifact):
    spec_id: str
    observations_id: str
    level: float
    offset: float
    residuals: tuple[float, ...]
    observation_ids: tuple[str, ...]
    estimator: str = "type7-residual-q-v1"

    def _validate(self) -> None:
        validate_fingerprint(self.spec_id, "c_spec")
        validate_fingerprint(self.observations_id, "c_observations")
        unique_ids(self.observation_ids, "c_observation")
        require(
            0 < self.level < 1
            and bool(self.residuals)
            and len(self.residuals) == len(self.observation_ids)
            and self.residuals == tuple(sorted(self.residuals)),
            "invalid offset evidence",
        )
        require(self.estimator == "type7-residual-q-v1", "unknown residual statistic")


@contract("c_score")
@dataclass(frozen=True, slots=True)
class NonconformityScore(Artifact):
    value: float
    observation_id: str

    def _validate(self) -> None:
        require(self.value >= 0, "negative nonconformity")
        validate_fingerprint(self.observation_id, "c_observation")


@contract("c_conformal")
@dataclass(frozen=True, slots=True)
class ConformalScoreSet(Artifact):
    spec_id: str
    observations_id: str
    alpha: float
    rank: int
    q_hat: float
    scores: tuple[NonconformityScore, ...]
    estimator: str = "ceil-n-plus-one-decimal-alpha-v1"

    def _validate(self) -> None:
        validate_fingerprint(self.spec_id, "c_spec")
        validate_fingerprint(self.observations_id, "c_observations")
        unique_ids(tuple(s.observation_id for s in self.scores), "c_observation")
        require(
            0 < self.alpha < 1
            and 1 <= self.rank <= len(self.scores)
            and self.q_hat == self.scores[self.rank - 1].value
            and self.scores
            == tuple(sorted(self.scores, key=lambda s: (s.value, s.observation_id))),
            "invalid conformal score order/rank",
        )
        require(
            self.estimator == "ceil-n-plus-one-decimal-alpha-v1", "unknown conformal statistic"
        )


@contract("c_reliability_bin")
@dataclass(frozen=True, slots=True)
class ReliabilityBin(Artifact):
    lower: float
    upper: float
    count: int
    mean_probability: float | None
    observed_frequency: float | None
    absolute_gap: float | None


@contract("c_event_diagnostic")
@dataclass(frozen=True, slots=True)
class EventDiagnostic(Artifact):
    event: ThresholdRequest
    count: int
    brier: float | None
    observed_frequency: float | None
    ece: float | None
    mce: float | None
    bins: tuple[ReliabilityBin, ...]


@contract("c_quantile_diagnostic")
@dataclass(frozen=True, slots=True)
class QuantileDiagnostic(Artifact):
    level: float
    count: int
    observed_frequency: float | None
    signed_gap: float | None
    absolute_gap: float | None


@contract("c_interval_diagnostic")
@dataclass(frozen=True, slots=True)
class IntervalDiagnostic(Artifact):
    nominal_coverage: float
    count: int
    coverage: float | None
    signed_gap: float | None
    absolute_gap: float | None
    mean_width: float | None


@contract("c_diagnostics")
@dataclass(frozen=True, slots=True)
class CalibrationDiagnostics(Artifact):
    context: str
    raw_events: tuple[EventDiagnostic, ...]
    calibrated_events: tuple[EventDiagnostic, ...]
    raw_quantiles: tuple[QuantileDiagnostic, ...]
    calibrated_quantiles: tuple[QuantileDiagnostic, ...]
    raw_interval: IntervalDiagnostic | None
    calibrated_interval: IntervalDiagnostic | None

    def _validate(self) -> None:
        require(
            self.context in ("fit-same-sample-retrospective", "independent-evaluation"),
            "diagnostic context",
        )


@contract("c_fit_inputs")
@dataclass(frozen=True, slots=True)
class CalibrationFitInputs(Artifact):
    spec_id: str
    raw_model_id: str
    observations_id: str
    sample_ids: tuple[str, ...]
    overlap: CalibrationOverlapStatus
    cutoff_ns: int
    fit_started_ns: int
    fit_completed_ns: int
    available_ns: int

    def _validate(self) -> None:
        for identity, domain in (
            (self.spec_id, "c_spec"),
            (self.raw_model_id, "p_artifact"),
            (self.observations_id, "c_observations"),
        ):
            validate_fingerprint(identity, domain)
        unique_ids(self.sample_ids, "r_sample")
        require(
            bool(self.sample_ids)
            and self.cutoff_ns
            <= self.fit_started_ns
            <= self.fit_completed_ns
            <= self.available_ns,
            "calibration fit clocks/evidence",
        )


@contract("c_state")
@dataclass(frozen=True, slots=True)
class CalibrationState(Artifact):
    inputs: CalibrationFitInputs
    target_definition_id: str
    mapping_ids: tuple[str, ...]
    offset_ids: tuple[str, ...]
    conformal_id: str | None
    diagnostics_id: str

    def _normalize(self) -> None:
        object.__setattr__(self, "mapping_ids", tuple(sorted(self.mapping_ids)))
        object.__setattr__(self, "offset_ids", tuple(sorted(self.offset_ids)))

    def _validate(self) -> None:
        validate_fingerprint(self.target_definition_id, "target_definition")
        unique_ids(self.mapping_ids, "c_mapping")
        unique_ids(self.offset_ids, "c_offset")
        if self.conformal_id is not None:
            validate_fingerprint(self.conformal_id, "c_conformal")
        validate_fingerprint(self.diagnostics_id, "c_diagnostics")


@contract("c_fit_run")
@dataclass(frozen=True, slots=True)
class CalibrationFitRun(Artifact):
    inputs: CalibrationFitInputs
    state_id: str
    diagnostics_id: str

    def _validate(self) -> None:
        validate_fingerprint(self.state_id, "c_state")
        validate_fingerprint(self.diagnostics_id, "c_diagnostics")


@contract("c_forecast")
@dataclass(frozen=True, slots=True)
class CalibratedForecast(Artifact):
    raw_forecast_id: str
    state_id: str
    target_definition_id: str
    input: PredictionInput
    quantiles: tuple[QuantileValue, ...]
    probabilities: tuple[ThresholdProbability, ...]
    raw_interval: IntervalValue | None
    calibrated_interval: IntervalValue | None
    full_distribution_preserved: bool
    calibration_available_ns: int
    computed_ns: int
    available_ns: int
    historical_admissible: bool

    def _validate(self) -> None:
        for identity, domain in (
            (self.raw_forecast_id, "p_forecast"),
            (self.state_id, "c_state"),
            (self.target_definition_id, "target_definition"),
        ):
            validate_fingerprint(identity, domain)
        validate_quantile_values(self.quantiles)
        require(
            len({p.request for p in self.probabilities}) == len(self.probabilities),
            "duplicate calibrated events",
        )
        require(
            self.computed_ns
            >= max(self.input.origin.timestamp_ns, self.calibration_available_ns)
            and self.available_ns >= self.computed_ns,
            "calibrated forecast clocks",
        )
        require(
            self.historical_admissible
            and self.calibration_available_ns <= self.input.origin.timestamp_ns,
            "calibration unavailable at origin",
        )


@contract("c_scored_pair")
@dataclass(frozen=True, slots=True)
class CalibrationScoredPair(Artifact):
    calibrated_forecast_id: str
    raw_forecast_id: str
    sample_id: str
    target_id: str
    origin_ns: int
    security_id: str
    truth: float
    raw_scores: tuple[ProbabilityScore, ...]
    calibrated_scores: tuple[ProbabilityScore, ...]


@contract("c_evaluation")
@dataclass(frozen=True, slots=True)
class CalibrationEvaluation(Artifact):
    state_id: str
    raw_evaluation_id: str
    forecast_ids: tuple[str, ...]
    pairs: tuple[CalibrationScoredPair, ...]
    raw_scores: tuple[ProbabilityScore, ...]
    calibrated_scores: tuple[ProbabilityScore, ...]
    diagnostics: CalibrationDiagnostics
    protocol: ProbabilisticEvaluationProtocol
    cutoff_ns: int
    available_ns: int

    def _normalize(self) -> None:
        object.__setattr__(self, "forecast_ids", tuple(sorted(self.forecast_ids)))

    def _validate(self) -> None:
        validate_fingerprint(self.state_id, "c_state")
        validate_fingerprint(self.raw_evaluation_id, "p_evaluation")
        unique_ids(self.forecast_ids, "c_forecast")
        require(
            bool(self.forecast_ids) and self.available_ns >= self.cutoff_ns,
            "evaluation clocks/forecasts",
        )


@contract("c_delta")
@dataclass(frozen=True, slots=True)
class CalibrationDelta(Artifact):
    raw: ProbabilityScore
    calibrated: ProbabilityScore
    delta: float | None


@contract("c_comparison")
@dataclass(frozen=True, slots=True)
class CalibrationComparison(Artifact):
    raw_evaluation_id: str
    calibrated_evaluation_id: str
    deltas: tuple[CalibrationDelta, ...]
    coverage_error_delta: float | None
    interval_width_delta: float | None

    def _validate(self) -> None:
        validate_fingerprint(self.raw_evaluation_id, "p_evaluation")
        validate_fingerprint(self.calibrated_evaluation_id, "c_evaluation")


@contract("c_drift_window")
@dataclass(frozen=True, slots=True)
class CalibrationDriftWindow(Artifact):
    evaluation_ids: tuple[str, ...]
    cutoff_ns: int
    count: int
    value: float | None
    state: DriftState


@contract("c_drift")
@dataclass(frozen=True, slots=True)
class CalibrationDriftDiagnostics(Artifact):
    spec: CalibrationDriftSpec
    state_id: str
    evaluation_ids: tuple[str, ...]
    windows: tuple[CalibrationDriftWindow, ...]

    def _validate(self) -> None:
        validate_fingerprint(self.state_id, "c_state")
        unique_ids(self.evaluation_ids, "c_evaluation")
        require(
            bool(self.evaluation_ids) and len(self.windows) == len(self.evaluation_ids),
            "empty or inconsistent drift history",
        )


@contract("c_audit")
@dataclass(frozen=True, slots=True)
class CalibrationLineageAudit(Artifact):
    root_id: str
    evidence_ids: tuple[str, ...]
    checks: tuple[str, ...]

    def _normalize(self) -> None:
        object.__setattr__(self, "evidence_ids", tuple(sorted(self.evidence_ids)))

    def _validate(self) -> None:
        validate_fingerprint(self.root_id)
        unique_ids(self.evidence_ids)
        require(self.root_id in self.evidence_ids, "audit root missing")

"""Immutable training evidence, uncertainty state, distributions and proper scores."""

from dataclasses import dataclass

from afre.ids import validate_fingerprint
from afre.probabilistic.definitions import ProbabilisticEvaluationProtocol, ThresholdRequest
from afre.probabilistic.schema import (
    DistributionFamily,
    DistributionState,
    ScoreName,
    ScoreState,
)
from afre.schema import Artifact, contract, require
from afre.statistical_models.artifacts import MatrixExclusion, PredictionInput, unique_ids
from afre.statistical_models.schema import PredictionScope


@contract("p_observation")
@dataclass(frozen=True, slots=True)
class TrainingObservation(Artifact):
    sample_id: str
    target_id: str
    origin_ns: int
    security_id: str
    response: float
    point_value: float | None
    value: float
    data_available_ns: int

    def _validate(self) -> None:
        validate_fingerprint(self.sample_id, "r_sample")
        validate_fingerprint(self.target_id, "target_vintage")
        validate_fingerprint(self.security_id, "instrument")


@contract("p_observations")
@dataclass(frozen=True, slots=True)
class TrainingObservations(Artifact):
    spec_id: str
    matrix_id: str
    rows: tuple[TrainingObservation, ...]

    def _normalize(self) -> None:
        object.__setattr__(
            self,
            "rows",
            tuple(sorted(self.rows, key=lambda r: (r.origin_ns, r.security_id, r.sample_id))),
        )

    def _validate(self) -> None:
        validate_fingerprint(self.spec_id, "p_spec")
        validate_fingerprint(self.matrix_id, "m_matrix")
        require(bool(self.rows), "empty TRAIN probability evidence")
        unique_ids(tuple(r.sample_id for r in self.rows), "r_sample")


@contract("p_fit_inputs")
@dataclass(frozen=True, slots=True)
class ProbabilisticFitInputs(Artifact):
    spec_id: str
    point_model_id: str
    point_fit_inputs_id: str
    observations_id: str
    matrix_id: str
    dataset_id: str
    split_id: str
    fold_id: str
    target_definition_id: str
    train_sample_ids: tuple[str, ...]
    preprocessing_state_ids: tuple[str, ...]
    training_cutoff_ns: int
    fit_started_ns: int
    fit_completed_ns: int
    available_ns: int

    def _validate(self) -> None:
        for identity, domain in (
            (self.spec_id, "p_spec"),
            (self.point_model_id, "m_artifact"),
            (self.point_fit_inputs_id, "m_fit_inputs"),
            (self.observations_id, "p_observations"),
            (self.matrix_id, "m_matrix"),
            (self.dataset_id, "r_dataset"),
            (self.split_id, "r_split"),
            (self.fold_id, "r_fold"),
            (self.target_definition_id, "target_definition"),
        ):
            validate_fingerprint(identity, domain)
        unique_ids(self.train_sample_ids, "r_sample")
        unique_ids(self.preprocessing_state_ids, "r_preprocessing_state")
        require(bool(self.train_sample_ids), "probability fit needs TRAIN samples")
        require(
            self.training_cutoff_ns
            <= self.fit_started_ns
            <= self.fit_completed_ns
            <= self.available_ns,
            "probability fit clocks out of order",
        )


@contract("p_diagnostics")
@dataclass(frozen=True, slots=True)
class ProbabilisticFitDiagnostics(Artifact):
    sample_count: int
    raw_mean: float
    centering_shift: float
    distribution_mean: float
    distribution_median: float
    population_stddev: float
    median_absolute_deviation: float
    estimated_scale: float
    degenerate_observations: bool

    def _validate(self) -> None:
        require(
            self.sample_count > 0
            and min(
                self.population_stddev, self.median_absolute_deviation, self.estimated_scale
            )
            >= 0,
            "invalid probability diagnostics",
        )


@contract("p_training_distribution")
@dataclass(frozen=True, slots=True)
class TrainingDistribution(Artifact):
    spec_id: str
    observations_id: str
    sample_ids: tuple[str, ...]
    values: tuple[float, ...]
    diagnostics: ProbabilisticFitDiagnostics
    available_ns: int

    def _normalize(self) -> None:
        object.__setattr__(self, "values", tuple(sorted(self.values)))

    def _validate(self) -> None:
        validate_fingerprint(self.spec_id, "p_spec")
        validate_fingerprint(self.observations_id, "p_observations")
        unique_ids(self.sample_ids, "r_sample")
        require(
            bool(self.values)
            and len(self.values) == len(self.sample_ids) == self.diagnostics.sample_count,
            "probability distribution evidence shape",
        )


@contract("p_artifact")
@dataclass(frozen=True, slots=True)
class ProbabilisticModelArtifact(Artifact):
    spec_id: str
    fit_inputs_id: str
    distribution_id: str
    family: DistributionFamily
    location_offset: float
    scale: float
    diagnostics_id: str
    approximation_version: str
    available_ns: int

    def _validate(self) -> None:
        for identity, domain in (
            (self.spec_id, "p_spec"),
            (self.fit_inputs_id, "p_fit_inputs"),
            (self.distribution_id, "p_training_distribution"),
            (self.diagnostics_id, "p_diagnostics"),
        ):
            validate_fingerprint(identity, domain)
        require(
            self.scale >= 0
            and (
                self.family is not DistributionFamily.GAUSSIAN_LOCATION_SCALE or self.scale > 0
            ),
            "invalid probabilistic artifact scale",
        )


@contract("p_fit_run")
@dataclass(frozen=True, slots=True)
class ProbabilisticFitRun(Artifact):
    inputs: ProbabilisticFitInputs
    artifact_id: str
    distribution_id: str
    diagnostics_id: str

    def _validate(self) -> None:
        validate_fingerprint(self.artifact_id, "p_artifact")
        validate_fingerprint(self.distribution_id, "p_training_distribution")
        validate_fingerprint(self.diagnostics_id, "p_diagnostics")


@contract("p_quantile_value")
@dataclass(frozen=True, slots=True)
class QuantileValue(Artifact):
    level: float
    value: float

    def _validate(self) -> None:
        require(0 < self.level < 1, "quantile level outside interior")


def validate_quantile_values(values: tuple[QuantileValue, ...]) -> None:
    require(
        bool(values) and 0.5 in {q.level for q in values}, "explicit forecast median required"
    )
    require(len({q.level for q in values}) == len(values), "duplicate forecast quantile")
    require(
        all(
            a.level < b.level and a.value <= b.value
            for a, b in zip(values, values[1:], strict=False)
        ),
        "crossing or unordered forecast quantiles",
    )


@contract("p_parameters")
@dataclass(frozen=True, slots=True)
class DistributionParameters(Artifact):
    family: DistributionFamily
    location: float
    scale: float
    samples: tuple[float, ...] = ()
    quantile_values: tuple[QuantileValue, ...] = ()
    state: DistributionState = DistributionState.REGULAR

    def _normalize(self) -> None:
        object.__setattr__(self, "samples", tuple(sorted(self.samples)))
        self.ordered("quantile_values", "level")

    def _validate(self) -> None:
        require(self.scale >= 0, "negative distribution scale")
        if self.family is DistributionFamily.GAUSSIAN_LOCATION_SCALE:
            require(
                self.scale > 0
                and not self.samples
                and not self.quantile_values
                and self.state is DistributionState.REGULAR,
                "Gaussian requires positive continuous scale",
            )
        elif self.family is DistributionFamily.EMPIRICAL_RESIDUAL:
            require(
                bool(self.samples) and not self.quantile_values,
                "empirical distribution requires samples only",
            )
            require(
                (self.state is DistributionState.DEGENERATE)
                == (min(self.samples) == max(self.samples)),
                "empirical degeneracy state mismatch",
            )
        else:
            require(not self.samples, "quantile-only cannot advertise atoms")
            validate_quantile_values(self.quantile_values)
            require(
                (self.state is DistributionState.DEGENERATE)
                == (self.quantile_values[0].value == self.quantile_values[-1].value),
                "quantile degeneracy state mismatch",
            )


@contract("p_threshold_probability")
@dataclass(frozen=True, slots=True)
class ThresholdProbability(Artifact):
    request: ThresholdRequest
    probability: float

    def _validate(self) -> None:
        require(0 <= self.probability <= 1, "probability outside unit interval")


@contract("p_forecast")
@dataclass(frozen=True, slots=True)
class ProbabilisticForecast(Artifact):
    model_artifact_id: str
    point_forecast_id: str
    target_definition_id: str
    input: PredictionInput
    distribution: DistributionParameters
    quantiles: tuple[QuantileValue, ...]
    threshold_probabilities: tuple[ThresholdProbability, ...]
    expected_value: float | None
    median_value: float
    conditional_variance: float | None
    model_available_ns: int
    computed_ns: int
    available_ns: int
    historical_admissible: bool

    def _normalize(self) -> None:
        self.ordered("quantiles", "level")
        object.__setattr__(
            self,
            "threshold_probabilities",
            tuple(
                sorted(
                    self.threshold_probabilities,
                    key=lambda p: (p.request.value, p.request.comparison.value),
                )
            ),
        )

    def _validate(self) -> None:
        validate_fingerprint(self.model_artifact_id, "p_artifact")
        validate_fingerprint(self.point_forecast_id, "m_point_forecast")
        validate_fingerprint(self.target_definition_id, "target_definition")
        validate_quantile_values(self.quantiles)
        require(
            len({p.request for p in self.threshold_probabilities})
            == len(self.threshold_probabilities),
            "duplicate forecast thresholds",
        )
        require(
            self.conditional_variance is None or self.conditional_variance >= 0,
            "negative conditional variance",
        )
        require(
            self.historical_admissible == (self.input.scope is not PredictionScope.IN_SAMPLE),
            "TRAIN diagnostics are retrospective",
        )
        require(
            not self.historical_admissible
            or self.model_available_ns <= self.input.origin.availability_cutoff_ns,
            "probabilistic model unavailable at origin",
        )
        require(
            self.computed_ns >= self.input.origin.timestamp_ns
            and self.available_ns >= max(self.computed_ns, self.model_available_ns),
            "probabilistic forecast backdated",
        )


@contract("p_score")
@dataclass(frozen=True, slots=True)
class ProbabilityScore(Artifact):
    name: ScoreName
    value: float | None
    state: ScoreState
    sample_count: int
    level: float | None = None
    upper_level: float | None = None
    threshold: ThresholdRequest | None = None

    def _validate(self) -> None:
        require(
            self.sample_count >= 0
            and (self.value is not None) == (self.state is ScoreState.AVAILABLE),
            "score count/value/state mismatch",
        )
        require(self.level is None or 0 < self.level < 1, "score quantile domain")
        require(
            self.upper_level is None
            or (self.level is not None and self.level < self.upper_level < 1),
            "score interval domain",
        )

    @property
    def key(self) -> tuple[str, float, float, str]:
        return (
            self.name.value,
            self.level or 0.0,
            self.upper_level or 0.0,
            self.threshold.fingerprint if self.threshold else "",
        )


@contract("p_scored_pair")
@dataclass(frozen=True, slots=True)
class ProbabilisticScoredPair(Artifact):
    forecast_id: str
    sample_id: str
    target_id: str
    origin_ns: int
    security_id: str
    truth: float
    pit: float | None
    scores: tuple[ProbabilityScore, ...]

    def _normalize(self) -> None:
        object.__setattr__(self, "scores", tuple(sorted(self.scores, key=lambda s: s.key)))

    def _validate(self) -> None:
        for identity, domain in (
            (self.forecast_id, "p_forecast"),
            (self.sample_id, "r_sample"),
            (self.target_id, "target_vintage"),
            (self.security_id, "instrument"),
        ):
            validate_fingerprint(identity, domain)
        require(self.pit is None or 0 <= self.pit <= 1, "invalid PIT")
        require(len({s.key for s in self.scores}) == len(self.scores), "duplicate scores")


@contract("p_origin_scores")
@dataclass(frozen=True, slots=True)
class OriginProbabilityScores(Artifact):
    origin_ns: int
    scores: tuple[ProbabilityScore, ...]


@contract("p_evaluation")
@dataclass(frozen=True, slots=True)
class ProbabilisticEvaluation(Artifact):
    model_artifact_id: str
    dataset_id: str
    fold_id: str
    target_definition_id: str
    scope: PredictionScope
    forecast_ids: tuple[str, ...]
    pairs: tuple[ProbabilisticScoredPair, ...]
    exclusions: tuple[MatrixExclusion, ...]
    scores: tuple[ProbabilityScore, ...]
    origin_scores: tuple[OriginProbabilityScores, ...]
    pit_histogram: tuple[int, ...]
    protocol: ProbabilisticEvaluationProtocol
    evaluation_cutoff_ns: int
    available_ns: int
    test_evaluation_id: str | None

    def _normalize(self) -> None:
        object.__setattr__(self, "forecast_ids", tuple(sorted(self.forecast_ids)))
        object.__setattr__(
            self,
            "pairs",
            tuple(sorted(self.pairs, key=lambda p: (p.origin_ns, p.security_id, p.sample_id))),
        )
        self.ordered("exclusions", "sample_id")
        self.ordered("origin_scores", "origin_ns")
        object.__setattr__(self, "scores", tuple(sorted(self.scores, key=lambda s: s.key)))

    def _validate(self) -> None:
        for identity, domain in (
            (self.model_artifact_id, "p_artifact"),
            (self.dataset_id, "r_dataset"),
            (self.fold_id, "r_fold"),
            (self.target_definition_id, "target_definition"),
        ):
            validate_fingerprint(identity, domain)
        unique_ids(self.forecast_ids, "p_forecast")
        unique_ids(tuple(p.sample_id for p in self.pairs), "r_sample")
        require(
            bool(self.forecast_ids)
            and {p.forecast_id for p in self.pairs} <= set(self.forecast_ids),
            "evaluation forecast evidence",
        )
        require(
            len(self.pit_histogram) == self.protocol.pit_bins
            and all(n >= 0 for n in self.pit_histogram),
            "PIT histogram shape",
        )
        require(self.available_ns >= self.evaluation_cutoff_ns, "evaluation before cutoff")
        require(
            (self.test_evaluation_id is not None) == (self.scope is PredictionScope.TEST),
            "TEST probability evaluation requires reuse record",
        )
        if self.test_evaluation_id:
            validate_fingerprint(self.test_evaluation_id, "r_test_evaluation")


@contract("p_comparison")
@dataclass(frozen=True, slots=True)
class ProbabilisticComparison(Artifact):
    candidate_evaluation_id: str
    reference_evaluation_id: str
    sample_ids: tuple[str, ...]
    deltas: tuple[ProbabilityScore, ...]

    def _normalize(self) -> None:
        object.__setattr__(self, "sample_ids", tuple(sorted(self.sample_ids)))
        object.__setattr__(self, "deltas", tuple(sorted(self.deltas, key=lambda s: s.key)))

    def _validate(self) -> None:
        validate_fingerprint(self.candidate_evaluation_id, "p_evaluation")
        validate_fingerprint(self.reference_evaluation_id, "p_evaluation")
        unique_ids(self.sample_ids, "r_sample")
        require(bool(self.sample_ids), "comparison needs exact common samples")


@contract("p_audit")
@dataclass(frozen=True, slots=True)
class ProbabilisticLineageAudit(Artifact):
    root_id: str
    evidence_ids: tuple[str, ...]
    checks: tuple[str, ...]

    def _normalize(self) -> None:
        object.__setattr__(self, "evidence_ids", tuple(sorted(self.evidence_ids)))
        object.__setattr__(self, "checks", tuple(sorted(self.checks)))

    def _validate(self) -> None:
        validate_fingerprint(self.root_id)
        unique_ids(self.evidence_ids)
        require(len(set(self.checks)) == len(self.checks), "duplicate probability audit check")

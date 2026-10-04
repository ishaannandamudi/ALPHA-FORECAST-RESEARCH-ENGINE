"""Immutable, data-only fit inputs, coefficients, forecasts and evaluation evidence."""

from dataclasses import dataclass

from afre.forecast import ForecastOrigin
from afre.ids import validate_fingerprint
from afre.schema import Artifact, contract, require
from afre.statistical_models.schema import (
    MetricName,
    MetricState,
    PredictionScope,
    SolverIdentity,
)


def unique_ids(values: tuple[str, ...], domain: str | None = None) -> None:
    require(len(set(values)) == len(values), "duplicate model evidence")
    for value in values:
        validate_fingerprint(value, domain)


@contract("m_matrix_row")
@dataclass(frozen=True, slots=True)
class TrainingMatrixRow(Artifact):
    sample_id: str
    origin: ForecastOrigin
    join_id: str
    feature_vintage_ids: tuple[str, ...]
    values: tuple[float, ...]
    target_id: str
    response: float
    data_available_ns: int

    def _validate(self) -> None:
        validate_fingerprint(self.sample_id, "r_sample")
        validate_fingerprint(self.join_id, "fs_join_result")
        validate_fingerprint(self.target_id, "target_vintage")
        unique_ids(self.feature_vintage_ids, "fs_vintage")


@contract("m_matrix_exclusion")
@dataclass(frozen=True, slots=True)
class MatrixExclusion(Artifact):
    sample_id: str
    reason: str

    def _validate(self) -> None:
        validate_fingerprint(self.sample_id, "r_sample")


@contract("m_matrix")
@dataclass(frozen=True, slots=True)
class DesignMatrix(Artifact):
    spec_id: str
    dataset_id: str
    split_id: str
    fold_id: str
    target_definition_id: str
    feature_ids: tuple[str, ...]
    rows: tuple[TrainingMatrixRow, ...]
    exclusions: tuple[MatrixExclusion, ...]
    preprocessing_state_ids: tuple[str, ...]
    training_cutoff_ns: int
    transformed_ns: int

    def _normalize(self) -> None:
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
        for identity, domain in (
            (self.spec_id, "m_spec"),
            (self.dataset_id, "r_dataset"),
            (self.split_id, "r_split"),
            (self.fold_id, "r_fold"),
            (self.target_definition_id, "target_definition"),
        ):
            validate_fingerprint(identity, domain)
        unique_ids(self.feature_ids, "feature_definition")
        unique_ids(self.preprocessing_state_ids, "r_preprocessing_state")
        require(bool(self.rows), "empty training matrix")
        unique_ids(tuple(r.sample_id for r in self.rows), "r_sample")
        require(
            not {r.sample_id for r in self.rows} & {r.sample_id for r in self.exclusions},
            "fit/exclusion overlap",
        )
        require(self.transformed_ns >= self.training_cutoff_ns, "matrix before fit cutoff")
        require(
            all(
                len(r.values) == len(self.feature_ids)
                and r.origin.timestamp_ns < self.training_cutoff_ns
                and r.data_available_ns <= self.transformed_ns
                for r in self.rows
            ),
            "training matrix shape/time mismatch",
        )


@contract("m_fit_inputs")
@dataclass(frozen=True, slots=True)
class ModelFitInputs(Artifact):
    spec_id: str
    dataset_id: str
    split_id: str
    fold_id: str
    matrix_id: str
    train_sample_ids: tuple[str, ...]
    preprocessing_state_ids: tuple[str, ...]
    training_cutoff_ns: int
    fit_started_ns: int
    fit_completed_ns: int
    model_available_ns: int

    def _validate(self) -> None:
        for identity, domain in (
            (self.spec_id, "m_spec"),
            (self.dataset_id, "r_dataset"),
            (self.split_id, "r_split"),
            (self.fold_id, "r_fold"),
            (self.matrix_id, "m_matrix"),
        ):
            validate_fingerprint(identity, domain)
        unique_ids(self.train_sample_ids, "r_sample")
        unique_ids(self.preprocessing_state_ids, "r_preprocessing_state")
        require(bool(self.train_sample_ids), "fit requires TRAIN evidence")
        require(
            self.training_cutoff_ns
            <= self.fit_started_ns
            <= self.fit_completed_ns
            <= self.model_available_ns,
            "model fit/availability clocks out of order",
        )


@contract("m_diagnostics")
@dataclass(frozen=True, slots=True)
class FitDiagnostics(Artifact):
    sample_count: int
    feature_count: int
    target_mean: float
    target_stddev: float
    residual_sum_squares: float
    coefficient_norm: float
    rank: int | None
    condition_proxy: float | None
    column_scales: tuple[float, ...]
    iterations: int
    converged: bool
    convergence_residual: float

    def _validate(self) -> None:
        require(
            self.sample_count > 0 and self.feature_count >= 0 and self.iterations >= 0,
            "invalid model diagnostic counts",
        )
        require(
            self.target_stddev >= 0
            and self.residual_sum_squares >= 0
            and self.coefficient_norm >= 0
            and self.convergence_residual >= 0,
            "negative model diagnostics",
        )
        require(self.rank is None or self.rank >= 0, "negative rank")
        require(
            self.condition_proxy is None or self.condition_proxy >= 1, "invalid condition proxy"
        )
        require(
            len(self.column_scales) == self.feature_count
            and all(s >= 0 for s in self.column_scales),
            "diagnostic column scales",
        )


@contract("m_artifact")
@dataclass(frozen=True, slots=True)
class FittedModelArtifact(Artifact):
    spec_id: str
    foundation_spec_id: str
    fit_inputs_id: str
    feature_ids: tuple[str, ...]
    coefficients: tuple[float, ...]
    intercept: float
    reference_value: float | None
    l1_penalty: float
    l2_penalty: float
    regularize_intercept: bool
    solver: SolverIdentity
    solver_version: str
    diagnostics: FitDiagnostics
    available_ns: int

    def _validate(self) -> None:
        validate_fingerprint(self.spec_id, "m_spec")
        validate_fingerprint(self.foundation_spec_id, "model_spec")
        validate_fingerprint(self.fit_inputs_id, "m_fit_inputs")
        unique_ids(self.feature_ids, "feature_definition")
        require(
            len(self.feature_ids) == len(self.coefficients) == self.diagnostics.feature_count,
            "model coefficient shape mismatch",
        )
        require(self.l1_penalty >= 0 and self.l2_penalty >= 0, "negative artifact penalties")


@contract("m_fit_run")
@dataclass(frozen=True, slots=True)
class ModelFitRun(Artifact):
    inputs: ModelFitInputs
    artifact_id: str
    diagnostics_id: str

    def _validate(self) -> None:
        validate_fingerprint(self.artifact_id, "m_artifact")
        validate_fingerprint(self.diagnostics_id, "m_diagnostics")


@contract("m_prediction_input")
@dataclass(frozen=True, slots=True)
class PredictionInput(Artifact):
    origin: ForecastOrigin
    join_id: str
    sample_id: str | None
    scope: PredictionScope

    def _validate(self) -> None:
        validate_fingerprint(self.join_id, "fs_join_result")
        if self.sample_id is not None:
            validate_fingerprint(self.sample_id, "r_sample")
        require(
            self.sample_id is not None or self.scope is PredictionScope.OUT_OF_SAMPLE_OTHER,
            "fold prediction requires exact sample",
        )


@contract("m_point_forecast")
@dataclass(frozen=True, slots=True)
class PointForecast(Artifact):
    model_artifact_id: str
    target_definition_id: str
    input: PredictionInput
    value: float
    model_available_ns: int
    computed_ns: int
    available_ns: int
    historical_admissible: bool

    def _validate(self) -> None:
        validate_fingerprint(self.model_artifact_id, "m_artifact")
        validate_fingerprint(self.target_definition_id, "target_definition")
        require(
            self.historical_admissible == (self.input.scope is not PredictionScope.IN_SAMPLE),
            "in-sample diagnostics cannot claim historical admissibility",
        )
        require(
            not self.historical_admissible
            or self.model_available_ns <= self.input.origin.availability_cutoff_ns,
            "model unavailable at forecast origin",
        )
        require(
            self.computed_ns >= self.input.origin.timestamp_ns
            and self.available_ns >= max(self.computed_ns, self.model_available_ns),
            "forecast computation/availability backdated",
        )


@contract("m_metric")
@dataclass(frozen=True, slots=True)
class PointMetric(Artifact):
    name: MetricName
    value: float | None
    state: MetricState
    sample_count: int

    def _validate(self) -> None:
        require(self.sample_count >= 0, "negative metric count")
        require(
            (self.value is not None) == (self.state is MetricState.AVAILABLE),
            "metric value/state mismatch",
        )


@contract("m_evaluation_pair")
@dataclass(frozen=True, slots=True)
class EvaluationPair(Artifact):
    prediction_id: str
    sample_id: str
    target_id: str
    origin_ns: int
    security_id: str
    prediction: float
    truth: float

    def _validate(self) -> None:
        for identity, domain in (
            (self.prediction_id, "m_point_forecast"),
            (self.sample_id, "r_sample"),
            (self.target_id, "target_vintage"),
            (self.security_id, "instrument"),
        ):
            validate_fingerprint(identity, domain)


@contract("m_origin_ic")
@dataclass(frozen=True, slots=True)
class OriginInformationCoefficient(Artifact):
    origin_ns: int
    pearson: PointMetric
    rank_ic: PointMetric


@contract("m_ic_summary")
@dataclass(frozen=True, slots=True)
class InformationCoefficientSummary(Artifact):
    origin_count: int
    pearson_count: int
    rank_count: int
    pearson_mean: float | None
    pearson_median: float | None
    pearson_stddev: float | None
    rank_mean: float | None
    rank_median: float | None
    rank_stddev: float | None

    def _validate(self) -> None:
        require(
            0 <= self.pearson_count <= self.origin_count
            and 0 <= self.rank_count <= self.origin_count,
            "invalid IC summary counts",
        )
        for count, values in (
            (self.pearson_count, (self.pearson_mean, self.pearson_median, self.pearson_stddev)),
            (self.rank_count, (self.rank_mean, self.rank_median, self.rank_stddev)),
        ):
            require(
                all((v is not None) == (count > 0) for v in values),
                "IC summary value/count mismatch",
            )


@contract("m_evaluation")
@dataclass(frozen=True, slots=True)
class PointEvaluation(Artifact):
    model_artifact_id: str
    dataset_id: str
    fold_id: str
    target_definition_id: str
    scope: PredictionScope
    prediction_ids: tuple[str, ...]
    pairs: tuple[EvaluationPair, ...]
    exclusions: tuple[MatrixExclusion, ...]
    metrics: tuple[PointMetric, ...]
    origin_ics: tuple[OriginInformationCoefficient, ...]
    ic_summary: InformationCoefficientSummary
    evaluation_cutoff_ns: int
    available_ns: int
    test_evaluation_id: str | None

    def _normalize(self) -> None:
        object.__setattr__(self, "prediction_ids", tuple(sorted(self.prediction_ids)))
        object.__setattr__(
            self,
            "pairs",
            tuple(sorted(self.pairs, key=lambda p: (p.origin_ns, p.security_id, p.sample_id))),
        )
        self.ordered("exclusions", "sample_id")
        require(len({m.name for m in self.metrics}) == len(self.metrics), "duplicate metric")
        object.__setattr__(
            self, "metrics", tuple(sorted(self.metrics, key=lambda m: m.name.value))
        )
        self.ordered("origin_ics", "origin_ns")

    def _validate(self) -> None:
        for identity, domain in (
            (self.model_artifact_id, "m_artifact"),
            (self.dataset_id, "r_dataset"),
            (self.fold_id, "r_fold"),
            (self.target_definition_id, "target_definition"),
        ):
            validate_fingerprint(identity, domain)
        unique_ids(self.prediction_ids, "m_point_forecast")
        unique_ids(tuple(p.sample_id for p in self.pairs), "r_sample")
        require(bool(self.prediction_ids), "empty evaluation request")
        require(
            {p.prediction_id for p in self.pairs} <= set(self.prediction_ids),
            "evaluation prediction evidence mismatch",
        )
        require(self.available_ns >= self.evaluation_cutoff_ns, "evaluation before cutoff")
        require(
            (self.test_evaluation_id is not None) == (self.scope is PredictionScope.TEST),
            "TEST evaluation requires sealed access record",
        )
        if self.test_evaluation_id is not None:
            validate_fingerprint(self.test_evaluation_id, "r_test_evaluation")


@contract("m_comparison")
@dataclass(frozen=True, slots=True)
class BaselineComparison(Artifact):
    candidate_evaluation_id: str
    reference_evaluation_id: str
    sample_ids: tuple[str, ...]
    delta_metrics: tuple[PointMetric, ...]

    def _normalize(self) -> None:
        object.__setattr__(self, "sample_ids", tuple(sorted(self.sample_ids)))
        require(
            len({m.name for m in self.delta_metrics}) == len(self.delta_metrics),
            "duplicate delta metric",
        )
        object.__setattr__(
            self, "delta_metrics", tuple(sorted(self.delta_metrics, key=lambda m: m.name.value))
        )

    def _validate(self) -> None:
        validate_fingerprint(self.candidate_evaluation_id, "m_evaluation")
        validate_fingerprint(self.reference_evaluation_id, "m_evaluation")
        unique_ids(self.sample_ids, "r_sample")
        require(bool(self.sample_ids), "comparison requires common evaluated samples")


@contract("m_audit")
@dataclass(frozen=True, slots=True)
class ModelLineageAudit(Artifact):
    root_id: str
    evidence_ids: tuple[str, ...]
    checks: tuple[str, ...]

    def _normalize(self) -> None:
        object.__setattr__(self, "evidence_ids", tuple(sorted(self.evidence_ids)))
        object.__setattr__(self, "checks", tuple(sorted(self.checks)))

    def _validate(self) -> None:
        validate_fingerprint(self.root_id)
        unique_ids(self.evidence_ids)
        require(len(set(self.checks)) == len(self.checks), "duplicate model audit check")

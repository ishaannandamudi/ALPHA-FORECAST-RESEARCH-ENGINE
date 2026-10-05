"""Frozen fit, covariance, bundle, evaluation and audit evidence."""

from dataclasses import dataclass

from afre.forecast import ForecastOrigin
from afre.ids import validate_fingerprint
from afre.multihorizon.schema import (
    Architecture,
    Completeness,
    ComponentState,
    Denominator,
    DependenceMethod,
    ParameterOwnership,
)
from afre.probabilistic.artifacts import ProbabilityScore, QuantileValue, ThresholdProbability
from afre.schema import Artifact, contract, require
from afre.statistical_models.artifacts import PointMetric, PredictionInput, unique_ids


@contract("mh_train_evidence")
@dataclass(frozen=True, slots=True)
class HorizonTrainEvidence(Artifact):
    target_id: str
    model_id: str
    matrix_id: str
    fold_id: str
    cutoff_ns: int
    preprocessing_state_ids: tuple[str, ...]
    sample_ids: tuple[str, ...]

    def _validate(self) -> None:
        for identity, domain in (
            (self.target_id, "target_definition"),
            (self.model_id, "m_artifact"),
            (self.matrix_id, "m_matrix"),
            (self.fold_id, "r_fold"),
        ):
            validate_fingerprint(identity, domain)
        unique_ids(self.sample_ids, "r_sample")
        unique_ids(self.preprocessing_state_ids, "r_preprocessing_state")
        require(bool(self.sample_ids), "TRAIN evidence required")


@contract("mh_alignment")
@dataclass(frozen=True, slots=True)
class AlignedTrainRow(Artifact):
    origin: ForecastOrigin
    sample_ids: tuple[str, ...]
    target_ids: tuple[str, ...]
    responses: tuple[float, ...]
    residuals: tuple[float, ...]
    features: tuple[tuple[float, ...], ...]
    available_ns: int

    def _validate(self) -> None:
        unique_ids(self.sample_ids, "r_sample")
        unique_ids(self.target_ids, "target_vintage")
        require(
            len(self.sample_ids)
            == len(self.target_ids)
            == len(self.responses)
            == len(self.residuals)
            == len(self.features)
            > 0,
            "aligned row shape",
        )


@contract("mh_shared_parameters")
@dataclass(frozen=True, slots=True)
class SharedParameters(Artifact):
    spec_id: str
    feature_ids: tuple[str, ...]
    coefficients: tuple[float, ...]
    intercepts: tuple[float, ...]
    sample_rows: tuple[AlignedTrainRow, ...]
    cutoff_ns: int
    available_ns: int
    rank: int
    condition_proxy: float
    residual_sum_squares: float
    solver_version: str = "weighted-pooled-pivoted-qr-v1"

    def _validate(self) -> None:
        validate_fingerprint(self.spec_id, "mh_model_spec")
        unique_ids(self.feature_ids, "feature_definition")
        require(
            len(self.coefficients) == len(self.feature_ids)
            and bool(self.sample_rows)
            and all(
                len(r.responses) == len(self.intercepts) and r.available_ns <= self.cutoff_ns
                for r in self.sample_rows
            ),
            "shared fit shape/availability",
        )
        require(
            self.available_ns >= self.cutoff_ns
            and self.rank > 0
            and self.condition_proxy >= 1
            and self.residual_sum_squares >= 0
            and self.solver_version == "weighted-pooled-pivoted-qr-v1",
            "shared fit diagnostics",
        )


@contract("mh_fit_run")
@dataclass(frozen=True, slots=True)
class MultiHorizonFitRun(Artifact):
    spec_id: str
    train: tuple[HorizonTrainEvidence, ...]
    intersection: tuple[AlignedTrainRow, ...]
    shared_parameters_id: str | None
    fit_started_ns: int
    fit_completed_ns: int
    available_ns: int

    def _validate(self) -> None:
        validate_fingerprint(self.spec_id, "mh_model_spec")
        if self.shared_parameters_id is not None:
            validate_fingerprint(self.shared_parameters_id, "mh_shared_parameters")
        require(
            bool(self.train)
            and self.fit_started_ns <= self.fit_completed_ns <= self.available_ns
            and self.fit_started_ns >= max(t.cutoff_ns for t in self.train),
            "multi-horizon fit clocks",
        )


@contract("mh_covariance")
@dataclass(frozen=True, slots=True)
class CovarianceArtifact(Artifact):
    fit_run_id: str
    horizon_ids: tuple[str, ...]
    rows: tuple[AlignedTrainRow, ...]
    means: tuple[float, ...]
    matrix: tuple[tuple[float, ...], ...]
    denominator: Denominator
    cutoff_ns: int
    available_ns: int
    tolerance: float = 1e-12
    centering: str = "matched-residual-mean-v1"
    method: DependenceMethod = DependenceMethod.EMPIRICAL_RESIDUAL_COVARIANCE
    numerical_version: str = "symmetric-unpivoted-psd-v1"
    ownership: ParameterOwnership = ParameterOwnership.GLOBAL_SHARED

    def _validate(self) -> None:
        from afre.multihorizon.covariance import validate_psd

        validate_fingerprint(self.fit_run_id, "mh_fit_run")
        unique_ids(self.horizon_ids, "horizon")
        require(
            0 < len(self.horizon_ids) <= 64
            and len(self.means) == len(self.horizon_ids)
            and all(
                len(r.residuals) == len(self.horizon_ids) and r.available_ns <= self.cutoff_ns
                for r in self.rows
            )
            and bool(self.rows)
            and self.available_ns >= self.cutoff_ns,
            "covariance evidence/availability",
        )
        require(
            self.ownership is ParameterOwnership.GLOBAL_SHARED
            and self.method is DependenceMethod.EMPIRICAL_RESIDUAL_COVARIANCE
            and self.centering == "matched-residual-mean-v1"
            and self.numerical_version == "symmetric-unpivoted-psd-v1",
            "covariance policy",
        )
        require(len(self.matrix) == len(self.horizon_ids), "covariance horizon dimension")
        validate_psd(self.matrix, self.tolerance)
        require(
            self.denominator is not Denominator.SAMPLE or len(self.rows) > 1,
            "sample covariance needs two rows",
        )


@contract("mh_shared_point")
@dataclass(frozen=True, slots=True)
class SharedPointForecast(Artifact):
    fit_run_id: str
    shared_parameters_id: str
    target_definition_id: str
    scaffold_forecast_id: str
    input: PredictionInput
    value: float
    computed_ns: int
    available_ns: int

    def _validate(self) -> None:
        for identity, domain in (
            (self.fit_run_id, "mh_fit_run"),
            (self.shared_parameters_id, "mh_shared_parameters"),
            (self.target_definition_id, "target_definition"),
            (self.scaffold_forecast_id, "m_point_forecast"),
        ):
            validate_fingerprint(identity, domain)
        require(
            self.input.origin.timestamp_ns <= self.computed_ns <= self.available_ns,
            "shared prediction clocks",
        )


@contract("mh_forecast_entry")
@dataclass(frozen=True, slots=True)
class HorizonForecastEntry(Artifact):
    target_definition_id: str
    state: ComponentState
    point_forecast_id: str | None = None
    probability_forecast_id: str | None = None
    calibrated_forecast_id: str | None = None
    reason: str = "included"

    def _validate(self) -> None:
        validate_fingerprint(self.target_definition_id, "target_definition")
        if self.point_forecast_id is not None:
            validate_fingerprint(self.point_forecast_id)
            require(
                self.point_forecast_id.startswith(
                    ("afre.m_point_forecast:", "afre.mh_shared_point:")
                ),
                "point forecast domain",
            )
        for identity, domain in (
            (self.probability_forecast_id, "p_forecast"),
            (self.calibrated_forecast_id, "c_forecast"),
        ):
            if identity is not None:
                validate_fingerprint(identity, domain)
        require(
            (self.point_forecast_id is not None) == (self.state is ComponentState.AVAILABLE),
            "entry state/point mismatch",
        )
        require(
            self.probability_forecast_id is None or self.point_forecast_id is not None,
            "probability needs point",
        )
        require(
            self.calibrated_forecast_id is None or self.probability_forecast_id is not None,
            "calibration needs raw probability",
        )


@contract("mh_forecast")
@dataclass(frozen=True, slots=True)
class MultiHorizonForecast(Artifact):
    fit_run_id: str
    horizon_set_id: str
    architecture: Architecture
    origin: ForecastOrigin
    entries: tuple[HorizonForecastEntry, ...]
    completeness: Completeness
    dependence_method: DependenceMethod
    covariance_id: str | None
    computed_ns: int
    available_ns: int
    historical_admissible: bool

    def _validate(self) -> None:
        validate_fingerprint(self.fit_run_id, "mh_fit_run")
        validate_fingerprint(self.horizon_set_id, "mh_horizon_set")
        unique_ids(tuple(e.target_definition_id for e in self.entries), "target_definition")
        require(bool(self.entries), "empty bundle")
        count = sum(e.state is ComponentState.AVAILABLE for e in self.entries)
        expected = (
            Completeness.COMPLETE
            if count == len(self.entries)
            else (Completeness.PARTIAL if count else Completeness.UNAVAILABLE)
        )
        require(
            self.completeness is expected and self.historical_admissible == bool(count),
            "bundle completeness/admissibility",
        )
        require(
            (self.covariance_id is None) == (self.dependence_method is DependenceMethod.NONE),
            "dependence state mismatch",
        )
        if self.covariance_id is not None:
            validate_fingerprint(self.covariance_id, "mh_covariance")
        require(
            self.origin.timestamp_ns <= self.computed_ns <= self.available_ns, "bundle clocks"
        )


@contract("mh_surface_value")
@dataclass(frozen=True, slots=True)
class SurfaceValue(Artifact):
    target_definition_id: str
    state: ComponentState
    value: float | None

    def _validate(self) -> None:
        validate_fingerprint(self.target_definition_id, "target_definition")
        require(
            (self.value is not None) == (self.state is ComponentState.AVAILABLE),
            "surface state",
        )


@contract("mh_surface_row")
@dataclass(frozen=True, slots=True)
class SurfaceRow(Artifact):
    target_definition_id: str
    state: ComponentState
    quantiles: tuple[QuantileValue, ...]
    probabilities: tuple[ThresholdProbability, ...]


@contract("mh_consistency")
@dataclass(frozen=True, slots=True)
class ConsistencyAudit(Artifact):
    bundle_id: str
    same_family_units: bool
    compatible_adjustment: bool
    nested_elapsed_windows: bool
    checks: tuple[str, ...]
    expectation_differences: tuple[float | None, ...]

    def _validate(self) -> None:
        validate_fingerprint(self.bundle_id, "mh_forecast")


@contract("mh_horizon_evaluation")
@dataclass(frozen=True, slots=True)
class HorizonEvaluation(Artifact):
    target_definition_id: str
    point_evaluation_id: str | None
    probability_evaluation_id: str | None
    calibration_evaluation_id: str | None
    test_evaluation_id: str | None
    point_metrics: tuple[PointMetric, ...]
    raw_scores: tuple[ProbabilityScore, ...]
    calibrated_scores: tuple[ProbabilityScore, ...]
    evaluated_origins: tuple[str, ...]
    missing_count: int

    def _validate(self) -> None:
        validate_fingerprint(self.target_definition_id, "target_definition")
        for identity, domain in (
            (self.point_evaluation_id, "m_evaluation"),
            (self.probability_evaluation_id, "p_evaluation"),
            (self.calibration_evaluation_id, "c_evaluation"),
            (self.test_evaluation_id, "r_test_evaluation"),
        ):
            if identity is not None:
                validate_fingerprint(identity, domain)
        unique_ids(self.evaluated_origins, "forecast_origin")
        require(self.missing_count >= 0, "negative missing count")


@contract("mh_evaluation")
@dataclass(frozen=True, slots=True)
class MultiHorizonEvaluation(Artifact):
    fit_run_id: str
    bundle_ids: tuple[str, ...]
    horizons: tuple[HorizonEvaluation, ...]
    horizon_weights: tuple[float, ...]
    weighted_mse: float | None
    matched_origins: tuple[str, ...]
    matched_point_metrics: tuple[tuple[PointMetric, ...], ...]
    cutoff_ns: int
    available_ns: int

    def _normalize(self) -> None:
        object.__setattr__(self, "bundle_ids", tuple(sorted(self.bundle_ids)))

    def _validate(self) -> None:
        validate_fingerprint(self.fit_run_id, "mh_fit_run")
        unique_ids(self.bundle_ids, "mh_forecast")
        unique_ids(self.matched_origins, "forecast_origin")
        require(
            bool(self.bundle_ids)
            and len(self.horizons)
            == len(self.horizon_weights)
            == len(self.matched_point_metrics)
            and all(w >= 0 for w in self.horizon_weights)
            and sum(self.horizon_weights) > 0
            and self.available_ns >= self.cutoff_ns,
            "evaluation shape/clocks/weights",
        )


@contract("mh_audit")
@dataclass(frozen=True, slots=True)
class MultiHorizonLineageAudit(Artifact):
    root_id: str
    evidence_ids: tuple[str, ...]
    checks: tuple[str, ...]

    def _normalize(self) -> None:
        object.__setattr__(self, "evidence_ids", tuple(sorted(self.evidence_ids)))

    def _validate(self) -> None:
        validate_fingerprint(self.root_id)
        unique_ids(self.evidence_ids)
        require(self.root_id in self.evidence_ids, "lineage root missing")

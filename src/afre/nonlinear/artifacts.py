"""Immutable inputs, TRAIN evidence, fitted data, forecasts and descriptive results."""

from dataclasses import dataclass

from afre.forecast import ForecastOrigin
from afre.ids import validate_fingerprint
from afre.nonlinear.definitions import ScalarFeatureDefinition
from afre.nonlinear.schema import NonlinearCalibrationStatus, NonlinearFamily
from afre.probabilistic.artifacts import (
    DistributionParameters,
    ProbabilityScore,
    QuantileValue,
    ThresholdProbability,
)
from afre.probabilistic.definitions import ThresholdRequest
from afre.research_datasets.schema import Partition
from afre.schema import Artifact, contract, require
from afre.statistical_models.artifacts import PointMetric
from afre.universe.identity import StableSecurityId


def identities(values: tuple[str, ...], domain: str | None) -> None:
    require(len(set(values)) == len(values), "duplicate nonlinear identity")
    for identity in values:
        validate_fingerprint(identity, domain)


@contract("nl_scalar")
@dataclass(frozen=True, slots=True)
class ScalarInput(Artifact):
    definition: ScalarFeatureDefinition
    source_id: str
    origin: ForecastOrigin
    value: float | None
    available_ns: int
    approved_attestors: tuple[str, ...] = ()

    def _normalize(self) -> None:
        require(
            len(set(self.approved_attestors)) == len(self.approved_attestors),
            "duplicate scalar attestors",
        )
        object.__setattr__(self, "approved_attestors", tuple(sorted(self.approved_attestors)))

    def _validate(self) -> None:
        validate_fingerprint(self.source_id)
        require(
            self.available_ns <= self.origin.availability_cutoff_ns,
            "scalar unavailable at origin",
        )


@contract("nl_input")
@dataclass(frozen=True, slots=True)
class NonlinearInput(Artifact):
    sample_id: str
    origin: ForecastOrigin
    scalars: tuple[ScalarInput, ...]

    def _normalize(self) -> None:
        object.__setattr__(
            self, "scalars", tuple(sorted(self.scalars, key=lambda s: s.definition.fingerprint))
        )

    def _validate(self) -> None:
        validate_fingerprint(self.sample_id, "r_sample")
        require(
            bool(self.scalars)
            and len({s.definition for s in self.scalars}) == len(self.scalars),
            "input unique semantic features",
        )
        require(
            all(s.origin == self.origin for s in self.scalars), "input full origin agreement"
        )


@contract("nl_transform_state")
@dataclass(frozen=True, slots=True)
class FittedTransformArtifact(Artifact):
    spec_id: str
    definition_id: str
    fold_id: str
    train_input_ids: tuple[str, ...]
    train_sample_ids: tuple[str, ...]
    knots: tuple[float, ...]
    cutoff_ns: int
    started_ns: int
    completed_ns: int
    available_ns: int

    def _normalize(self) -> None:
        for name in ("train_input_ids", "train_sample_ids"):
            object.__setattr__(self, name, tuple(sorted(getattr(self, name))))

    def _validate(self) -> None:
        validate_fingerprint(self.spec_id, "nl_spec")
        validate_fingerprint(self.definition_id, "nl_interaction")
        validate_fingerprint(self.fold_id, "r_fold")
        identities(self.train_input_ids, "nl_input")
        identities(self.train_sample_ids, "r_sample")
        require(
            bool(self.train_input_ids)
            and len(self.train_input_ids) == len(self.train_sample_ids),
            "transform exact TRAIN evidence",
        )
        require(
            2 <= len(self.knots) <= 16
            and all(a < b for a, b in zip(self.knots, self.knots[1:], strict=False)),
            "fitted unique knots",
        )
        require(
            self.cutoff_ns <= self.started_ns <= self.completed_ns <= self.available_ns,
            "transform fit clocks",
        )


@contract("nl_value")
@dataclass(frozen=True, slots=True)
class InteractionValue(Artifact):
    definition_id: str
    input_ids: tuple[str, ...]
    transform_id: str | None
    value: float | None
    used_fallback: bool
    computed_ns: int
    available_ns: int

    def _validate(self) -> None:
        validate_fingerprint(self.definition_id, "nl_interaction")
        # Repeated operands are explicit and valid; order follows the definition.
        for identity in self.input_ids:
            validate_fingerprint(identity, "nl_scalar")
        if self.transform_id:
            validate_fingerprint(self.transform_id, "nl_transform_state")
        require(self.available_ns >= self.computed_ns, "interaction computation availability")


@contract("nl_training_row")
@dataclass(frozen=True, slots=True)
class InteractionTrainingRow(Artifact):
    spec_id: str
    sample_id: str
    input_id: str
    interaction_ids: tuple[str, ...]
    values: tuple[float, ...]
    target_id: str
    response: float
    available_ns: int

    def _validate(self) -> None:
        validate_fingerprint(self.spec_id, "nl_spec")
        validate_fingerprint(self.sample_id, "r_sample")
        validate_fingerprint(self.input_id, "nl_input")
        validate_fingerprint(self.target_id, "target_vintage")
        identities(self.interaction_ids, "nl_value")
        require(bool(self.values), "training columns required")


@contract("nl_matrix")
@dataclass(frozen=True, slots=True)
class InteractionMatrix(Artifact):
    spec_id: str
    fold_id: str
    rows: tuple[InteractionTrainingRow, ...]
    columns: tuple[str, ...]
    transform_ids: tuple[str, ...]
    cutoff_ns: int
    computed_ns: int

    def _normalize(self) -> None:
        self.ordered("rows", "sample_id")
        object.__setattr__(self, "transform_ids", tuple(sorted(self.transform_ids)))

    def _validate(self) -> None:
        validate_fingerprint(self.spec_id, "nl_spec")
        validate_fingerprint(self.fold_id, "r_fold")
        identities(self.transform_ids, "nl_transform_state")
        require(
            bool(self.rows)
            and bool(self.columns)
            and len(set(self.columns)) == len(self.columns),
            "matrix evidence and columns",
        )
        require(
            all(
                len(r.values) == len(self.columns) and r.available_ns <= self.computed_ns
                for r in self.rows
            )
            and self.cutoff_ns <= self.computed_ns,
            "matrix dimensions/clocks",
        )


@contract("nl_tree_node")
@dataclass(frozen=True, slots=True)
class TreeNode(Artifact):
    node_id: int
    depth: int
    sample_ids: tuple[str, ...]
    value: float
    squared_error: float
    feature_id: str | None = None
    threshold: float | None = None
    left: int | None = None
    right: int | None = None

    def _normalize(self) -> None:
        object.__setattr__(self, "sample_ids", tuple(sorted(self.sample_ids)))

    def _validate(self) -> None:
        identities(self.sample_ids, "r_sample")
        require(
            bool(self.sample_ids)
            and self.node_id >= 0
            and 0 <= self.depth <= 4
            and self.squared_error >= 0,
            "tree node support/depth/loss",
        )
        require(
            (
                self.feature_id is None
                and self.threshold is None
                and self.left is None
                and self.right is None
            )
            or (
                self.feature_id is not None
                and self.threshold is not None
                and self.left is not None
                and self.right is not None
                and self.node_id < self.left < self.right
            ),
            "tree split/leaf shape",
        )


@contract("nl_model")
@dataclass(frozen=True, slots=True)
class NonlinearModelArtifact(Artifact):
    spec_id: str
    matrix_id: str
    train_sample_ids: tuple[str, ...]
    transform_ids: tuple[str, ...]
    columns: tuple[str, ...]
    family: NonlinearFamily
    centers: tuple[float, ...]
    scales: tuple[float, ...]
    intercept: float
    coefficients: tuple[float, ...]
    nodes: tuple[TreeNode, ...]
    training_squared_error: float
    qr_rank: int | None
    condition_proxy: float | None
    cutoff_ns: int
    started_ns: int
    completed_ns: int
    available_ns: int

    def _normalize(self) -> None:
        object.__setattr__(self, "train_sample_ids", tuple(sorted(self.train_sample_ids)))
        object.__setattr__(self, "transform_ids", tuple(sorted(self.transform_ids)))

    def _validate(self) -> None:
        validate_fingerprint(self.spec_id, "nl_spec")
        validate_fingerprint(self.matrix_id, "nl_matrix")
        identities(self.train_sample_ids, "r_sample")
        identities(self.transform_ids, "nl_transform_state")
        require(
            bool(self.train_sample_ids)
            and len(self.columns) == len(self.centers) == len(self.scales)
            and all(s > 0 for s in self.scales),
            "model scaling dimensions",
        )
        tree = self.family is NonlinearFamily.SHALLOW_REGRESSION_TREE
        require(
            bool(self.nodes) == tree
            and (
                not self.coefficients if tree else len(self.coefficients) == len(self.columns)
            ),
            "model family payload",
        )
        require(
            self.training_squared_error >= 0
            and self.cutoff_ns <= self.started_ns <= self.completed_ns <= self.available_ns,
            "model loss/fit clocks",
        )
        require(
            not tree or tuple(n.node_id for n in self.nodes) == tuple(range(len(self.nodes))),
            "tree node order",
        )


@contract("nl_probability")
@dataclass(frozen=True, slots=True)
class NonlinearProbabilityView(Artifact):
    base_forecast_id: str
    shift: float
    distribution: DistributionParameters
    quantiles: tuple[QuantileValue, ...]
    events: tuple[ThresholdProbability, ...]

    def _validate(self) -> None:
        validate_fingerprint(self.base_forecast_id, "p_forecast")


@contract("nl_path")
@dataclass(frozen=True, slots=True)
class TreePathStep(Artifact):
    node_id: int
    feature_id: str | None
    threshold: float | None
    branch: str
    value: float

    def _validate(self) -> None:
        require(self.branch in ("left-leq", "right-gt", "leaf"), "tree path branch")


@contract("nl_forecast")
@dataclass(frozen=True, slots=True)
class NonlinearForecast(Artifact):
    model_id: str
    spec_id: str
    input_id: str
    sample_id: str
    origin: ForecastOrigin
    security: StableSecurityId
    target_definition_id: str
    partition: Partition
    interaction_ids: tuple[str, ...]
    column_values: tuple[float, ...]
    contributions: tuple[tuple[str, float], ...]
    path: tuple[TreePathStep, ...]
    value: float
    probability: NonlinearProbabilityView | None
    computed_ns: int
    available_ns: int

    def _validate(self) -> None:
        for identity, domain in (
            (self.model_id, "nl_model"),
            (self.spec_id, "nl_spec"),
            (self.input_id, "nl_input"),
            (self.sample_id, "r_sample"),
            (self.target_definition_id, "target_definition"),
        ):
            validate_fingerprint(identity, domain)
        identities(self.interaction_ids, "nl_value")
        require(
            self.partition in (Partition.VALIDATION, Partition.TEST),
            "held-out nonlinear forecast partition",
        )
        require(
            self.security.instrument == self.origin.instrument
            and self.origin.timestamp_ns
            <= self.computed_ns
            <= self.available_ns
            <= self.origin.availability_cutoff_ns,
            "forecast security/actual computation/causality",
        )


@contract("nl_evaluation_pair")
@dataclass(frozen=True, slots=True)
class NonlinearEvaluationPair(Artifact):
    forecast_id: str
    sample_id: str
    target_id: str
    prediction: float
    truth: float
    baseline_id: str | None
    baseline: float | None
    scores: tuple[ProbabilityScore, ...]


@contract("nl_evaluation")
@dataclass(frozen=True, slots=True)
class NonlinearEvaluation(Artifact):
    model_id: str
    forecast_ids: tuple[str, ...]
    pairs: tuple[NonlinearEvaluationPair, ...]
    metrics: tuple[PointMetric, ...]
    baseline_metrics: tuple[PointMetric, ...]
    deltas: tuple[PointMetric, ...]
    cohorts: tuple[tuple[str, tuple[PointMetric, ...]], ...]
    probability_scores: tuple[ProbabilityScore, ...]
    thresholds: tuple[ThresholdRequest, ...]
    cutoff_ns: int
    available_ns: int
    test_evaluation_id: str | None

    def _normalize(self) -> None:
        object.__setattr__(self, "forecast_ids", tuple(sorted(self.forecast_ids)))
        self.ordered("pairs", "sample_id")
        object.__setattr__(self, "cohorts", tuple(sorted(self.cohorts)))
        object.__setattr__(
            self,
            "thresholds",
            tuple(sorted(self.thresholds, key=lambda t: (t.value, t.comparison.value))),
        )

    def _validate(self) -> None:
        validate_fingerprint(self.model_id, "nl_model")
        identities(self.forecast_ids, "nl_forecast")
        require(
            bool(self.forecast_ids) and self.available_ns >= self.cutoff_ns,
            "evaluation clocks/input",
        )
        if self.test_evaluation_id:
            validate_fingerprint(self.test_evaluation_id, "r_test_evaluation")


@contract("nl_stability")
@dataclass(frozen=True, slots=True)
class InteractionStability(Artifact):
    model_ids: tuple[str, ...]
    columns: tuple[str, ...]
    coefficient_sign_consistency: tuple[float, ...]
    coefficient_magnitude_drift: tuple[float, ...]
    split_recurrence: tuple[float, ...]
    available_ns: int

    def _normalize(self) -> None:
        object.__setattr__(self, "model_ids", tuple(sorted(self.model_ids)))

    def _validate(self) -> None:
        identities(self.model_ids, "nl_model")
        require(len(self.model_ids) >= 2, "stability needs distinct compatible models")
        require(
            all(
                0 <= v <= 1
                for v in (*self.coefficient_sign_consistency, *self.split_recurrence)
            ),
            "stability fraction",
        )


@contract("nl_calibration")
@dataclass(frozen=True, slots=True)
class NonlinearCalibrationAssessment(Artifact):
    forecast_id: str
    observation_ids: tuple[str, ...]
    proposed_state_id: str | None
    minimum_count: int
    cutoff_ns: int
    status: NonlinearCalibrationStatus

    def _normalize(self) -> None:
        object.__setattr__(self, "observation_ids", tuple(sorted(self.observation_ids)))

    def _validate(self) -> None:
        validate_fingerprint(self.forecast_id, "nl_forecast")
        identities(self.observation_ids, "nl_forecast")
        require(self.minimum_count >= 2, "calibration minimum count")
        if self.proposed_state_id:
            validate_fingerprint(self.proposed_state_id, "c_state")


@contract("nl_ranking")
@dataclass(frozen=True, slots=True)
class NonlinearRanking(Artifact):
    ranking_id: str
    forecast_ids: tuple[str, ...]
    signal_ids: tuple[str, ...]

    def _normalize(self) -> None:
        for name in ("forecast_ids", "signal_ids"):
            object.__setattr__(self, name, tuple(sorted(getattr(self, name))))

    def _validate(self) -> None:
        validate_fingerprint(self.ranking_id, "cs_ranking")
        identities(self.forecast_ids, "nl_forecast")
        identities(self.signal_ids, "cs_external_signal")
        require(
            bool(self.forecast_ids) and len(self.forecast_ids) == len(self.signal_ids),
            "ranking grid",
        )


@contract("nl_rank_evaluation")
@dataclass(frozen=True, slots=True)
class NonlinearRankEvaluation(Artifact):
    ranking_id: str
    matched_id: str
    cross_section_id: str

    def _validate(self) -> None:
        validate_fingerprint(self.ranking_id, "nl_ranking")
        validate_fingerprint(self.matched_id, "nl_evaluation")
        validate_fingerprint(self.cross_section_id, "cs_evaluation")


@contract("nl_audit")
@dataclass(frozen=True, slots=True)
class NonlinearAudit(Artifact):
    root_id: str
    node_ids: tuple[str, ...]
    checks: tuple[str, ...]

    def _normalize(self) -> None:
        object.__setattr__(self, "node_ids", tuple(sorted(self.node_ids)))

    def _validate(self) -> None:
        validate_fingerprint(self.root_id)
        identities(self.node_ids, None)

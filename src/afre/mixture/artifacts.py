"""Safe immutable gate evidence, finite distributions, forecasts and diagnostics."""

from dataclasses import dataclass
from math import fsum

from afre.forecast import ForecastOrigin
from afre.ids import validate_fingerprint
from afre.mixture.definitions import validate_weights
from afre.mixture.schema import GateMode, MixtureCalibrationStatus
from afre.probabilistic.artifacts import DistributionParameters, ProbabilityScore
from afre.probabilistic.definitions import ThresholdRequest
from afre.probabilistic.schema import DistributionFamily
from afre.research_datasets.schema import Partition
from afre.schema import Artifact, contract, require
from afre.statistical_models.artifacts import PointMetric, unique_ids
from afre.universe.identity import StableSecurityId


@contract("mix_train_row")
@dataclass(frozen=True, slots=True)
class GateTrainingRow(Artifact):
    sample_id: str
    binding_ids: tuple[str, ...]
    feature_ids: tuple[str, ...]
    target_id: str
    response: float
    origin: ForecastOrigin
    data_available_ns: int
    spec_id: str

    def _normalize(self) -> None:
        object.__setattr__(self, "feature_ids", tuple(sorted(self.feature_ids)))

    def _validate(self) -> None:
        validate_fingerprint(self.sample_id, "r_sample")
        validate_fingerprint(self.spec_id, "mix_learned_spec")
        validate_fingerprint(self.target_id, "target_vintage")
        unique_ids(self.binding_ids, "mix_binding")
        unique_ids(self.feature_ids, "mix_gating_feature")


@contract("mix_gate_model")
@dataclass(frozen=True, slots=True)
class GateModelArtifact(Artifact):
    spec_id: str
    expert_set_id: str
    weights: tuple[tuple[str, float], ...]
    rows: tuple[GateTrainingRow, ...]
    iterations: int
    convergence_residual: float
    objective_value: float
    cutoff_ns: int
    fit_started_ns: int
    fit_completed_ns: int
    available_ns: int
    solver_version: str = "scaled-simplex-projected-gradient-v1"
    converged: bool = True

    def _normalize(self) -> None:
        self.ordered("rows", "sample_id")
        object.__setattr__(self, "weights", tuple(sorted(self.weights)))

    def _validate(self) -> None:
        validate_fingerprint(self.spec_id, "mix_learned_spec")
        validate_fingerprint(self.expert_set_id, "mix_set")
        validate_weights(self.weights, tuple(i for i, _ in self.weights))
        require(
            bool(self.rows)
            and self.iterations > 0
            and self.converged
            and self.convergence_residual >= 0
            and self.objective_value >= 0,
            "completed gate requires converged positive diagnostics",
        )
        require(
            self.cutoff_ns <= self.fit_started_ns <= self.fit_completed_ns <= self.available_ns
            and all(
                r.origin.timestamp_ns < self.cutoff_ns and r.data_available_ns <= self.cutoff_ns
                for r in self.rows
            ),
            "gate TRAIN/fit availability clocks",
        )
        require(
            self.solver_version == "scaled-simplex-projected-gradient-v1",
            "unsupported gate solver",
        )


@contract("mix_component")
@dataclass(frozen=True, slots=True)
class MixtureComponent(Artifact):
    expert_id: str
    binding_id: str
    weight: float
    distribution: DistributionParameters

    def _validate(self) -> None:
        validate_fingerprint(self.expert_id, "mix_expert")
        validate_fingerprint(self.binding_id, "mix_binding")
        require(
            self.weight > 0 and self.distribution.family is not DistributionFamily.QUANTILE_SET,
            "finite mixture needs positive components with complete laws",
        )


@contract("mix_distribution")
@dataclass(frozen=True, slots=True)
class MixtureDistribution(Artifact):
    components: tuple[MixtureComponent, ...]
    tolerance: float = 1e-12
    semantics: str = "finite-component-law-v1"
    quantile_policy: str = "unsupported-no-quantile-averaging-v1"

    def _normalize(self) -> None:
        self.ordered("components", "expert_id")

    def _validate(self) -> None:
        require(bool(self.components), "empty finite mixture")
        validate_weights(
            tuple((c.expert_id, c.weight) for c in self.components),
            tuple(c.expert_id for c in self.components),
            self.tolerance,
        )
        require(
            self.semantics == "finite-component-law-v1"
            and self.quantile_policy == "unsupported-no-quantile-averaging-v1",
            "unsupported mixture probability semantics",
        )


@contract("mix_request")
@dataclass(frozen=True, slots=True)
class MixtureRequest(Artifact):
    expert_set_id: str
    gate_id: str
    fold_id: str
    sample_id: str
    expert_inputs: tuple[tuple[str, str | None], ...]
    gating_feature_ids: tuple[str, ...]
    computed_ns: int

    def _normalize(self) -> None:
        object.__setattr__(self, "expert_inputs", tuple(sorted(self.expert_inputs)))
        object.__setattr__(self, "gating_feature_ids", tuple(sorted(self.gating_feature_ids)))

    def _validate(self) -> None:
        for identity, domain in (
            (self.expert_set_id, "mix_set"),
            (self.fold_id, "r_fold"),
            (self.sample_id, "r_sample"),
        ):
            validate_fingerprint(identity, domain)
        validate_fingerprint(self.gate_id)
        require(
            self.gate_id.startswith(("afre.mix_fixed_gate:", "afre.mix_gate_model:")),
            "explicit fixed/fitted gate required",
        )
        unique_ids(tuple(i for i, _ in self.expert_inputs), "mix_expert")
        unique_ids(self.gating_feature_ids, "mix_gating_feature")
        for _, binding_id in self.expert_inputs:
            if binding_id:
                validate_fingerprint(binding_id, "mix_binding")


@contract("mix_contribution")
@dataclass(frozen=True, slots=True)
class ExpertContribution(Artifact):
    expert_id: str
    binding_id: str | None
    original_weight: float
    effective_weight: float
    value: float | None
    contribution: float | None
    reason: str

    def _validate(self) -> None:
        validate_fingerprint(self.expert_id, "mix_expert")
        if self.binding_id:
            validate_fingerprint(self.binding_id, "mix_binding")
        require(
            self.original_weight >= 0 and self.effective_weight >= 0,
            "negative expert contribution weight",
        )
        require(
            (self.contribution is None) == (self.value is None),
            "missing expert must remain missing",
        )
        require(
            self.value is not None or self.effective_weight == 0,
            "missing expert cannot contribute",
        )
        if self.value is not None:
            require(
                self.contribution == self.effective_weight * self.value,
                "expert contribution arithmetic mismatch",
            )


@contract("mix_forecast")
@dataclass(frozen=True, slots=True)
class MixtureForecast(Artifact):
    request: MixtureRequest
    security: StableSecurityId
    origin: ForecastOrigin
    target_definition_id: str
    partition: Partition
    gating_mode: GateMode
    contributions: tuple[ExpertContribution, ...]
    value: float
    distribution: MixtureDistribution | None
    probability_state: str
    fallback_id: str | None
    available_ns: int

    def _normalize(self) -> None:
        self.ordered("contributions", "expert_id")

    def _validate(self) -> None:
        validate_fingerprint(self.target_definition_id, "target_definition")
        require(
            self.security.instrument == self.origin.instrument,
            "mixture stable security identity",
        )
        require(
            tuple(c.expert_id for c in self.contributions)
            == tuple(i for i, _ in self.request.expert_inputs),
            "mixture expert grid mismatch",
        )
        validate_weights(
            tuple((c.expert_id, c.effective_weight) for c in self.contributions),
            tuple(c.expert_id for c in self.contributions),
        )
        require(
            self.value
            == fsum(c.contribution for c in self.contributions if c.contribution is not None),
            "mixture sum mismatch",
        )
        require(
            self.origin.timestamp_ns
            <= self.request.computed_ns
            <= self.available_ns
            <= self.origin.availability_cutoff_ns,
            "mixture computation backdated/unavailable",
        )
        require(
            self.partition in (Partition.TRAIN, Partition.VALIDATION, Partition.TEST),
            "mixture requires admitted fold sample",
        )
        require(
            (self.distribution is not None) == (self.probability_state == "available"),
            "mixture probability state mismatch",
        )


@contract("mix_eval_pair")
@dataclass(frozen=True, slots=True)
class MixtureEvaluationPair(Artifact):
    forecast_id: str
    sample_id: str
    target_id: str
    origin_ns: int
    mixture: float
    truth: float
    experts: tuple[tuple[str, float | None], ...]
    probability_scores: tuple[ProbabilityScore, ...]


@contract("mix_expert_comparison")
@dataclass(frozen=True, slots=True)
class MatchedExpertComparison(Artifact):
    expert_id: str
    sample_truth_ids: tuple[tuple[str, str], ...]
    mixture_metrics: tuple[PointMetric, ...]
    expert_metrics: tuple[PointMetric, ...]
    deltas: tuple[PointMetric, ...]
    mixture_probability_scores: tuple[ProbabilityScore, ...] = ()
    expert_probability_scores: tuple[ProbabilityScore, ...] = ()
    probability_deltas: tuple[ProbabilityScore, ...] = ()


@contract("mix_evaluation")
@dataclass(frozen=True, slots=True)
class MixtureEvaluation(Artifact):
    expert_set_id: str
    gate_id: str
    fold_id: str
    partition: Partition
    forecast_ids: tuple[str, ...]
    pairs: tuple[MixtureEvaluationPair, ...]
    exclusions: tuple[tuple[str, str], ...]
    metrics: tuple[PointMetric, ...]
    comparisons: tuple[MatchedExpertComparison, ...]
    cohorts: tuple[tuple[str, tuple[PointMetric, ...]], ...]
    probability_scores: tuple[ProbabilityScore, ...]
    cutoff_ns: int
    available_ns: int
    test_evaluation_id: str | None
    thresholds: tuple[ThresholdRequest, ...] = ()

    def _normalize(self) -> None:
        object.__setattr__(self, "forecast_ids", tuple(sorted(self.forecast_ids)))
        self.ordered("pairs", "sample_id")
        self.ordered("comparisons", "expert_id")
        object.__setattr__(self, "exclusions", tuple(sorted(self.exclusions)))

    def _validate(self) -> None:
        unique_ids(self.forecast_ids, "mix_forecast")
        require(
            bool(self.forecast_ids) and self.available_ns >= self.cutoff_ns,
            "mixture evaluation request/time",
        )
        require(
            (self.test_evaluation_id is not None) == (self.partition is Partition.TEST),
            "mixture TEST access record required",
        )
        if self.test_evaluation_id:
            validate_fingerprint(self.test_evaluation_id, "r_test_evaluation")


@contract("mix_expert_diagnostic")
@dataclass(frozen=True, slots=True)
class ExpertDiagnostic(Artifact):
    expert_id: str
    mean_weight: float
    median_weight: float
    minimum_weight: float
    maximum_weight: float
    zero_weight_frequency: float
    availability_rate: float
    mean_signed_contribution: float | None
    mean_absolute_contribution: float | None
    contribution_frequency: float


@contract("mix_diagnostics")
@dataclass(frozen=True, slots=True)
class MixtureDiagnostics(Artifact):
    forecast_ids: tuple[str, ...]
    evaluation_id: str
    experts: tuple[ExpertDiagnostic, ...]
    correlations: tuple[tuple[str, str, PointMetric, PointMetric, float | None], ...]
    mean_effective_expert_count: float
    mean_weight_entropy: float
    fallback_frequency: float
    missingness_frequency: float

    def _normalize(self) -> None:
        object.__setattr__(self, "forecast_ids", tuple(sorted(self.forecast_ids)))
        self.ordered("experts", "expert_id")


@contract("mix_drift")
@dataclass(frozen=True, slots=True)
class GateDriftDiagnostic(Artifact):
    reference_diagnostics_id: str
    current_diagnostics_id: str
    weight_deltas: tuple[tuple[str, float], ...]
    availability_deltas: tuple[tuple[str, float], ...]
    error_delta: float | None
    cutoff_ns: int
    minimum_count: int
    state: str

    def _validate(self) -> None:
        require(
            self.minimum_count > 0 and self.state in ("available", "insufficient-data"),
            "mixture drift state/count",
        )


@contract("mix_calibration")
@dataclass(frozen=True, slots=True)
class MixtureCalibrationAssessment(Artifact):
    forecast_id: str
    observation_ids: tuple[str, ...]
    cutoff_ns: int
    minimum_count: int
    status: MixtureCalibrationStatus
    proposed_component_state_id: str | None = None

    def _normalize(self) -> None:
        object.__setattr__(self, "observation_ids", tuple(sorted(self.observation_ids)))

    def _validate(self) -> None:
        unique_ids(self.observation_ids, "mix_forecast")
        require(
            self.minimum_count > 0 and self.status is not MixtureCalibrationStatus.SUPPORTED,
            "mixture calibrator fitting is unavailable",
        )


@contract("mix_ranking")
@dataclass(frozen=True, slots=True)
class MixtureRanking(Artifact):
    ranking_id: str
    forecast_ids: tuple[str, ...]
    signal_ids: tuple[str, ...]

    def _normalize(self) -> None:
        for name in ("forecast_ids", "signal_ids"):
            object.__setattr__(self, name, tuple(sorted(getattr(self, name))))


@contract("mix_rank_evaluation")
@dataclass(frozen=True, slots=True)
class MixtureRankEvaluation(Artifact):
    mixture_ranking_id: str
    matched_evaluation_id: str
    cross_section_evaluation_id: str


@contract("mix_audit")
@dataclass(frozen=True, slots=True)
class MixtureAudit(Artifact):
    root_id: str
    evidence_ids: tuple[str, ...]
    checks: tuple[str, ...]

    def _normalize(self) -> None:
        object.__setattr__(self, "evidence_ids", tuple(sorted(self.evidence_ids)))
        object.__setattr__(self, "checks", tuple(sorted(self.checks)))

    def _validate(self) -> None:
        unique_ids(self.evidence_ids)

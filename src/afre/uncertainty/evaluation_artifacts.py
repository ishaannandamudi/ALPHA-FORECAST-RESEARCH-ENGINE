"""Later truth, separate coverage/sharpness, matched comparisons and descriptive drift."""

from dataclasses import dataclass

from afre.ids import validate_fingerprint
from afre.probabilistic.artifacts import ProbabilityScore
from afre.probabilistic.definitions import ThresholdRequest
from afre.research_datasets.schema import Partition
from afre.schema import Artifact, contract, require
from afre.statistical_models.artifacts import PointMetric, unique_ids
from afre.uncertainty.schema import IdentifiabilityStatus


@contract("unc_evaluation_spec")
@dataclass(frozen=True, slots=True)
class UncertaintyEvaluationSpec(Artifact):
    minimum_count: int = 2
    bucket_count: int = 3
    thresholds: tuple[ThresholdRequest, ...] = ()
    uncertainty_measure: str = "total-predictive-variance-v1"
    bucket_policy: str = "ordinal-rank-equal-count-value-sample-ties-v1"

    def _normalize(self) -> None:
        require(
            len(set(self.thresholds)) == len(self.thresholds), "duplicate uncertainty events"
        )
        object.__setattr__(
            self,
            "thresholds",
            tuple(sorted(self.thresholds, key=lambda t: (t.value, t.comparison.value))),
        )

    def _validate(self) -> None:
        require(
            2 <= self.minimum_count <= 2000
            and 1 <= self.bucket_count <= 20
            and len(self.thresholds) <= 32
            and self.uncertainty_measure == "total-predictive-variance-v1"
            and self.bucket_policy == "ordinal-rank-equal-count-value-sample-ties-v1",
            "uncertainty evaluation policy/bounds",
        )


@contract("unc_evaluation_pair")
@dataclass(frozen=True, slots=True)
class UncertaintyEvaluationPair(Artifact):
    evaluation_spec_id: str
    decomposition_id: str
    forecast_id: str
    sample_id: str
    target_id: str
    prediction: float
    truth: float
    variance: float | None
    interval_width: float | None
    covered: bool | None
    scores: tuple[ProbabilityScore, ...]

    def _validate(self) -> None:
        for value, domain in (
            (self.evaluation_spec_id, "unc_evaluation_spec"),
            (self.decomposition_id, "unc_decomposition"),
            (self.sample_id, "r_sample"),
            (self.target_id, "target_vintage"),
        ):
            validate_fingerprint(value, domain)
        validate_fingerprint(self.forecast_id)
        require(
            (self.interval_width is None) == (self.covered is None),
            "coverage interval mismatch",
        )
        require(self.variance is None or self.variance >= 0, "negative predictive variance")
        require(
            self.interval_width is None or self.interval_width >= 0, "negative interval width"
        )


@contract("unc_coverage")
@dataclass(frozen=True, slots=True)
class UncertaintyCoverage(Artifact):
    sample_ids: tuple[str, ...]
    interval_count: int
    variance_count: int
    nominal_coverage: float
    empirical_coverage: float | None
    coverage_error: float | None
    mean_width: float | None
    mean_variance: float | None
    status: IdentifiabilityStatus

    def _normalize(self) -> None:
        unique_ids(self.sample_ids, "r_sample")
        object.__setattr__(self, "sample_ids", tuple(sorted(self.sample_ids)))

    def _validate(self) -> None:
        require(
            0 <= self.interval_count <= len(self.sample_ids)
            and 0 <= self.variance_count <= len(self.sample_ids)
            and 0 < self.nominal_coverage < 1,
            "coverage counts/nominal level",
        )
        require(
            (self.empirical_coverage is None)
            == (self.coverage_error is None)
            == (self.mean_width is None),
            "coverage/sharpness availability mismatch",
        )
        if self.empirical_coverage is not None:
            require(
                0 <= self.empirical_coverage <= 1
                and self.coverage_error == self.empirical_coverage - self.nominal_coverage,
                "coverage error arithmetic",
            )


@contract("unc_bucket")
@dataclass(frozen=True, slots=True)
class UncertaintyBucket(Artifact):
    index: int
    sample_ids: tuple[str, ...]
    minimum_variance: float
    maximum_variance: float
    mean_variance: float
    mean_absolute_error: float | None
    mean_squared_error: float | None
    status: IdentifiabilityStatus

    def _normalize(self) -> None:
        unique_ids(self.sample_ids, "r_sample")
        object.__setattr__(self, "sample_ids", tuple(sorted(self.sample_ids)))

    def _validate(self) -> None:
        require(
            self.index >= 0
            and bool(self.sample_ids)
            and 0 <= self.minimum_variance <= self.mean_variance <= self.maximum_variance,
            "uncertainty bucket range/support",
        )


@contract("unc_error_diagnostic")
@dataclass(frozen=True, slots=True)
class UncertaintyErrorDiagnostic(Artifact):
    sample_ids: tuple[str, ...]
    absolute_pearson: PointMetric
    absolute_spearman: PointMetric
    squared_pearson: PointMetric
    squared_spearman: PointMetric
    monotonic_bucket_error: bool | None

    def _normalize(self) -> None:
        unique_ids(self.sample_ids, "r_sample")
        object.__setattr__(self, "sample_ids", tuple(sorted(self.sample_ids)))


@contract("unc_evaluation")
@dataclass(frozen=True, slots=True)
class UncertaintyEvaluation(Artifact):
    evaluation_spec_id: str
    decomposition_ids: tuple[str, ...]
    pairs: tuple[UncertaintyEvaluationPair, ...]
    fold_id: str
    target_definition_id: str
    horizon_id: str
    partition: Partition
    interval_levels: tuple[float, float]
    coverage: UncertaintyCoverage
    cohorts: tuple[tuple[str, UncertaintyCoverage], ...]
    buckets: tuple[UncertaintyBucket, ...]
    error_diagnostic: UncertaintyErrorDiagnostic
    scores: tuple[ProbabilityScore, ...]
    cutoff_ns: int
    available_ns: int
    test_evaluation_id: str | None

    def _normalize(self) -> None:
        unique_ids(self.decomposition_ids, "unc_decomposition")
        object.__setattr__(self, "decomposition_ids", tuple(sorted(self.decomposition_ids)))
        self.ordered("pairs", "sample_id")
        object.__setattr__(self, "cohorts", tuple(sorted(self.cohorts)))

    def _validate(self) -> None:
        validate_fingerprint(self.evaluation_spec_id, "unc_evaluation_spec")
        validate_fingerprint(self.fold_id, "r_fold")
        validate_fingerprint(self.target_definition_id, "target_definition")
        validate_fingerprint(self.horizon_id)
        require(
            bool(self.pairs)
            and len(self.pairs) == len(self.decomposition_ids)
            and {p.decomposition_id for p in self.pairs} == set(self.decomposition_ids)
            and self.available_ns >= self.cutoff_ns,
            "uncertainty evaluation grid/time",
        )
        require(
            (self.test_evaluation_id is not None) == (self.partition is Partition.TEST)
            and self.partition in (Partition.VALIDATION, Partition.TEST),
            "uncertainty TEST seal",
        )
        if self.test_evaluation_id:
            validate_fingerprint(self.test_evaluation_id, "r_test_evaluation")


@contract("unc_comparison")
@dataclass(frozen=True, slots=True)
class UncertaintyComparison(Artifact):
    left_id: str
    right_id: str
    sample_truth_ids: tuple[tuple[str, str], ...]
    coverage_delta: float | None
    width_delta: float | None
    variance_delta: float | None
    available_ns: int

    def _normalize(self) -> None:
        object.__setattr__(self, "sample_truth_ids", tuple(sorted(self.sample_truth_ids)))

    def _validate(self) -> None:
        validate_fingerprint(self.left_id, "unc_evaluation")
        validate_fingerprint(self.right_id, "unc_evaluation")
        require(
            self.left_id != self.right_id and bool(self.sample_truth_ids),
            "matched comparison identity",
        )


@contract("unc_drift")
@dataclass(frozen=True, slots=True)
class UncertaintyDrift(Artifact):
    evaluation_ids: tuple[str, ...]
    mean_variances: tuple[float | None, ...]
    variance_shifts: tuple[float | None, ...]
    coverage_errors: tuple[float | None, ...]
    error_correlations: tuple[float | None, ...]
    component_shares: tuple[tuple[tuple[str, float | None], ...], ...]
    available_ns: int
    behavior: str = "descriptive-no-refit-no-selection-v1"

    def _validate(self) -> None:
        unique_ids(self.evaluation_ids, "unc_evaluation")
        require(
            2 <= len(self.evaluation_ids) <= 32
            and len(self.mean_variances)
            == len(self.coverage_errors)
            == len(self.error_correlations)
            == len(self.component_shares)
            == len(self.evaluation_ids)
            and len(self.variance_shifts) == len(self.evaluation_ids) - 1
            and self.behavior == "descriptive-no-refit-no-selection-v1",
            "drift windows/behavior",
        )

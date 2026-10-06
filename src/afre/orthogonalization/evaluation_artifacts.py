"""Separate held-out redundancy, fixed-model incremental evidence and descriptive stability."""

from dataclasses import dataclass

from afre.ids import validate_fingerprint
from afre.research_datasets.schema import Partition
from afre.schema import Artifact, contract, require
from afre.statistical_models.artifacts import PointMetric, unique_ids


@contract("ort_target_models")
@dataclass(frozen=True, slots=True)
class PredictiveModelPair(Artifact):
    projection_id: str
    row_ids: tuple[str, ...]
    target_ids: tuple[str, ...]
    truths: tuple[float, ...]
    base_intercept: float
    base_coefficients: tuple[float, ...]
    augmented_intercept: float
    augmented_coefficients: tuple[float, ...]
    augmented_uses_residual: bool
    cutoff_ns: int
    computed_ns: int
    available_ns: int

    def _validate(self) -> None:
        validate_fingerprint(self.projection_id, "ort_projection")
        unique_ids(self.row_ids, "ort_row")
        unique_ids(self.target_ids, "target_vintage")
        require(
            len(self.row_ids) == len(self.target_ids) == len(self.truths)
            and len(self.augmented_coefficients) == len(self.base_coefficients) + 1,
            "matched base/augmented model dimensions",
        )
        require(
            self.cutoff_ns <= self.computed_ns <= self.available_ns,
            "target model computation clocks",
        )


@contract("ort_evaluation")
@dataclass(frozen=True, slots=True)
class RedundancyEvaluation(Artifact):
    projection_id: str
    residual_ids: tuple[str, ...]
    sample_ids: tuple[str, ...]
    partition: Partition
    projection_metrics: tuple[PointMetric, ...]
    candidate_variance: float | None
    residual_variance: float | None
    residual_variance_ratio: float | None
    variance_redundancy_fraction: float | None
    raw_reference_correlations: tuple[PointMetric, ...]
    residual_reference_correlations: tuple[PointMetric, ...]
    predictive_pair_id: str | None
    target_ids: tuple[str, ...]
    truths: tuple[float, ...]
    base_metrics: tuple[PointMetric, ...]
    augmented_metrics: tuple[PointMetric, ...]
    incremental_metrics: tuple[PointMetric, ...]
    raw_target_correlations: tuple[PointMetric, ...]
    residual_target_correlations: tuple[PointMetric, ...]
    partial_target_correlations: tuple[PointMetric, ...]
    origin_information_coefficients: tuple[tuple[int, PointMetric, PointMetric], ...]
    cutoff_ns: int
    available_ns: int
    test_evaluation_id: str | None

    def _normalize(self) -> None:
        unique_ids(self.residual_ids, "ort_value")
        unique_ids(self.sample_ids, "r_sample")

    def _validate(self) -> None:
        validate_fingerprint(self.projection_id, "ort_projection")
        require(
            bool(self.residual_ids)
            and len(self.sample_ids) <= len(self.residual_ids)
            and self.available_ns >= self.cutoff_ns,
            "evaluation counts/clocks",
        )
        require(
            (self.test_evaluation_id is not None) == (self.partition is Partition.TEST),
            "orthogonal TEST seal required",
        )
        if self.test_evaluation_id:
            validate_fingerprint(self.test_evaluation_id, "r_test_evaluation")
        require(
            len(self.target_ids) == len(self.truths)
            and (not self.target_ids or len(self.truths) == len(self.sample_ids)),
            "exact heldout truth intersection",
        )
        require(
            (self.residual_variance_ratio is None)
            == (self.variance_redundancy_fraction is None),
            "variance ratio/fraction status",
        )
        if self.residual_variance_ratio is not None:
            require(
                self.residual_variance_ratio >= 0
                and self.variance_redundancy_fraction == 1 - self.residual_variance_ratio,
                "named variance-ratio semantics",
            )


@contract("ort_partial")
@dataclass(frozen=True, slots=True)
class PartialCorrelation(Artifact):
    left_residual_ids: tuple[str, ...]
    right_residual_ids: tuple[str, ...]
    sample_ids: tuple[str, ...]
    pearson: PointMetric
    residual_rank_correlation: PointMetric
    available_ns: int
    semantics: str = "correlation-of-frozen-TRAIN-linear-residuals-not-independence-v1"

    def _validate(self) -> None:
        unique_ids(self.sample_ids, "r_sample")
        require(
            len(self.left_residual_ids)
            == len(self.right_residual_ids)
            == len(self.sample_ids)
            > 0
            and self.semantics
            == "correlation-of-frozen-TRAIN-linear-residuals-not-independence-v1",
            "partial residual intersection/semantics",
        )


@contract("ort_stability")
@dataclass(frozen=True, slots=True)
class RedundancyStability(Artifact):
    evaluation_ids: tuple[str, ...]
    coefficient_ranges: tuple[tuple[float, float], ...]
    residual_variance_ratios: tuple[float | None, ...]
    correlation_values: tuple[tuple[float | None, ...], ...]
    available_ns: int
    behavior: str = "descriptive-compatible-windows-no-refit-no-pruning-v1"

    def _validate(self) -> None:
        unique_ids(self.evaluation_ids, "ort_evaluation")
        require(
            2 <= len(self.evaluation_ids) <= 32
            and len(self.residual_variance_ratios)
            == len(self.correlation_values)
            == len(self.evaluation_ids)
            and self.behavior == "descriptive-compatible-windows-no-refit-no-pruning-v1",
            "stability fixed behavior/windows",
        )

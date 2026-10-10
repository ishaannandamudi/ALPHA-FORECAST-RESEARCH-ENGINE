"""Immutable common intersections and descriptive diagnostics, never selectors."""

from dataclasses import dataclass

from afre.schema import Artifact, contract, require
from afre.statistical_models.artifacts import PointMetric


@contract("fus_pair_diversity")
@dataclass(frozen=True, slots=True)
class FusionPairDiversity(Artifact):
    left_id: str
    right_id: str
    pearson: PointMetric
    spearman: PointMetric
    error_correlation: PointMetric | None
    mean_absolute_disagreement: float | None
    sign_agreement: float | None


@contract("fus_diversity")
@dataclass(frozen=True, slots=True)
class DiversityMatrix(Artifact):
    source_ids: tuple[str, ...]
    observation_ids: tuple[str, ...]
    sample_ids: tuple[str, ...]
    excluded_sample_ids: tuple[str, ...]
    pairs: tuple[FusionPairDiversity, ...]
    truth_ids: tuple[str, ...]
    cutoff_ns: int | None
    available_ns: int

    def _normalize(self) -> None:
        for name in (
            "source_ids",
            "observation_ids",
            "sample_ids",
            "excluded_sample_ids",
            "truth_ids",
        ):
            values = getattr(self, name)
            require(len(set(values)) == len(values), "distinct diversity identifiers")
            object.__setattr__(self, name, tuple(sorted(values)))
        object.__setattr__(
            self, "pairs", tuple(sorted(self.pairs, key=lambda p: (p.left_id, p.right_id)))
        )

    def _validate(self) -> None:
        require(
            0 < len(self.source_ids) <= 16
            and len(self.sample_ids) <= 2000
            and len(self.pairs) == len(self.source_ids) ** 2 <= 256
            and (self.cutoff_ns is None or self.cutoff_ns <= self.available_ns),
            "diversity matrix bounds/clocks",
        )


@contract("fus_eval_pair")
@dataclass(frozen=True, slots=True)
class FusionEvaluationPair(Artifact):
    sample_id: str
    forecast_id: str
    truth_id: str
    truth: float
    fused: float
    component_values: tuple[tuple[str, float], ...]


@contract("fus_comparison")
@dataclass(frozen=True, slots=True)
class FusionComparison(Artifact):
    artifact_id: str
    forecast_ids: tuple[str, ...]
    pairs: tuple[FusionEvaluationPair, ...]
    exclusions: tuple[tuple[str, str], ...]
    fused_metrics: tuple[PointMetric, ...]
    component_metrics: tuple[tuple[str, tuple[PointMetric, ...]], ...]
    deltas: tuple[tuple[str, str, float | None], ...]
    probability_scores: tuple[tuple[str, str, float | None], ...]
    origin_ic: tuple[tuple[str, int, float | None, float | None], ...]
    cutoff_ns: int
    available_ns: int
    test_choice_id: str | None
    test_evaluation_id: str | None
    trial_pool_id: str | None = None
    sign_convention: str = "fused-minus-component;negative-error-delta-is-better-v1"

    def _normalize(self) -> None:
        object.__setattr__(self, "forecast_ids", tuple(sorted(self.forecast_ids)))
        self.ordered("pairs", "sample_id")
        object.__setattr__(self, "exclusions", tuple(sorted(self.exclusions)))

    def _validate(self) -> None:
        require(
            0 < len(self.forecast_ids) <= 2000
            and len(set(self.forecast_ids)) == len(self.forecast_ids)
            and self.cutoff_ns <= self.available_ns
            and len(self.pairs) <= 2000,
            "fusion evaluation bounds/clocks",
        )
        require(
            self.sign_convention == "fused-minus-component;negative-error-delta-is-better-v1"
            and (self.test_choice_id is None) == (self.test_evaluation_id is None),
            "comparison semantics/TEST authority",
        )


@contract("fus_weight_stability")
@dataclass(frozen=True, slots=True)
class FusionWeightStability(Artifact):
    artifact_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    ranges: tuple[tuple[str, float, float, bool], ...]
    concentrations: tuple[tuple[str, float], ...]

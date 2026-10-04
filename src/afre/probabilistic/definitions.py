"""Immutable fixed uncertainty assumptions; no calibration or family selection."""

from dataclasses import dataclass

from afre.ids import validate_fingerprint
from afre.probabilistic.schema import (
    APPROXIMATION_VERSION,
    IMPLEMENTATION_VERSION,
    DistributionFamily,
    ObservationPolicy,
    QuantileConvention,
    ResidualCentering,
    ScalePolicy,
    ThresholdComparison,
)
from afre.schema import Artifact, contract, require
from afre.target_engine.definitions import TargetDefinition


@contract("p_quantiles")
@dataclass(frozen=True, slots=True)
class QuantileDefinition(Artifact):
    levels: tuple[float, ...]
    convention: QuantileConvention = QuantileConvention.LINEAR_N_MINUS_ONE
    implementation_version: str = "type7-v1"

    def _normalize(self) -> None:
        object.__setattr__(self, "levels", tuple(sorted(self.levels)))

    def _validate(self) -> None:
        require(
            0 < len(self.levels) <= 256
            and len(set(self.levels)) == len(self.levels)
            and all(0 < q < 1 for q in self.levels)
            and 0.5 in self.levels,
            "quantiles require unique interior levels and explicit median",
        )


@contract("p_threshold")
@dataclass(frozen=True, slots=True)
class ThresholdRequest(Artifact):
    value: float
    comparison: ThresholdComparison


@contract("p_thresholds")
@dataclass(frozen=True, slots=True)
class ThresholdDefinition(Artifact):
    requests: tuple[ThresholdRequest, ...]

    def _normalize(self) -> None:
        object.__setattr__(
            self,
            "requests",
            tuple(sorted(self.requests, key=lambda r: (r.value, r.comparison.value))),
        )

    def _validate(self) -> None:
        require(
            len(self.requests) <= 256 and len(set(self.requests)) == len(self.requests),
            "threshold count/duplicates",
        )


@contract("p_scale_spec")
@dataclass(frozen=True, slots=True)
class ScaleSpec(Artifact):
    policy: ScalePolicy
    fixed_scale: float | None = None
    mad_consistency_factor: float = 1.482602218505602

    def _validate(self) -> None:
        require(
            (self.fixed_scale is not None) == (self.policy is ScalePolicy.FIXED_SCALE),
            "fixed scale/policy mismatch",
        )
        require(
            self.fixed_scale is None or self.fixed_scale > 0, "fixed scale must be positive"
        )
        require(self.mad_consistency_factor > 0, "positive MAD consistency factor")


@contract("p_spec")
@dataclass(frozen=True, slots=True)
class ProbabilisticModelSpec(Artifact):
    point_model_id: str
    family: DistributionFamily
    observation_policy: ObservationPolicy
    residual_centering: ResidualCentering
    scale: ScaleSpec
    quantiles: QuantileDefinition
    thresholds: ThresholdDefinition
    fold_id: str
    target: TargetDefinition
    training_cutoff_ns: int
    random_seed: int
    implementation_version: str = IMPLEMENTATION_VERSION
    approximation_version: str = APPROXIMATION_VERSION

    def _validate(self) -> None:
        validate_fingerprint(self.point_model_id, "m_artifact")
        validate_fingerprint(self.fold_id, "r_fold")
        require(0 <= self.random_seed < 2**64, "probability seed outside uint64")
        require(
            self.observation_policy is not ObservationPolicy.TRAIN_TARGETS
            or self.residual_centering is ResidualCentering.RAW,
            "unconditional targets cannot be silently centered",
        )
        if self.family is not DistributionFamily.GAUSSIAN_LOCATION_SCALE:
            require(
                self.scale.policy is ScalePolicy.TRAIN_RESIDUAL_STD,
                "empirical/quantile scale is descriptive population STD only",
            )
        else:
            require(
                all(1e-12 <= q <= 1 - 1e-12 for q in self.quantiles.levels),
                "Gaussian quantile numerical domain",
            )
        require(
            self.family is not DistributionFamily.QUANTILE_SET or not self.thresholds.requests,
            "quantile-only family does not define event probabilities",
        )


@contract("p_interval")
@dataclass(frozen=True, slots=True)
class QuantileInterval(Artifact):
    lower: float
    upper: float

    def _validate(self) -> None:
        require(0 < self.lower < self.upper < 1, "invalid quantile interval")


@contract("p_evaluation_protocol")
@dataclass(frozen=True, slots=True)
class ProbabilisticEvaluationProtocol(Artifact):
    intervals: tuple[QuantileInterval, ...] = ()
    pit_bins: int = 10
    implementation_version: str = "proper-scores-v1"

    def _normalize(self) -> None:
        object.__setattr__(
            self, "intervals", tuple(sorted(self.intervals, key=lambda r: (r.lower, r.upper)))
        )

    def _validate(self) -> None:
        require(
            len(self.intervals) <= 256 and len(set(self.intervals)) == len(self.intervals),
            "interval count/duplicates",
        )
        require(1 <= self.pit_bins <= 100, "PIT histogram bin bound")

"""Closed probability families, assumptions, score states and resource limits."""

from dataclasses import dataclass, fields
from enum import Enum

from afre.schema import Artifact, contract, enum, require

IMPLEMENTATION_VERSION = "probabilistic-v1"
APPROXIMATION_VERSION = "erfc-normaldist-v1"


@enum
class DistributionFamily(Enum):
    EMPIRICAL_RESIDUAL = "empirical_residual"
    GAUSSIAN_LOCATION_SCALE = "gaussian_location_scale"
    QUANTILE_SET = "quantile_set"


@enum
class ObservationPolicy(Enum):
    POINT_MODEL_RESIDUALS = "point_model_residuals"
    TRAIN_TARGETS = "train_targets"


@enum
class ResidualCentering(Enum):
    RAW = "raw"
    CENTER_MEAN = "center_mean"


@enum
class ScalePolicy(Enum):
    TRAIN_RESIDUAL_STD = "train_residual_std"
    TRAIN_RESIDUAL_MAD_SCALED = "train_residual_mad_scaled"
    FIXED_SCALE = "fixed_scale"


@enum
class QuantileConvention(Enum):
    LINEAR_N_MINUS_ONE = "linear_n_minus_one"


@enum
class ThresholdComparison(Enum):
    GT = "gt"
    GE = "ge"
    LT = "lt"
    LE = "le"


@enum
class DistributionState(Enum):
    REGULAR = "regular"
    DEGENERATE = "degenerate"


@enum
class ScoreName(Enum):
    COUNT = "count"
    NLL = "negative_log_likelihood"
    CRPS = "crps"
    PINBALL = "pinball"
    BRIER = "brier"
    QUANTILE_FREQUENCY = "quantile_frequency"
    INTERVAL_COVERAGE = "interval_coverage"
    INTERVAL_WIDTH = "interval_width"
    SHARPNESS_SCALE = "sharpness_scale"
    PIT_MEAN = "pit_mean"


@enum
class ScoreState(Enum):
    AVAILABLE = "available"
    UNSUPPORTED = "unsupported"
    INSUFFICIENT_OBSERVATIONS = "insufficient_observations"


@contract("p_bounds")
@dataclass(frozen=True, slots=True)
class ProbabilisticBounds(Artifact):
    observations: int = 50000
    quantiles: int = 64
    thresholds: int = 64
    forecasts: int = 10000
    evaluations: int = 10000
    audit_nodes: int = 100000
    audit_depth: int = 64
    serialized_bytes: int = 8 * 1024 * 1024
    work_cells: int = 2000000

    def _validate(self) -> None:
        require(
            all(getattr(self, f.name) > 0 for f in fields(self)), "positive probability bounds"
        )
        require(self.serialized_bytes <= 16 * 1024 * 1024, "decoder byte ceiling")
        require(self.audit_depth <= 64, "decoder depth ceiling")
        require(self.quantiles <= 256 and self.thresholds <= 256, "probability request ceiling")

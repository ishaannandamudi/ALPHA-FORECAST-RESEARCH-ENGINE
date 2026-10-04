"""Closed calibration methods, explicit evidence policies and resource limits."""

from dataclasses import dataclass, fields
from enum import Enum

from afre.schema import Artifact, contract, enum, require

IMPLEMENTATION_VERSION = "calibration-v1"


@enum
class CalibrationMethod(Enum):
    IDENTITY = "identity"
    BINNED_PROBABILITY = "binned_probability"
    ISOTONIC_PROBABILITY = "isotonic_probability"
    QUANTILE_OFFSET = "quantile_offset"
    CONFORMAL_ABSOLUTE_RESIDUAL = "conformal_absolute_residual"
    ROLLING_CONFORMAL = "rolling_conformal"


@enum
class CalibrationPartitionPolicy(Enum):
    DEDICATED_CALIBRATION = "dedicated_calibration"
    TRAIN_TAIL = "train_tail"
    ROLLING_PAST = "rolling_past"


@enum
class CalibrationOverlapStatus(Enum):
    DISJOINT_FROM_MODEL_TRAIN = "disjoint_from_model_train"
    OVERLAPS_MODEL_TRAIN = "overlaps_model_train"
    UNKNOWN = "unknown"


@enum
class EmptyBinPolicy(Enum):
    RAW = "raw"
    FAIL = "fail"


@enum
class TiePolicy(Enum):
    AGGREGATE_EQUAL_INPUT = "aggregate_equal_input"


@enum
class ExtrapolationPolicy(Enum):
    CLAMP_EDGE = "clamp_edge"


@enum
class DriftState(Enum):
    STABLE = "stable"
    DEGRADED = "degraded"
    INSUFFICIENT_DATA = "insufficient_data"
    UNKNOWN = "unknown"


@enum
class DriftMetric(Enum):
    BRIER = "brier"
    ECE = "ece"
    MAX_ABS_QUANTILE_GAP = "max_abs_quantile_gap"
    ABS_INTERVAL_GAP = "abs_interval_gap"


@contract("c_bounds")
@dataclass(frozen=True, slots=True)
class CalibrationBounds(Artifact):
    observations: int = 50000
    bins: int = 128
    blocks: int = 50000
    quantiles: int = 64
    events: int = 64
    conformal_scores: int = 50000
    rolling_window: int = 50000
    forecasts: int = 10000
    evaluations: int = 10000
    diagnostics: int = 10000
    audit_nodes: int = 100000
    audit_depth: int = 64
    serialized_bytes: int = 8 * 1024 * 1024
    work_cells: int = 2000000

    def _validate(self) -> None:
        require(
            all(getattr(self, f.name) > 0 for f in fields(self)), "positive calibration bounds"
        )
        require(self.serialized_bytes <= 16 * 1024 * 1024, "decoder byte ceiling")
        require(self.audit_depth <= 64, "decoder depth ceiling")
        require(
            max(self.bins, self.events, self.quantiles) <= 256, "calibration request ceiling"
        )

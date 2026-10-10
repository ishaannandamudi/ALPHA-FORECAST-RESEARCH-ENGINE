"""Closed descriptive health semantics and bounded research work."""

from dataclasses import dataclass
from enum import Enum

from afre.ids import validate_fingerprint
from afre.schema import Artifact, contract, enum, require


@enum
class HealthStatus(Enum):
    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    DEGRADED = "DEGRADED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    UNAVAILABLE = "UNAVAILABLE"
    INCOMPARABLE = "INCOMPARABLE"


@enum
class HealthDirection(Enum):
    HIGHER_WORSE = "HIGHER_WORSE"
    LOWER_WORSE = "LOWER_WORSE"
    ABSOLUTE_CHANGE_WORSE = "ABSOLUTE_CHANGE_WORSE"
    TWO_SIDED_RANGE = "TWO_SIDED_RANGE"


@enum
class HealthStatistic(Enum):
    DELTA = "DELTA"
    CURRENT = "CURRENT"
    RATIO = "RATIO"


@enum
class HealthIntersection(Enum):
    NATIVE_PER_WINDOW = "NATIVE_PER_WINDOW"
    COMMON_INTERSECTION = "COMMON_INTERSECTION"
    PAIRWISE_INTERSECTION = "PAIRWISE_INTERSECTION"


@enum
class HealthPairKey(Enum):
    SAMPLE = "SAMPLE"
    SECURITY = "SECURITY"


@enum
class HealthDiagnostic(Enum):
    INPUT_MEAN = "INPUT_MEAN"
    INPUT_STD = "INPUT_STD"
    INPUT_QUANTILE = "INPUT_QUANTILE"
    MISSINGNESS = "MISSINGNESS"
    INPUT_KS = "INPUT_KS"
    STANDARDIZED_MEAN = "STANDARDIZED_MEAN"
    PREDICTION_MEAN = "PREDICTION_MEAN"
    PREDICTION_STD = "PREDICTION_STD"
    PREDICTION_QUANTILE = "PREDICTION_QUANTILE"
    SIGN_FRACTION = "SIGN_FRACTION"
    PREDICTION_KS = "PREDICTION_KS"
    MEAN_ABSOLUTE_SHIFT = "MEAN_ABSOLUTE_SHIFT"
    PREDICTIVE_VARIANCE = "PREDICTIVE_VARIANCE"
    THRESHOLD_PROBABILITY = "THRESHOLD_PROBABILITY"
    INTERVAL_WIDTH = "INTERVAL_WIDTH"
    BIAS = "BIAS"
    MAE = "MAE"
    MSE = "MSE"
    RMSE = "RMSE"
    ERROR_VARIANCE = "ERROR_VARIANCE"
    ERROR_QUANTILE = "ERROR_QUANTILE"
    R_SQUARED = "R_SQUARED"
    CRPS = "CRPS"
    NLL = "NLL"
    IC = "IC"
    RANK_IC = "RANK_IC"
    COVERAGE = "COVERAGE"
    COVERAGE_ERROR = "COVERAGE_ERROR"
    ECE = "ECE"
    MCE = "MCE"
    RANK_DISPLACEMENT = "RANK_DISPLACEMENT"
    TOP_K_OVERLAP = "TOP_K_OVERLAP"
    SIGN_PERSISTENCE = "SIGN_PERSISTENCE"
    SCORE_DISPERSION = "SCORE_DISPERSION"
    PARAMETER_L1 = "PARAMETER_L1"
    PARAMETER_L2 = "PARAMETER_L2"
    RELATIVE_PARAMETER = "RELATIVE_PARAMETER"
    PARAMETER_SIGN_CHANGES = "PARAMETER_SIGN_CHANGES"
    PARAMETER_CORRELATION = "PARAMETER_CORRELATION"
    INTERCEPT = "INTERCEPT"
    TREE_SPLIT_RECURRENCE = "TREE_SPLIT_RECURRENCE"
    TREE_THRESHOLD = "TREE_THRESHOLD"
    TREE_PATH_RECURRENCE = "TREE_PATH_RECURRENCE"
    TREE_LEAF_SUPPORT = "TREE_LEAF_SUPPORT"
    SEQUENCE_DECAY = "SEQUENCE_DECAY"
    SEQUENCE_STATE_NORM = "SEQUENCE_STATE_NORM"
    SEQUENCE_AGGREGATE = "SEQUENCE_AGGREGATE"
    UNCERTAINTY_VARIANCE = "UNCERTAINTY_VARIANCE"
    UNCERTAINTY_SHARE = "UNCERTAINTY_SHARE"
    DISAGREEMENT = "DISAGREEMENT"
    RESIDUAL_VARIANCE_RATIO = "RESIDUAL_VARIANCE_RATIO"
    RAW_REFERENCE_CORRELATION = "RAW_REFERENCE_CORRELATION"
    INCREMENTAL_VALUE = "INCREMENTAL_VALUE"
    FUSION_DOMINANCE = "FUSION_DOMINANCE"
    EFFECTIVE_SOURCE_COUNT = "EFFECTIVE_SOURCE_COUNT"
    WEIGHT_ENTROPY = "WEIGHT_ENTROPY"
    CONTRIBUTION_MEAN = "CONTRIBUTION_MEAN"
    GROSS_EDGE = "GROSS_EDGE"
    COST = "COST"
    NET_EDGE = "NET_EDGE"
    TURNOVER = "TURNOVER"
    BREAK_EVEN_COST = "BREAK_EVEN_COST"
    QUALITY_FRACTION = "QUALITY_FRACTION"


TRUTH_DIAGNOSTICS = frozenset(
    {
        HealthDiagnostic.BIAS,
        HealthDiagnostic.MAE,
        HealthDiagnostic.MSE,
        HealthDiagnostic.RMSE,
        HealthDiagnostic.ERROR_VARIANCE,
        HealthDiagnostic.ERROR_QUANTILE,
        HealthDiagnostic.R_SQUARED,
        HealthDiagnostic.CRPS,
        HealthDiagnostic.NLL,
        HealthDiagnostic.IC,
        HealthDiagnostic.RANK_IC,
        HealthDiagnostic.COVERAGE,
        HealthDiagnostic.COVERAGE_ERROR,
        HealthDiagnostic.ECE,
        HealthDiagnostic.MCE,
    }
)
IMPLEMENTATION = "frozen-window-descriptive-health-v1"
PRECEDENCE = (
    HealthStatus.INCOMPARABLE,
    HealthStatus.UNAVAILABLE,
    HealthStatus.INSUFFICIENT_DATA,
    HealthStatus.DEGRADED,
    HealthStatus.WARNING,
    HealthStatus.HEALTHY,
)


def ids(value: Artifact, *names: str) -> None:
    for name in names:
        items = getattr(value, name)
        require(len(items) == len(set(items)), "duplicate health identities")
        for identity in items:
            validate_fingerprint(identity)
        object.__setattr__(value, name, tuple(sorted(items)))


@contract("hlt_bounds")
@dataclass(frozen=True, slots=True)
class HealthBounds(Artifact):
    metrics: int = 128
    windows: int = 64
    samples: int = 2000
    features: int = 256
    sources: int = 32
    cohorts: int = 32
    trend_windows: int = 64
    artifacts: int = 100000
    payload_bytes: int = 8 * 1024 * 1024
    snapshot_bytes: int = 128 * 1024 * 1024
    lineage_nodes: int = 100000
    lineage_depth: int = 64
    lineage_bytes: int = 16 * 1024 * 1024

    def _validate(self) -> None:
        for name, hard in (
            ("metrics", 128),
            ("windows", 64),
            ("samples", 2000),
            ("features", 256),
            ("sources", 32),
            ("cohorts", 32),
            ("trend_windows", 64),
            ("artifacts", 100000),
            ("payload_bytes", 8 * 1024 * 1024),
            ("snapshot_bytes", 128 * 1024 * 1024),
            ("lineage_nodes", 100000),
            ("lineage_depth", 64),
            ("lineage_bytes", 16 * 1024 * 1024),
        ):
            require(1 <= getattr(self, name) <= hard, "health bound exceeds hard limit")

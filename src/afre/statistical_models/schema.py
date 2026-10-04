"""Closed baseline families, numerical policies and explicit workload bounds."""

from dataclasses import dataclass, fields
from enum import Enum

from afre.schema import Artifact, contract, enum, require

IMPLEMENTATION_VERSION = "baseline-v1"
SOLVER_VERSION = "stdlib-v1"


@enum
class ModelFamily(Enum):
    UNCONDITIONAL_MEAN = "unconditional_mean"
    UNCONDITIONAL_MEDIAN = "unconditional_median"
    REFERENCE_VALUE = "reference_value"
    PERSISTENCE = "persistence"
    LINEAR_REGRESSION = "linear_regression"
    RIDGE_REGRESSION = "ridge_regression"
    LASSO_REGRESSION = "lasso_regression"
    ELASTIC_NET = "elastic_net"
    CROSS_SECTIONAL_LINEAR = "cross_sectional_linear"
    RESIDUAL_LINEAR = "residual_linear"


@enum
class InterceptPolicy(Enum):
    NONE = "none"
    GLOBAL = "global"
    WITHIN_ORIGIN = "within_origin"


@enum
class SolverIdentity(Enum):
    REFERENCE_STATISTIC = "reference_statistic"
    PIVOTED_HOUSEHOLDER_QR = "pivoted_householder_qr"
    COORDINATE_DESCENT = "coordinate_descent"


@enum
class RankDeficiencyPolicy(Enum):
    FAIL = "fail"
    RIDGE_REQUIRED = "ridge_required"


@enum
class NonconvergencePolicy(Enum):
    FAIL = "fail"
    RETURN_NONCONVERGED = "return_nonconverged"


@enum
class TrainingMissingPolicy(Enum):
    FAIL = "fail"
    SKIP = "skip"


@enum
class RowWeighting(Enum):
    EQUAL_ROWS = "equal_rows"


@enum
class PredictionScope(Enum):
    IN_SAMPLE = "in_sample"
    VALIDATION = "validation"
    TEST = "test"
    OUT_OF_SAMPLE_OTHER = "out_of_sample_other"


@enum
class MetricName(Enum):
    COUNT = "count"
    MEAN_ERROR = "mean_error"
    MAE = "mae"
    MSE = "mse"
    RMSE = "rmse"
    R_SQUARED = "r_squared"
    PEARSON_CORRELATION = "pearson_correlation"
    SPEARMAN_CORRELATION = "spearman_correlation"
    DIRECTIONAL_ACCURACY = "directional_accuracy"


@enum
class MetricState(Enum):
    AVAILABLE = "available"
    INSUFFICIENT_OBSERVATIONS = "insufficient_observations"
    CONSTANT_TARGET = "constant_target"
    CONSTANT_PREDICTION = "constant_prediction"


@contract("m_bounds")
@dataclass(frozen=True, slots=True)
class ModelBounds(Artifact):
    samples: int = 50000
    features: int = 64
    coefficients: int = 65
    iterations: int = 10000
    predictions: int = 50000
    evaluations: int = 10000
    audit_nodes: int = 100000
    audit_depth: int = 64
    serialized_bytes: int = 8 * 1024 * 1024
    dense_cells: int = 4000000

    def _validate(self) -> None:
        require(all(getattr(self, f.name) > 0 for f in fields(self)), "positive model bounds")
        require(self.features <= 128, "stdlib dense feature ceiling is 128")
        require(self.serialized_bytes <= 16 * 1024 * 1024, "closed decoder byte ceiling")
        require(self.audit_depth <= 64, "closed decoder depth ceiling")

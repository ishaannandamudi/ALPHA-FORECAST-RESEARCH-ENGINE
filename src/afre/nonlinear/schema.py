"""Closed interaction policies and bounded deterministic research work."""

from dataclasses import dataclass, fields
from enum import Enum

from afre.schema import Artifact, contract, enum, require

NONLINEAR_IMPLEMENTATION = "nonlinear-v1"


@enum
class ScalarSourceKind(Enum):
    FEATURE = "feature"
    EXTERNAL_SIGNAL = "external_signal"
    EVENT_ATTRIBUTE = "event_attribute"
    REGIME_PROBABILITY = "regime_probability"
    EXPERT_POINT = "expert_point"
    MIXTURE_POINT = "mixture_point"


@enum
class InteractionTransform(Enum):
    IDENTITY = "identity"
    PRODUCT = "product"
    RATIO = "ratio"
    DIFFERENCE = "difference"
    ABS_DIFFERENCE = "abs_difference"
    SQUARE = "square"
    CUBE = "cube"
    LOG1P_SIGNED = "log1p_signed"
    CLIPPED_LINEAR = "clipped_linear"
    PIECEWISE_LINEAR = "piecewise_linear"


@enum
class InteractionMissingPolicy(Enum):
    FAIL = "fail"
    PROPAGATE_MISSING = "propagate_missing"
    DECLARED_FALLBACK = "declared_fallback"


@enum
class DenominatorPolicy(Enum):
    FAIL_ON_ZERO = "fail_on_zero"
    EPSILON_FLOOR = "epsilon_floor"
    MISSING_ON_ZERO = "missing_on_zero"


@enum
class KnotPolicy(Enum):
    FIXED = "fixed"
    TRAIN_QUANTILES = "train_quantiles"


@enum
class NonlinearFamily(Enum):
    LINEAR_ON_INTERACTIONS = "linear_on_interactions"
    LINEAR_PLUS_INTERACTIONS = "linear_plus_interactions"
    SHALLOW_REGRESSION_TREE = "shallow_regression_tree"


@enum
class NonlinearPreprocessing(Enum):
    NONE = "none"
    STANDARDIZE = "standardize"


@enum
class NonlinearMissingPolicy(Enum):
    FAIL = "fail"


@enum
class NonlinearCalibrationStatus(Enum):
    INSUFFICIENT_DATA = "insufficient_data"
    UNAVAILABLE = "unavailable"
    INCOMPATIBLE = "incompatible"


@contract("nl_bounds")
@dataclass(frozen=True, slots=True)
class NonlinearBounds(Artifact):
    interactions: int = 128
    features: int = 256
    training_rows: int = 50_000
    forecasts: int = 100_000
    split_candidates: int = 64
    tree_depth: int = 4
    work_cells: int = 2_000_000
    artifacts: int = 100_000
    evaluations: int = 1000
    audit_nodes: int = 100_000
    audit_depth: int = 64
    serialized_bytes: int = 8 * 1024 * 1024

    def _validate(self) -> None:
        require(
            all(getattr(self, f.name) > 0 for f in fields(self)), "positive nonlinear bounds"
        )
        require(
            self.interactions <= 128
            and self.features <= 256
            and self.tree_depth <= 4
            and self.split_candidates <= 64
            and self.audit_depth <= 64
            and self.serialized_bytes <= 16 * 1024 * 1024
            and max(
                self.training_rows,
                self.forecasts,
                self.artifacts,
                self.audit_nodes,
                self.work_cells,
            )
            <= 2_000_000,
            "nonlinear hard bounds",
        )

"""Closed multi-horizon policies and explicit resource limits."""

from dataclasses import dataclass
from enum import Enum

from afre.schema import Artifact, contract, enum, require

IMPLEMENTATION_VERSION = "multihorizon-v1"


@enum
class Architecture(Enum):
    INDEPENDENT_PER_HORIZON = "independent_per_horizon"
    SHARED_FEATURES_SEPARATE_MODELS = "shared_features_separate_models"
    SHARED_LINEAR_BACKBONE = "shared_linear_backbone"


@enum
class HorizonOrder(Enum):
    COMPARABLE_DURATION = "comparable_duration"
    EXPLICIT_CANONICAL = "explicit_canonical"


@enum
class ParameterOwnership(Enum):
    GLOBAL_SHARED = "global_shared"
    HORIZON_SPECIFIC = "horizon_specific"
    GROUP_SHARED = "group_shared"


@enum
class Completeness(Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


@enum
class ComponentState(Enum):
    AVAILABLE = "available"
    MISSING = "missing"
    UNSUPPORTED = "unsupported"


@enum
class DependenceMethod(Enum):
    NONE = "none"
    EMPIRICAL_RESIDUAL_COVARIANCE = "empirical_residual_covariance"


@enum
class Denominator(Enum):
    POPULATION = "population_n"
    SAMPLE = "sample_n_minus_one"


@contract("mh_bounds")
@dataclass(frozen=True, slots=True)
class MultiHorizonBounds(Artifact):
    horizons: int = 16
    samples: int = 100_000
    features: int = 128
    work_cells: int = 4_000_000
    forecasts: int = 100_000
    evaluations: int = 10_000
    audit_nodes: int = 100_000
    audit_depth: int = 64
    serialized_bytes: int = 8 * 1024 * 1024

    def _validate(self) -> None:
        require(
            all(
                v > 0
                for v in (
                    self.horizons,
                    self.samples,
                    self.features,
                    self.work_cells,
                    self.forecasts,
                    self.evaluations,
                    self.audit_nodes,
                    self.audit_depth,
                    self.serialized_bytes,
                )
            ),
            "positive multi-horizon bounds",
        )
        require(
            self.horizons <= 64
            and self.audit_depth <= 64
            and self.serialized_bytes <= 16 * 1024 * 1024,
            "multi-horizon hard bounds",
        )

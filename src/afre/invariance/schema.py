"""Closed descriptive research semantics; no causal proof or production decisions."""

from dataclasses import dataclass, fields
from enum import Enum

from afre.schema import Artifact, contract, enum, require

INVARIANCE_SCHEMA_VERSION = "1.0"
INVARIANCE_IMPLEMENTATION = "declared-environment-descriptive-v1"


@enum
class EnvironmentKind(Enum):
    TIME_WINDOW = "time_window"
    REGIME = "regime"
    EVENT = "event"
    SECTOR = "sector"
    INDUSTRY = "industry"
    UNIVERSE = "universe"
    MARKET_STATE = "market_state"
    DATA_QUALITY = "data_quality"
    CUSTOM = "custom"


@enum
class EnvironmentRule(Enum):
    TIME = "time"
    REGIME_STATE = "regime_state"
    EVENT_COHORT = "event_cohort"
    GROUP = "group"
    UNIVERSE = "universe"
    QUALITY = "quality"
    LABEL = "label"
    COMPOUND = "compound"


@enum
class EnvironmentState(Enum):
    INCLUDED = "included"
    EXCLUDED = "excluded"
    UNAVAILABLE = "unavailable"


@enum
class ComparabilityStatus(Enum):
    COMPARABLE = "comparable"
    PARTIALLY_COMPARABLE = "partially_comparable"
    INCOMPARABLE = "incomparable"
    INSUFFICIENT_DATA = "insufficient_data"
    UNAVAILABLE = "unavailable"


@enum
class SampleIntersectionPolicy(Enum):
    PER_ENVIRONMENT_NATIVE = "per_environment_native"
    COMMON_INTERSECTION = "common_intersection"
    PAIRWISE_INTERSECTION = "pairwise_intersection"


@enum
class StabilityWeighting(Enum):
    HARD_ONLY = "hard_only"
    EXPLICIT_MEMBERSHIP = "explicit_membership"


@enum
class StabilitySampleMode(Enum):
    TEMPORAL_PANEL = "temporal_panel"
    SAME_ORIGIN_CROSS_SECTION = "same_origin_cross_section"


@enum
class StabilityMetricName(Enum):
    MAE = "mae"
    MSE = "mse"
    RMSE = "rmse"
    R_SQUARED = "r_squared"
    PEARSON = "pearson"
    SPEARMAN = "spearman"
    SIGN_ACCURACY = "sign_accuracy"
    CRPS = "crps"
    NLL = "nll"
    BRIER = "brier"
    PINBALL = "pinball"
    COVERAGE = "coverage"
    COVERAGE_ERROR = "coverage_error"
    WIDTH = "width"
    PEARSON_IC = "pearson_ic"
    RANK_IC = "rank_ic"
    ECE = "ece"
    MCE = "mce"
    PREDICTION_MEAN = "prediction_mean"
    PREDICTIVE_VARIANCE = "predictive_variance"
    EXPERT_DISAGREEMENT = "expert_disagreement"
    COMPONENT_SHARE = "component_share"


@contract("inv_bounds")
@dataclass(frozen=True, slots=True)
class InvarianceBounds(Artifact):
    environments: int = 32
    compounds: int = 8
    samples: int = 2000
    forecasts: int = 2000
    metrics: int = 24
    features: int = 16
    windows: int = 32
    shift_cells: int = 64_000
    artifacts: int = 20_000
    serialized_bytes: int = 8_388_608
    audit_nodes: int = 100_000
    audit_depth: int = 64

    def _validate(self) -> None:
        maxima = (32, 8, 2000, 2000, 24, 16, 32, 64_000, 20_000, 8_388_608, 100_000, 64)
        require(
            all(
                1 <= getattr(self, f.name) <= m
                for f, m in zip(fields(self), maxima, strict=True)
            ),
            "invariance hard bound",
        )


def canonical_ids(value: Artifact, *names: str) -> None:
    from afre.ids import validate_fingerprint

    for name in names:
        ids = getattr(value, name)
        require(len(ids) == len(set(ids)), "duplicate invariance identity")
        for identity in ids:
            validate_fingerprint(identity)
        object.__setattr__(value, name, tuple(sorted(ids)))

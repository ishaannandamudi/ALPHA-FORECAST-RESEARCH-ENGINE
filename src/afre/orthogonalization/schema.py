"""Closed causal research-transform semantics; orthogonal never means independent."""

from dataclasses import dataclass, fields
from enum import Enum

from afre.schema import Artifact, contract, enum, require


@enum
class SignalSourceType(Enum):
    FEATURE = "feature"
    EXTERNAL = "external"
    GENERIC = "generic"
    EVENT = "event"
    REGIME = "regime"
    EXPERT = "expert"
    MIXTURE = "mixture"
    NONLINEAR = "nonlinear"
    SEQUENCE = "sequence"
    UNCERTAINTY = "uncertainty"
    SCALAR = "scalar"


@enum
class OrthogonalizationMode(Enum):
    TEMPORAL_PANEL = "temporal_panel"
    CROSS_SECTIONAL_HISTORICAL = "cross_sectional_historical"


@enum
class ProjectionIntercept(Enum):
    WITH_INTERCEPT = "with_intercept"
    NO_INTERCEPT = "no_intercept"


@enum
class ProjectionPreprocessing(Enum):
    NONE = "none"
    TRAIN_STANDARDIZE = "train_standardize"


@enum
class OrthogonalQuality(Enum):
    AVAILABLE = "available"
    MISSING = "missing"


@contract("ort_bounds")
@dataclass(frozen=True, slots=True)
class OrthogonalizationBounds(Artifact):
    references: int = 16
    candidates: int = 16
    rows: int = 2000
    cells: int = 2_000_000
    artifacts: int = 20_000
    serialized_bytes: int = 8_388_608
    windows: int = 32
    audit_nodes: int = 100_000
    audit_depth: int = 64

    def _validate(self) -> None:
        limits = (16, 16, 2000, 2_000_000, 20_000, 8_388_608, 32, 100_000, 64)
        require(
            all(
                1 <= getattr(self, f.name) <= m
                for f, m in zip(fields(self), limits, strict=True)
            ),
            "orthogonalization hard bound",
        )

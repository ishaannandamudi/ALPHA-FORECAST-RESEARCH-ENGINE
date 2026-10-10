"""Closed data-only fusion semantics; weight coefficients are not probabilities."""

from dataclasses import dataclass
from enum import Enum

from afre.schema import Artifact, contract, enum, require

IMPLEMENTATION = "explicit-causal-fusion-v1"


@enum
class FusionKind(Enum):
    POINT = "POINT"
    PROBABILISTIC = "PROBABILISTIC"
    SCALAR_SIGNAL = "SCALAR_SIGNAL"


@enum
class FusionFamily(Enum):
    FIXED_WEIGHT_POINT = "FIXED_WEIGHT_POINT"
    LEARNED_LINEAR_POINT = "LEARNED_LINEAR_POINT"
    FIXED_PROBABILITY_MIXTURE = "FIXED_PROBABILITY_MIXTURE"
    FIXED_SIGNAL_BLEND = "FIXED_SIGNAL_BLEND"


@enum
class FusionMissingness(Enum):
    FAIL = "FAIL"
    DROP_AND_RENORMALIZE = "DROP_AND_RENORMALIZE"
    USE_DECLARED_FALLBACK = "USE_DECLARED_FALLBACK"


@enum
class FusionWeights(Enum):
    SIMPLEX = "SIMPLEX"
    SIGNED_LINEAR = "SIGNED_LINEAR"
    UNCONSTRAINED_QR = "UNCONSTRAINED_QR"


@enum
class FusionNormalization(Enum):
    NONE = "NONE"
    EXPLICIT_SIMPLEX = "EXPLICIT_SIMPLEX"
    TRAIN_STANDARDIZE = "TRAIN_STANDARDIZE"


@enum
class FusionIntercept(Enum):
    WITH_INTERCEPT = "WITH_INTERCEPT"
    NO_INTERCEPT = "NO_INTERCEPT"


@enum
class FusionStatus(Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


@contract("fus_bounds")
@dataclass(frozen=True, slots=True)
class FusionBounds(Artifact):
    sources: int = 16
    train_rows: int = 2000
    prediction_rows: int = 2000
    probability_components: int = 32
    probability_atoms: int = 2000
    diversity_cells: int = 256
    comparisons: int = 128
    artifacts: int = 100000
    payload_bytes: int = 8388608
    snapshot_bytes: int = 134217728
    publication_rows: int = 100000
    lineage_nodes: int = 100000
    lineage_depth: int = 64

    def _validate(self) -> None:
        from dataclasses import fields

        limits = (
            16,
            2000,
            2000,
            32,
            2000,
            256,
            128,
            100000,
            8388608,
            134217728,
            100000,
            100000,
            64,
        )
        require(
            all(
                1 <= getattr(self, f.name) <= m
                for f, m in zip(fields(self), limits, strict=True)
            ),
            "fusion hard bounds",
        )

"""Closed, data-only selection policies. No adaptive optimizer or TEST protocol."""

from dataclasses import dataclass
from enum import Enum

from afre.schema import Artifact, contract, enum, require

IMPLEMENTATION = "declared-exhaustive-native-selection-v1"


@enum
class SelectionCriterion(Enum):
    MIN_MSE = "MIN_MSE"
    MIN_MAE = "MIN_MAE"
    MAX_R2 = "MAX_R2"
    MIN_CRPS = "MIN_CRPS"
    MIN_NLL = "MIN_NLL"

    @property
    def maximize(self) -> bool:
        return self is SelectionCriterion.MAX_R2


@enum
class CandidateStatus(Enum):
    VALID = "VALID"
    FIT_FAILED = "FIT_FAILED"
    INCOMPATIBLE = "INCOMPATIBLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NUMERICAL_FAILURE = "NUMERICAL_FAILURE"


@enum
class SelectionStatus(Enum):
    COMPETITIVE = "COMPETITIVE"
    NONCOMPETITIVE = "NONCOMPETITIVE"
    NO_VALID_CANDIDATE = "NO_VALID_CANDIDATE"


@enum
class SelectionReadRole(Enum):
    PLANNING = "PLANNING"
    FIT = "FIT"
    VALIDATION = "VALIDATION"


@contract("sel_bounds")
@dataclass(frozen=True, slots=True)
class SelectionBounds(Artifact):
    candidates: int = 128
    dimensions: int = 16
    rows: int = 2000
    comparisons: int = 128
    artifacts: int = 100000
    payload_bytes: int = 8 * 1024 * 1024
    snapshot_bytes: int = 128 * 1024 * 1024
    publication_rows: int = 100000
    lineage_nodes: int = 100000
    lineage_depth: int = 64

    def _validate(self) -> None:
        require(
            1 <= self.candidates <= 128
            and 1 <= self.dimensions <= 16
            and 1 <= self.rows <= 2000
            and 1 <= self.comparisons <= 128
            and 1 <= self.artifacts <= 100000
            and 1 <= self.payload_bytes <= 8388608
            and 1 <= self.snapshot_bytes <= 134217728
            and 1 <= self.publication_rows <= 100000
            and 1 <= self.lineage_nodes <= 100000
            and 1 <= self.lineage_depth <= 64,
            "selection absolute bounds",
        )

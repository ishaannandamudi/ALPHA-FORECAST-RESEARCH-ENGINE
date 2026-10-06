"""Closed sequence policies and hard research resource limits."""

from dataclasses import dataclass
from enum import Enum

from afre.schema import Artifact, contract, enum, require

SEQUENCE_IMPLEMENTATION = "causal-sequence-v1"


@enum
class SequenceWindowMode(Enum):
    FIXED_OBSERVATION_COUNT = "fixed_observation_count"
    ELAPSED_DURATION = "elapsed_duration"


@enum
class SequencePadding(Enum):
    FAIL_IF_SHORT = "fail_if_short"
    LEFT_PAD_MASKED = "left_pad_masked"
    RIGHT_PAD_MASKED = "right_pad_masked"


@enum
class SequenceRevisionPolicy(Enum):
    LATEST_AVAILABLE_REVISION = "latest_available_revision"
    EXACT_VINTAGE = "exact_vintage"
    FAIL_ON_MULTIPLE = "fail_on_multiple"


@enum
class SequenceTimeEncoding(Enum):
    NONE = "none"
    DELTA_SECONDS = "delta_seconds"
    AGE_FROM_ORIGIN = "age_from_origin"
    NORMALIZED_POSITION = "normalized_position"


@enum
class SequenceCompleteness(Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    INSUFFICIENT = "insufficient"
    UNAVAILABLE = "unavailable"


@enum
class SequenceObservationQuality(Enum):
    PRESENT = "present"
    MISSING = "missing"
    STALE = "stale"
    INVALID = "invalid"
    WITHHELD = "withheld"


@enum
class SequenceFamily(Enum):
    EXPONENTIAL_DECAY_LINEAR = "exponential_decay_linear"
    LINEAR_STATE_SPACE = "linear_state_space"


@enum
class SequencePreprocessing(Enum):
    NONE = "none"
    STANDARDIZE = "standardize"


@contract("sq_bounds")
@dataclass(frozen=True, slots=True)
class SequenceBounds(Artifact):
    length: int = 128
    features: int = 16
    observations: int = 100_000
    training_rows: int = 2000
    forecasts: int = 20_000
    work_cells: int = 2_000_000
    serialized_bytes: int = 8_388_608
    audit_nodes: int = 100_000
    audit_depth: int = 64

    def _validate(self) -> None:
        limits = (128, 16, 100_000, 2000, 20_000, 2_000_000, 8_388_608, 100_000, 64)
        values = (
            self.length,
            self.features,
            self.observations,
            self.training_rows,
            self.forecasts,
            self.work_cells,
            self.serialized_bytes,
            self.audit_nodes,
            self.audit_depth,
        )
        require(
            all(1 <= x <= limit for x, limit in zip(values, limits, strict=True)),
            "sequence hard resource bound",
        )

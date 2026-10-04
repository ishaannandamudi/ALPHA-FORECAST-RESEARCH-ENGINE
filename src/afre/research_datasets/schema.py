"""Dataset/split identity, explicit states and bounded offline research operations."""

from dataclasses import dataclass
from enum import Enum

from afre.schema import Artifact, contract, enum, require
from afre.version import DATASET_SCHEMA_VERSION as DATASET_SCHEMA_VERSION

BUILDER_VERSION = "afre-research-dataset-v1"
SPLITTER_VERSION = "afre-research-split-v1"
PREPROCESSING_VERSION = "afre-fold-preprocessing-v1"


@enum
class SampleState(Enum):
    AVAILABLE = "available"
    FEATURE_INCOMPLETE = "feature_incomplete"
    TARGET_NOT_AVAILABLE_YET = "target_not_available_yet"
    TARGET_MISSING = "target_missing"
    INELIGIBLE = "ineligible"
    UNIVERSE_UNKNOWN = "universe_unknown"
    CONFLICTED = "conflicted"
    INVALID = "invalid"


@enum
class DatasetMissingPolicy(Enum):
    FAIL = "fail"
    DROP_SAMPLE = "drop_sample"
    PRESERVE_MISSING = "preserve_missing"
    IMPUTE_TRAIN_ONLY = "impute_train_only"


@enum
class DatasetCompleteness(Enum):
    COMPLETE = "complete"
    KNOWN_GAPS = "known_gaps"
    UNKNOWN = "unknown"


@enum
class Partition(Enum):
    TRAIN = "train"
    VALIDATION = "validation"
    TEST = "test"
    PURGED = "purged"
    EMBARGOED = "embargoed"
    INELIGIBLE = "ineligible"


@enum
class SplitStrategy(Enum):
    WALK_FORWARD = "walk_forward"
    ROLLING_WINDOW = "rolling_window"
    EXPANDING_WINDOW = "expanding_window"
    FIXED_HOLDOUT = "fixed_holdout"


@enum
class PurgeRule(Enum):
    NONE = "none"
    TARGET_INTERVAL_OVERLAP = "target_interval_overlap"
    FULL_INFORMATION_INTERVAL_OVERLAP = "full_information_interval_overlap"


@enum
class PurgeScope(Enum):
    SECURITY = "security"
    ISSUER = "issuer"
    SECTOR = "sector"
    MARKET = "market"
    GLOBAL = "global"


@enum
class EmbargoBasis(Enum):
    ELAPSED_TIME = "elapsed_time"
    TRADING_SESSIONS = "trading_sessions"
    BARS = "bars"


@enum
class EmbargoDirection(Enum):
    AFTER = "after"
    BEFORE = "before"
    BOTH = "both"


@enum
class PreprocessingScope(Enum):
    TRAIN_PARTITION = "train_partition"
    WITHIN_ORIGIN = "within_origin_prepared"
    WITHIN_ORIGIN_GROUP = "within_origin_group_prepared"


@enum
class ZeroScaleRule(Enum):
    FAIL = "fail"
    UNIT_SCALE = "unit_scale"


@enum
class ColumnRole(Enum):
    FEATURE = "feature"
    TARGET = "target"
    IDENTIFIER = "identifier"
    METADATA = "metadata"


@contract("r_bounds")
@dataclass(frozen=True, slots=True)
class DatasetBounds(Artifact):
    origins: int = 10000
    securities: int = 5000
    samples: int = 100000
    features: int = 256
    targets: int = 128
    folds: int = 1000
    interval_comparisons: int = 10000000
    audit_nodes: int = 100000
    lineage_depth: int = 64
    serialized_bytes: int = 8 * 1024 * 1024

    def _validate(self) -> None:
        require(
            all(
                value > 0
                for value in (
                    self.origins,
                    self.securities,
                    self.samples,
                    self.features,
                    self.targets,
                    self.folds,
                    self.interval_comparisons,
                    self.audit_nodes,
                    self.lineage_depth,
                    self.serialized_bytes,
                )
            ),
            "positive dataset bounds required",
        )

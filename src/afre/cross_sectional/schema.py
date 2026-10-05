"""Closed research policies; rankings never imply portfolio allocations."""

from dataclasses import dataclass
from enum import Enum

from afre.schema import Artifact, contract, enum, require

IMPLEMENTATION_VERSION = "cross-sectional-v1"


@enum
class ScoreSource(Enum):
    POINT_EXPECTATION = "point_expectation"
    POINT_PREDICTION = "point_prediction"
    MEDIAN = "median"
    QUANTILE = "quantile"
    THRESHOLD_PROBABILITY = "threshold_probability"
    EXTERNAL_SIGNAL = "external_signal"


@enum
class RankDirection(Enum):
    HIGHER_BETTER = "higher_better"
    LOWER_BETTER = "lower_better"


@enum
class RankTiePolicy(Enum):
    AVERAGE_RANK = "average_rank"
    MIN_RANK = "min_rank"
    MAX_RANK = "max_rank"
    DENSE_RANK = "dense_rank"


@enum
class PeerTransform(Enum):
    NONE = "none"
    ZSCORE = "zscore"
    MEDIAN_MAD = "median_mad"
    PERCENTILE = "percentile"


@enum
class MissingScorePolicy(Enum):
    EXCLUDE_MISSING = "exclude_missing"
    FAIL_ON_MISSING = "fail_on_missing"
    RETAIN_UNRANKED = "retain_unranked"


@enum
class CrossSectionQuality(Enum):
    VALID = "valid"
    TOO_SMALL = "too_small"
    CONSTANT = "constant"
    EXCESSIVE_MISSINGNESS = "excessive_missingness"
    UNAVAILABLE = "unavailable"


@enum
class CrossSectionScoreState(Enum):
    AVAILABLE = "available"
    MISSING = "missing"
    FUTURE = "future"
    INVALID = "invalid"
    UNSUPPORTED = "unsupported"
    GROUP_UNAVAILABLE = "group_unavailable"


@enum
class GroupType(Enum):
    SECTOR = "sector"
    INDUSTRY = "industry"
    SUBINDUSTRY = "subindustry"
    CUSTOM = "custom"


@enum
class SmallGroupPolicy(Enum):
    FAIL = "fail"
    LEAVE_RAW = "leave_raw"
    MARK_UNAVAILABLE = "mark_unavailable"


@enum
class RankingLayer(Enum):
    RAW = "raw"
    NORMALIZED = "normalized"
    GROUP_NEUTRAL = "group_neutral"


@enum
class SignalQuality(Enum):
    VALID = "valid"
    STALE = "stale"
    MISSING = "missing"
    UNSUPPORTED = "unsupported"
    DEGRADED = "degraded"
    INVALID = "invalid"


@enum
class TruthPolicy(Enum):
    REQUIRE_COMPLETE = "require_complete"
    AVAILABLE_INTERSECTION = "available_intersection"


@enum
class StabilityMembership(Enum):
    SAME_MEMBERS = "same_members"
    INTERSECTION = "intersection"


@enum
class TargetCentering(Enum):
    NONE = "none"
    WITHIN_ORIGIN = "within_origin"


@contract("cs_bounds")
@dataclass(frozen=True, slots=True)
class CrossSectionBounds(Artifact):
    securities: int = 10_000
    groups: int = 1_000
    external_signals: int = 100_000
    features: int = 128
    truths: int = 100_000
    rankings: int = 100_000
    series: int = 10_000
    audit_nodes: int = 100_000
    audit_depth: int = 64
    serialized_bytes: int = 8 * 1024 * 1024

    def _validate(self) -> None:
        require(
            all(
                v > 0
                for v in (
                    self.securities,
                    self.groups,
                    self.external_signals,
                    self.features,
                    self.truths,
                    self.rankings,
                    self.series,
                    self.audit_nodes,
                    self.audit_depth,
                    self.serialized_bytes,
                )
            ),
            "positive cross-sectional bounds",
        )
        require(
            self.securities <= 100_000
            and self.audit_depth <= 64
            and self.serialized_bytes <= 16 * 1024 * 1024,
            "cross-sectional hard bounds",
        )

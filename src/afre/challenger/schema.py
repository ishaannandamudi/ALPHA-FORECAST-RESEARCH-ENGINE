"""Closed advisory comparison policies and hard resource limits."""

from dataclasses import dataclass
from enum import Enum

from afre.health.schema import ids
from afre.schema import Artifact, contract, enum, require


@enum
class ParticipantRole(Enum):
    CHAMPION = "CHAMPION"
    CHALLENGER = "CHALLENGER"


@enum
class ChallengeStatus(Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INCOMPARABLE = "INCOMPARABLE"


@enum
class ChallengeTestPolicy(Enum):
    VALIDATION_ONLY = "VALIDATION_ONLY"
    SEALED_TEST = "SEALED_TEST"


@enum
class ShadowMode(Enum):
    RECORDED_CAUSAL = "RECORDED_CAUSAL"
    RECONSTRUCTED_NATIVE = "RECONSTRUCTED_NATIVE"


@enum
class ChallengeMatching(Enum):
    COMMON_INTERSECTION = "COMMON_INTERSECTION"


@enum
class CriteriaPolicy(Enum):
    ALL_REQUIRED = "ALL_REQUIRED"
    ANY_REQUIRED = "ANY_REQUIRED"


@enum
class ChallengeDirection(Enum):
    HIGHER = "HIGHER"
    LOWER = "LOWER"


@enum
class PromotionOutcome(Enum):
    PROMOTION_ELIGIBLE = "PROMOTION_ELIGIBLE"
    PROMOTION_NOT_ELIGIBLE = "PROMOTION_NOT_ELIGIBLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INCOMPARABLE = "INCOMPARABLE"


@enum
class RollbackOutcome(Enum):
    ROLLBACK_ELIGIBLE = "ROLLBACK_ELIGIBLE"
    ROLLBACK_NOT_ELIGIBLE = "ROLLBACK_NOT_ELIGIBLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INCOMPARABLE = "INCOMPARABLE"


@enum
class ChallengeMetric(Enum):
    MAE = "MAE"
    MSE = "MSE"
    RMSE = "RMSE"
    R_SQUARED = "R_SQUARED"
    PEARSON = "PEARSON"
    SPEARMAN = "SPEARMAN"
    SIGN_ACCURACY = "SIGN_ACCURACY"
    CRPS = "CRPS"
    NLL = "NLL"
    BRIER = "BRIER"
    PINBALL = "PINBALL"
    COVERAGE = "COVERAGE"
    SHARPNESS = "SHARPNESS"
    IC = "IC"
    RANK_IC = "RANK_IC"
    RANK_DISPLACEMENT = "RANK_DISPLACEMENT"
    TOP_K_OVERLAP = "TOP_K_OVERLAP"
    GROSS_EDGE = "GROSS_EDGE"
    COST = "COST"
    NET_EDGE = "NET_EDGE"
    TURNOVER = "TURNOVER"
    BREAK_EVEN_COST = "BREAK_EVEN_COST"


COST_METRICS = frozenset(
    {
        ChallengeMetric.GROSS_EDGE,
        ChallengeMetric.COST,
        ChallengeMetric.NET_EDGE,
        ChallengeMetric.TURNOVER,
        ChallengeMetric.BREAK_EVEN_COST,
    }
)
HIGHER_BETTER = frozenset(
    {
        ChallengeMetric.R_SQUARED,
        ChallengeMetric.PEARSON,
        ChallengeMetric.SPEARMAN,
        ChallengeMetric.SIGN_ACCURACY,
        ChallengeMetric.IC,
        ChallengeMetric.RANK_IC,
        ChallengeMetric.TOP_K_OVERLAP,
        ChallengeMetric.GROSS_EDGE,
        ChallengeMetric.NET_EDGE,
        ChallengeMetric.BREAK_EVEN_COST,
    }
)
DESCRIPTIVE = frozenset(
    {
        ChallengeMetric.COVERAGE,
        ChallengeMetric.SHARPNESS,
        ChallengeMetric.TURNOVER,
        ChallengeMetric.BREAK_EVEN_COST,
    }
)
IMPLEMENTATION = "explicit-common-shadow-manual-only-v1"


@contract("ch_bounds")
@dataclass(frozen=True, slots=True)
class ChallengeBounds(Artifact):
    challengers: int = 16
    shadow_rows: int = 34000
    samples: int = 2000
    metrics: int = 32
    criteria: int = 32
    cohorts: int = 32
    comparisons: int = 512
    artifacts: int = 100000
    payload_bytes: int = 8 * 1024 * 1024
    snapshot_bytes: int = 128 * 1024 * 1024
    lineage_nodes: int = 100000
    lineage_depth: int = 64
    lineage_bytes: int = 16 * 1024 * 1024

    def _validate(self) -> None:
        for name, maximum in (
            ("challengers", 16),
            ("shadow_rows", 34000),
            ("samples", 2000),
            ("metrics", 32),
            ("criteria", 32),
            ("cohorts", 32),
            ("comparisons", 512),
            ("artifacts", 100000),
            ("payload_bytes", 8 * 1024 * 1024),
            ("snapshot_bytes", 128 * 1024 * 1024),
            ("lineage_nodes", 100000),
            ("lineage_depth", 64),
            ("lineage_bytes", 16 * 1024 * 1024),
        ):
            require(1 <= getattr(self, name) <= maximum, "challenge hard bound")


__all__ = ["ids"]

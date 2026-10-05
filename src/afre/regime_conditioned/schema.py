"""Closed provider-neutral policies; externally supplied memberships are data."""

from dataclasses import dataclass
from enum import Enum

from afre.schema import Artifact, contract, enum, require

REGIME_IMPLEMENTATION = "regime-conditioned-v1"


@enum
class RegimeCategory(Enum):
    MARKET_CONTEXT = "market_context"
    VOLATILITY = "volatility"
    LIQUIDITY = "liquidity"
    MICROSTRUCTURE = "microstructure"
    RISK = "risk"
    CUSTOM = "custom"


@enum
class RegimeScope(Enum):
    GLOBAL = "global"
    MARKET = "market"
    SECTOR = "sector"
    SECURITY = "security"
    VENUE = "venue"
    CUSTOM = "custom"


@enum
class RegimeMembershipKind(Enum):
    HARD = "hard"
    SOFT = "soft"


@enum
class RegimeStateSemantics(Enum):
    FILTERED = "filtered"
    SMOOTHED = "smoothed"
    EX_POST = "ex_post"


@enum
class RegimeQuality(Enum):
    VALID = "valid"
    STALE = "stale"
    MISSING = "missing"
    DEGRADED = "degraded"
    UNSUPPORTED = "unsupported"
    INVALID = "invalid"


@enum
class RegimeMatchPolicy(Enum):
    LATEST_AVAILABLE = "latest_available"
    EXACT_AS_OF = "exact_as_of"
    FAIL_ON_MULTIPLE = "fail_on_multiple"


@enum
class RegimeModelFamily(Enum):
    REGIME_TARGET_MEAN = "regime_target_mean"
    REGIME_RESIDUAL_OFFSET = "regime_residual_offset"
    SOFT_REGIME_WEIGHTED_OFFSET = "soft_regime_weighted_offset"


@enum
class RegimeFallback(Enum):
    FAIL = "fail"
    USE_BASE = "use_base"
    GLOBAL_OFFSET = "global_offset"


@enum
class RegimeCalibrationStatus(Enum):
    SUPPORTED = "supported"
    INSUFFICIENT_DATA = "insufficient_data"
    UNAVAILABLE = "unavailable"
    INCOMPATIBLE = "incompatible"


@contract("rc_bounds")
@dataclass(frozen=True, slots=True)
class RegimeBounds(Artifact):
    states: int = 128
    taxonomies: int = 1000
    snapshots: int = 100_000
    samples: int = 100_000
    transitions: int = 100_000
    evaluations: int = 1000
    drift_windows: int = 1000
    audit_nodes: int = 100_000
    audit_depth: int = 64
    serialized_bytes: int = 8 * 1024 * 1024

    def _validate(self) -> None:
        require(
            all(
                v > 0
                for v in (
                    self.states,
                    self.taxonomies,
                    self.snapshots,
                    self.samples,
                    self.transitions,
                    self.evaluations,
                    self.drift_windows,
                    self.audit_nodes,
                    self.audit_depth,
                    self.serialized_bytes,
                )
            ),
            "positive regime bounds",
        )
        require(
            self.states <= 4096
            and self.audit_depth <= 64
            and self.serialized_bytes <= 16 * 1024 * 1024
            and max(self.snapshots, self.samples, self.transitions, self.audit_nodes)
            <= 1_000_000,
            "regime hard bounds",
        )

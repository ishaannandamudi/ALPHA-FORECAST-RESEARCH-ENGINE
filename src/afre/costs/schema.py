"""Closed research-only costs, timing and non-executable mapping semantics."""

from dataclasses import dataclass, fields
from enum import Enum

from afre.schema import Artifact, contract, enum, require

COST_RESEARCH_SCHEMA_VERSION = "1.0"
COST_IMPLEMENTATION = "explicit-hypothetical-cost-research-v1"


@enum
class CostComponentType(Enum):
    SPREAD = "spread"
    EXPLICIT_FEE = "explicit_fee"
    SLIPPAGE = "slippage"
    MARKET_IMPACT = "market_impact"
    BORROW_COST = "borrow_cost"
    CUSTOM_COST = "custom_cost"


@enum
class CostUnit(Enum):
    BASIS_POINTS = "basis_points"
    RETURN_FRACTION = "return_fraction"
    PRICE = "price"
    CURRENCY_PER_UNIT = "currency_per_unit"
    CURRENCY_TOTAL = "currency_total"
    UNIT_QUANTITY = "unit_quantity"


@enum
class CostInputRole(Enum):
    MODEL_VALUE = "model_value"
    BID = "bid"
    ASK = "ask"
    REFERENCE_PRICE = "reference_price"
    REFERENCE_NOTIONAL = "reference_notional"
    AVAILABLE_VOLUME = "available_volume"


@enum
class CostQuality(Enum):
    VALID = "valid"
    MISSING = "missing"
    STALE = "stale"
    DEGRADED = "degraded"
    UNSUPPORTED = "unsupported"
    INVALID = "invalid"


@enum
class CostTiming(Enum):
    HISTORICAL_CAUSAL = "historical_causal"
    EX_POST_RESEARCH = "ex_post_research"


@enum
class CostMissingPolicy(Enum):
    FAIL = "fail"
    EXCLUDE_SAMPLE = "exclude_sample"
    DECLARED_FALLBACK = "declared_fallback"


@enum
class CostModel(Enum):
    FIXED_HALF_SPREAD = "fixed_half_spread"
    OBSERVED_BID_ASK_SPREAD = "observed_bid_ask_spread"
    FIXED_RATE = "fixed_rate"
    PROVIDER_ESTIMATE = "provider_estimate"
    LINEAR_PARTICIPATION = "linear_participation"
    SQRT_PARTICIPATION = "sqrt_participation"


@enum
class CostBasis(Enum):
    PER_SIDE_PER_TURNOVER = "per_side_per_turnover"
    ROUND_TRIP_PER_TURNOVER = "round_trip_per_turnover"
    PER_TRADE = "per_trade"


@enum
class SpreadMeaning(Enum):
    NOT_SPREAD = "not_spread"
    HALF_SPREAD = "half_spread"
    FULL_SPREAD = "full_spread"


@enum
class ResearchExposureMode(Enum):
    SIGN = "sign"
    THRESHOLD_SIGN = "threshold_sign"
    FIXED_UNIT_NOTIONAL = "fixed_unit_notional"
    DECLARED_SCALAR_EXPOSURE = "declared_scalar_exposure"


@enum
class InitialExposurePolicy(Enum):
    ZERO = "zero"
    DECLARED_INITIAL = "declared_initial"


@enum
class CostResultState(Enum):
    AVAILABLE = "available"
    EXCLUDED = "excluded"
    INSUFFICIENT_DATA = "insufficient_data"
    INCOMPARABLE = "incomparable"
    UNAVAILABLE = "unavailable"


@contract("cost_bounds")
@dataclass(frozen=True, slots=True)
class CostResearchBounds(Artifact):
    components: int = 12
    samples: int = 2000
    grid_points: int = 64
    participation_rates: int = 32
    environments: int = 32
    artifacts: int = 20_000
    serialized_bytes: int = 8_388_608
    audit_nodes: int = 100_000
    audit_depth: int = 64

    def _validate(self) -> None:
        maxima = (12, 2000, 64, 32, 32, 20_000, 8_388_608, 100_000, 64)
        require(
            all(
                1 <= getattr(self, f.name) <= m
                for f, m in zip(fields(self), maxima, strict=True)
            ),
            "cost research bounds",
        )


def ids(value: Artifact, *names: str) -> None:
    from afre.ids import validate_fingerprint

    for name in names:
        values = getattr(value, name)
        require(len(set(values)) == len(values), "duplicate cost reference")
        for identity in values:
            validate_fingerprint(identity)
        object.__setattr__(value, name, tuple(sorted(values)))

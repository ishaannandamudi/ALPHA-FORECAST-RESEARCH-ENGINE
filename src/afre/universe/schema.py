"""Closed security/universe vocabulary and bounded research operations."""

from dataclasses import dataclass
from enum import Enum

from afre.schema import Artifact, contract, enum, require
from afre.version import UNIVERSE_SCHEMA_VERSION as UNIVERSE_SCHEMA_VERSION

UNIVERSE_BUILDER_VERSION = "afre-universe-builder-v1"


@enum
class SecurityType(Enum):
    COMMON_STOCK = "common_stock"
    PREFERRED_STOCK = "preferred_stock"
    ADR = "adr"
    ETF = "etf"
    FUND = "fund"
    REIT = "reit"
    SPAC = "spac"
    WARRANT = "warrant"
    RIGHT = "right"
    UNIT = "unit"
    OTHER_EQUITY = "other_equity"


@enum
class UniverseSourceKind(Enum):
    EXPLICIT_CONSTITUENT_STREAM = "explicit_constituent_stream"
    RULE_BASED = "rule_based_candidates"
    SUPPLIED_MEMBERSHIP = "supplied_membership"
    INDEX_MEMBERSHIP = "index_membership"
    ETF_CONSTITUENT = "etf_constituent"
    EXCHANGE_LISTING_SET = "exchange_listing_set"
    CURRENT_CONSTITUENTS = "current_constituents_prohibited"


@enum
class MembershipState(Enum):
    INCLUDED = "included"
    EXCLUDED = "excluded"
    UNKNOWN = "unknown"
    CONFLICTED = "conflicted"


@enum
class EligibilityState(Enum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    NOT_APPLICABLE = "not_applicable"
    NOT_AVAILABLE_YET = "not_available_yet"
    UNKNOWN = "unknown"
    CONFLICTED = "conflicted"


@enum
class EligibilityReason(Enum):
    PASSED = "passed"
    NOT_MEMBER = "not_member"
    UNKNOWN_MEMBERSHIP = "unknown_membership"
    WRONG_SECURITY_TYPE = "wrong_security_type"
    WRONG_VENUE = "wrong_venue"
    WRONG_COUNTRY = "wrong_country"
    CURRENCY_MISMATCH = "currency_mismatch_no_fx"
    PRICE_TOO_LOW = "price_too_low"
    INSUFFICIENT_VOLUME = "insufficient_volume"
    INSUFFICIENT_LIQUIDITY = "insufficient_liquidity"
    INSUFFICIENT_HISTORY = "insufficient_history"
    INSUFFICIENT_LISTING_AGE = "insufficient_listing_age"
    STALE_MARKET_DATA = "stale_market_data"
    HALTED = "halted"
    SUSPENDED = "suspended"
    DELISTED = "delisted"
    MISSING_DATA = "missing_data"
    NOT_YET_LISTED = "not_yet_listed"
    MARKET_CLOSED = "market_closed"
    CONFLICT = "conflict"


@enum
class SnapshotCompleteness(Enum):
    COMPLETE = "complete"
    KNOWN_GAPS = "known_gaps"
    UNKNOWN = "unknown"


@enum
class TradabilityState(Enum):
    TRADABLE = "tradable"
    HALTED = "halted"
    SUSPENDED = "suspended"
    DELISTED = "delisted"
    UNKNOWN = "unknown"


@enum
class LifecycleKind(Enum):
    IPO = "ipo"
    DIRECT_LISTING = "direct_listing"
    SPINOFF = "spinoff"
    MERGER = "merger"
    ACQUISITION = "acquisition"
    BANKRUPTCY = "bankruptcy"
    DELISTING = "delisting"
    RELISTING = "relisting"
    SHARE_CLASS_CHANGE = "share_class_change"
    NAME_CHANGE = "name_change"
    TICKER_CHANGE = "ticker_change"
    VENUE_CHANGE = "venue_change"


@enum
class RelationshipKind(Enum):
    SECURITY_ISSUED_BY = "security_issued_by"
    PRIMARY_LISTING_OF = "primary_listing_of"
    ADR_OF = "adr_of"
    SUCCESSOR_TO = "successor_to"
    PREDECESSOR_OF = "predecessor_of"
    SPINOFF_FROM = "spinoff_from"


@enum
class ExternalIdentifierKind(Enum):
    CUSIP = "cusip"
    ISIN = "isin"
    FIGI = "figi"
    CIK = "cik"
    SEDOL = "sedol"
    PROVIDER = "provider"


@enum
class EligibilityMissingRule(Enum):
    UNKNOWN = "unknown"
    INELIGIBLE = "explicitly_ineligible"


@contract("u_bounds")
@dataclass(frozen=True, slots=True)
class UniverseBounds(Artifact):
    securities: int = 2000
    records: int = 100_000
    vintages: int = 5000
    snapshots: int = 1000
    lineage_nodes: int = 100_000
    lineage_depth: int = 64
    serialized_bytes: int = 8 * 1024 * 1024

    def _validate(self) -> None:
        require(
            all(
                value > 0
                for value in (
                    self.securities,
                    self.records,
                    self.vintages,
                    self.snapshots,
                    self.lineage_nodes,
                    self.lineage_depth,
                    self.serialized_bytes,
                )
            ),
            "positive universe bounds required",
        )

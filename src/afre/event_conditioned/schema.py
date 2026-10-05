"""Closed event research policies; no extraction, regimes or execution."""

from dataclasses import dataclass
from enum import Enum

from afre.schema import Artifact, contract, enum, require

EVENT_IMPLEMENTATION = "event-conditioned-v1"


@enum
class EventClass(Enum):
    EARNINGS = "earnings"
    GUIDANCE = "guidance"
    FILING = "filing"
    MERGER = "merger"
    MANAGEMENT = "management"
    MACRO = "macro"
    LEGAL_REGULATORY = "legal_regulatory"
    PRODUCT = "product"
    CAPITAL_ACTION = "capital_action"
    CREDIT = "credit"
    ANALYST_RESEARCH = "analyst_research"
    OTHER = "other"


@enum
class EventScope(Enum):
    SECURITY = "security"
    ISSUER = "issuer"
    SECTOR = "sector"
    MARKET = "market"
    MACRO = "macro"
    CUSTOM = "custom"


@enum
class EventRelation(Enum):
    PRE_EVENT = "pre_event"
    AT_EVENT = "at_event"
    POST_EVENT = "post_event"
    POST_EVENT_DELAYED = "post_event_delayed"


@enum
class EventAnchor(Enum):
    OCCURRENCE = "occurrence"
    PUBLICATION = "publication"
    FINAL_AVAILABILITY = "final_availability"


@enum
class EventOverlapPolicy(Enum):
    FAIL_ON_MULTIPLE = "fail_on_multiple"
    NEAREST_EVENT = "nearest_event"
    ALL_EVENTS_SEPARATE = "all_events_separate"


@enum
class EventModelFamily(Enum):
    EVENT_CLASS_OFFSET = "event_class_offset"
    MATERIALITY_LINEAR = "materiality_linear"
    SURPRISE_LINEAR = "surprise_linear"
    EVENT_FEATURE_LINEAR = "event_feature_linear"


@enum
class EventCalibrationStatus(Enum):
    SUPPORTED = "supported"
    INSUFFICIENT_DATA = "insufficient_data"
    UNAVAILABLE = "unavailable"


@contract("ec_bounds")
@dataclass(frozen=True, slots=True)
class EventBounds(Artifact):
    events: int = 100_000
    matches_per_sample: int = 128
    samples: int = 100_000
    reaction_features: int = 32
    groups: int = 1000
    audit_nodes: int = 100_000
    audit_depth: int = 64
    serialized_bytes: int = 8 * 1024 * 1024

    def _validate(self) -> None:
        require(
            all(
                v > 0
                for v in (
                    self.events,
                    self.matches_per_sample,
                    self.samples,
                    self.reaction_features,
                    self.groups,
                    self.audit_nodes,
                    self.audit_depth,
                    self.serialized_bytes,
                )
            ),
            "positive event bounds",
        )
        require(
            self.events <= 1_000_000
            and self.samples <= 1_000_000
            and self.audit_depth <= 64
            and self.serialized_bytes <= 16 * 1024 * 1024,
            "event hard bounds",
        )

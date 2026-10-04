"""Unambiguous horizon identities; no calendar resolver in AFRE-0."""

from dataclasses import dataclass
from enum import Enum

from afre.schema import Artifact, contract, enum, require


@enum
class HorizonBasis(Enum):
    ELAPSED_TIME = "elapsed_time"
    TRADING_SESSIONS = "trading_sessions"
    BARS = "bars"


@enum
class EndpointConvention(Enum):
    LAST_AT_OR_BEFORE = "last_at_or_before"


@contract("horizon")
@dataclass(frozen=True, slots=True)
class ForecastHorizon(Artifact):
    basis: HorizonBasis
    duration_ns: int | None = None
    count: int | None = None
    calendar_id: str | None = None
    bar_definition: str | None = None
    endpoint: EndpointConvention = EndpointConvention.LAST_AT_OR_BEFORE

    def _validate(self) -> None:
        if self.basis is HorizonBasis.ELAPSED_TIME:
            require(
                self.duration_ns is not None and self.duration_ns > 0,
                "elapsed horizon requires a positive duration",
            )
            require(
                self.count is None and self.calendar_id is None and self.bar_definition is None,
                "ambiguous elapsed horizon",
            )
        else:
            require(
                self.duration_ns is None and self.count is not None and self.count > 0,
                "session/bar horizon requires positive count",
            )
            require(self.calendar_id is not None, "calendar version required")
            require(
                (self.bar_definition is not None) == (self.basis is HorizonBasis.BARS),
                "bar definition required only for bars",
            )

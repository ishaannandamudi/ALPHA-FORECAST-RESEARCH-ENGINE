"""Freshness qualifies a retained value; it never changes its availability."""

from dataclasses import dataclass
from enum import Enum

from afre.schema import Artifact, contract, enum, require


@enum
class FreshnessBasis(Enum):
    NEVER = "never"
    EFFECTIVE_TIME = "effective_time"
    SOURCE_AVAILABILITY = "source_availability"


@contract("fs_freshness")
@dataclass(frozen=True, slots=True)
class FreshnessPolicy(Artifact):
    basis: FreshnessBasis = FreshnessBasis.NEVER
    max_age_ns: int | None = None

    def _validate(self) -> None:
        require(
            (self.max_age_ns is None) == (self.basis is FreshnessBasis.NEVER),
            "freshness basis/age mismatch",
        )

    def stale(self, origin_ns: int, effective_ns: int, source_available_ns: int) -> bool:
        if self.basis is FreshnessBasis.NEVER:
            return False
        clock = (
            effective_ns if self.basis is FreshnessBasis.EFFECTIVE_TIME else source_available_ns
        )
        return origin_ns - clock > (self.max_age_ns or 0)

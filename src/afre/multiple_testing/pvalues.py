"""Exact fair-sign binomial tails; ties are excluded under an explicit conditional null."""

import math
from dataclasses import dataclass

from afre.ids import validate_fingerprint
from afre.multiple_testing.schema import EvidenceState, HypothesisDirection, RawTestMethod
from afre.schema import Artifact, contract, require


@contract("mt_pvalue")
@dataclass(frozen=True, slots=True)
class PValueResult(Artifact):
    trial_id: str
    hypothesis_id: str
    method: RawTestMethod
    state: EvidenceState
    reason: str
    raw_p_value: float | None
    statistic: float | None
    sample_count: int
    informative_count: int
    zero_count: int
    available_ns: int

    def _validate(self) -> None:
        validate_fingerprint(self.trial_id, "mt_trial")
        validate_fingerprint(self.hypothesis_id, "mt_hypothesis")
        require(self.raw_p_value is None or 0 <= self.raw_p_value <= 1, "p-value outside [0,1]")
        require(
            0 <= self.informative_count <= self.sample_count <= 2000
            and self.zero_count == self.sample_count - self.informative_count,
            "p-value sample/tie counts",
        )
        require(
            (self.state is EvidenceState.AVAILABLE) == (self.raw_p_value is not None)
            and (self.statistic is not None) == (self.raw_p_value is not None),
            "p-value status/shape",
        )


def fair_sign_pvalue(positive: int, count: int, direction: HypothesisDirection) -> float:
    require(
        type(positive) is int
        and type(count) is int
        and 0 <= positive <= count <= 2000
        and count > 0
        and type(direction) is HypothesisDirection,
        "bounded fair sign counts/direction",
    )
    # Integer sums divided by 2**n avoid underflow of intermediate tail masses.
    if direction is HypothesisDirection.GREATER:
        numerator = sum(math.comb(count, k) for k in range(positive, count + 1))
    else:
        k = (
            min(positive, count - positive)
            if direction is HypothesisDirection.TWO_SIDED
            else positive
        )
        numerator = sum(math.comb(count, i) for i in range(k + 1))
        if direction is HypothesisDirection.TWO_SIDED:
            numerator *= 2
    return min(1.0, max(math.nextafter(0.0, 1.0), numerator / (1 << count)))

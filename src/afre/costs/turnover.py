"""Absolute exposure changes, with no inferred terminal liquidation or capital compounding."""

import math

from afre.costs.artifacts import ResearchExposureChange


def turnover(changes: tuple[ResearchExposureChange, ...]) -> float:
    return math.fsum(abs(c.trade_delta) for c in sorted(changes, key=lambda c: c.fingerprint))

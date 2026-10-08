"""Declared crossing assumptions; full bid/ask spread is explicitly halved once."""

from afre.costs.schema import SpreadMeaning
from afre.schema import require


def observed_full_spread(bid: float, ask: float) -> float:
    require(0 < bid <= ask, "invalid observed bid/ask spread")
    return ask - bid


def spread_multiplier(meaning: SpreadMeaning) -> float:
    return 0.5 if meaning is SpreadMeaning.FULL_SPREAD else 1.0

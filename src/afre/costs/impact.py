"""Simple explicit research impact coefficients, with no sizing or execution optimization."""

import math

from afre.costs.schema import CostModel
from afre.schema import require


def impact_multiplier(model: CostModel, participation: float | None) -> float:
    if model not in (CostModel.LINEAR_PARTICIPATION, CostModel.SQRT_PARTICIPATION):
        return 1.0
    require(
        participation is not None and 0 <= participation <= 1,
        "explicit bounded impact participation",
    )
    assert participation is not None
    return (
        participation if model is CostModel.LINEAR_PARTICIPATION else math.sqrt(participation)
    )

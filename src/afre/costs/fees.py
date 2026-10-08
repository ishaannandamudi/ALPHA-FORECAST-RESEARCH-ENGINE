"""Currency and return-rate conversions against explicitly supplied reference notional."""

from afre.costs.schema import CostBasis, CostUnit
from afre.schema import require


def conversion_factor(
    unit: CostUnit, basis: CostBasis, delta: float, price: float, notional: float
) -> float:
    require(price > 0 and notional > 0, "positive supplied price/reference notional")
    absolute = abs(delta)
    if basis is CostBasis.PER_TRADE:
        require(unit is CostUnit.CURRENCY_TOTAL, "flat trade cost units")
        return 1.0 / notional if absolute > 0 else 0.0
    scales = {
        CostUnit.BASIS_POINTS: 1e-4,
        CostUnit.RETURN_FRACTION: 1.0,
        CostUnit.PRICE: 1.0 / price,
        CostUnit.CURRENCY_PER_UNIT: 1.0 / price,
        CostUnit.CURRENCY_TOTAL: 1.0 / notional,
    }
    require(unit in scales, "unsupported cost conversion unit")
    return (
        absolute * scales[unit] * (0.5 if basis is CostBasis.ROUND_TRIP_PER_TURNOVER else 1.0)
    )

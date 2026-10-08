# Algebraic break-even diagnostics

The total available budget is included arithmetic gross contribution. A common per-side
bps threshold is gross_sum / (included turnover /10000), when support is sufficient, gross
is nonnegative and turnover is positive. Zero gross yields a zero threshold with positive
turnover. Negative gross or zero turnover yields UNAVAILABLE, not a negative or infinite rate.

For one selected component, keep all other included component costs fixed. The budget is
gross_sum − other_cost_sum; divide by the sum of the selected rate's explicit unit-conversion
factor and its model multiplier. This supports spread, slippage, fee and linear/sqrt impact
coefficient thresholds in the selected input rate unit. Observed spread returns a full PRICE
spread threshold because the conversion already contains the half-spread multiplier; fixed
half-spread returns a half-spread threshold. Participation is held fixed for an impact
coefficient threshold. The exact scenario/component/target/evaluation references are pinned.

The algebra solves net_sum = 0 without grid interpolation or extrapolation. Unsupported,
insufficient, negative-budget and zero-denominator cases remain explicit. Thresholds are
research diagnostics, not recommended execution prices, fills, capacity or model choices.
See [cost units](spread-fee-slippage.md) and [sensitivity](cost-sensitivity.md).

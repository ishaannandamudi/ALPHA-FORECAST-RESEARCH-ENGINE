# Spread, fee and slippage semantics

Every component declares category, source/provider/version/schema/venue, applicability,
model, rate unit, side basis, included categories, fixed rate or explicit rate refs, fallback
and declaration time. Rates and costs are nonnegative magnitudes. Maker/taker-specific
behavior or rebates are not inferred. Generic explicit fees are supported.

For absolute exposure change d, reference price P and notional N, hypothetical quantity
is dN/P. All output costs are compatible RETURN_FRACTION contributions:

| Input rate unit | Per-side cost before model multipliers |
| --- | --- |
| BASIS_POINTS | d × rate / 10000 |
| RETURN_FRACTION | d × rate |
| PRICE or CURRENCY_PER_UNIT | d × rate / P |
| CURRENCY_TOTAL, per turnover | d × rate / N |
| CURRENCY_TOTAL, PER_TRADE | rate / N for d > 0; zero for d = 0 |

ROUND_TRIP_PER_TURNOVER explicitly divides the supplied round-trip rate by two, so a buy
and sell each charge one side. Per-trade flat fees do not scale with d. Spread requires a
per-side basis; no extra automatic round-trip halving is applied. FIXED_HALF_SPREAD pins
half-spread meaning directly. OBSERVED_BID_ASK_SPREAD requires exact bid/ask PRICE refs,
positive bid ≤ ask, explicit full-spread meaning and one crossing multiplier of 1/2.
A full 0.04 spread at price 100 and d = 1 contributes 0.0002 exactly up to float rounding.

FIXED_RATE slippage pins explicit bps or compatible units; PROVIDER_ESTIMATE uses a
neutral supplied rate. Linear/sqrt participation slippage is also explicit and bounded.
Fixed slippage is not a fill model. Provider MODEL_VALUE inputs must explicitly declare
included categories exactly matching the component spec; scenario category sets must be
disjoint. A provider estimate including spread cannot be charged together with a separate
spread component. Liquidity/quote refs carry no hidden embedded-cost metadata.

No currency mixing, silent defaults, signed rebates or copied external TCA algorithms occur.
See [scenarios](cost-scenarios.md) and [impact](market-impact-research.md).

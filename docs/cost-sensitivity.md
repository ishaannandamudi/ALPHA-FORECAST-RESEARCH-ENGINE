# Supplied cost sensitivity

`CostSensitivitySpec` pins an exact scenario/component, nonnegative supplied rate grid,
optional bounded participation grid, positive cost-intensity multipliers ≤ 10, declaration
clock and closed convention. The Cartesian grid is bounded to 64 points, participation to 32
levels. Duplicates and unknown conventions reject; values are canonicalized. Grids must be
declared by the same frozen TRAIN cutoff as scenario settings. No grid search or winner
selection is performed.

For each supplied rate, replace the selected component rate while retaining other costs and
exact included samples. Optional p replaces the selected participation-model parameter.
Intensity multipliers scale absolute transition quantities and associated impact p; flat
PER_TRADE fees stay flat, and over-limit p becomes an explicit unavailable point. Gross is
held fixed; these are conditional cost-intensity diagnostics, not internally consistent new
exposure paths or size optimizations. Result fields retain rate/p/multiplier, cost sum, net
sum/mean, state and reason. Exact algebra supplies break-even; no interpolation is advertised.

Descriptive comparisons require identical cost/exposure policy, units, sample/truth IDs,
cutoff, inclusion set and compatible state. They report right−left gross/net/turnover deltas;
policy/horizon mismatch yields INCOMPARABLE. Forecast rankings and raw IC remain unchanged.
No comparison selects a survivor or uses TEST to tune a rule, fallback or coefficient.

The [measured profile](costs-profile.json) reports a bounded native workload separately from
a larger arithmetic-only loop. No production SLA, capacity or profitability claim follows.
See [research boundaries](transaction-cost-aware-research.md).

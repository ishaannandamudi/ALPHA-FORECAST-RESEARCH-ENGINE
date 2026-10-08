# Market-impact research

LINEAR_PARTICIPATION uses coefficient_bps × p; SQRT_PARTICIPATION uses coefficient_bps × sqrt(p).
The contribution multiplies that rate by abs(trade delta)/10000. Coefficients are explicit
neutral provider refs with exact horizon, source/version/quality/six clocks. PROVIDER_ESTIMATE
may supply a separate explicit magnitude without recreating an external impact algorithm.

`p = hypothetical quantity / declared available volume`, with quantity = abs(delta)N/P.
Volume is UNIT_QUANTITY, positive, security/currency/horizon-specific and historically available
for causal cost evaluation. p must lie in [0, declared maximum] with maximum ≤ 1; excess
participation rejects instead of clipping. No volume, ADV, depth or volatility is inferred.
A coefficient of 20 bps with p = 0.01 produces 0.2 bps of impact under the linear convention.

Supplied participation grids describe model-dependent sensitivity. They hold gross fixed and
replace the selected component participation parameter; they are not inferred achievable
fills, executable quantities, capacity estimates or optimization. No venue, schedule, order
size or brokerage action is selected. Uncertainty metadata does not automatically set the
impact coefficient. See [sensitivity](cost-sensitivity.md).

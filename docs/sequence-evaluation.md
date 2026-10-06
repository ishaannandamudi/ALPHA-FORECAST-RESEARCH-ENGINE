# Sequence research evaluation

Sequence forecasts pin model/spec, exact sample/security/origin, target/horizon, snapshot, contributions, optional law and actual computation/availability. Application inputs and outputs must be available at the exact cutoff. Later evaluation resolves only the target vintage pinned by the sample, completed and available by the evaluation cutoff.

Matched comparison requires a complete exact sample grid and same origin/security/target/horizon for point, nonlinear, mixture or sequence baselines. All compared predictions use the same truth IDs. Metrics include point errors, directional accuracy, correlations and proper scores when a compatible law exists. Deltas are sequence metric minus baseline metric, not a selection criterion. Cohorts preserve source event classes and active filtered regimes without claiming causal effects.

Optional AFRE-6 location translation shifts a compatible existing law to the sequence point forecast; scale/residual samples are retained and quantiles/threshold probabilities recomputed. Unsupported expectation laws fail. This does not identify aleatoric, epistemic or other uncertainty components. Upstream AFRE-7 calibrators are incompatible; dedicated sequence calibration fitting is unavailable, with explicit `insufficient`, `unavailable` or `incompatible` assessment states. Calibration observations must be independent non-TRAIN/non-TEST VALIDATION forecasts of the exact model with known truth.

An explicit derived neutral sequence score feeds unchanged AFRE-9 same-origin ranking/IC. It is not a portfolio weight. Each horizon has an independent spec, transform, dataset, model and forecast; actual 1h/1d fixtures prove distinct target identities. There is no cross-horizon covariance model.

Coverage reports eligible unique origins, completeness states and exclusions. Stability reports compatible raw-scale readout coefficient ranges without auto-refit. Contributions/state trajectories are arithmetic/model internals, not causal importance. TEST evaluation records exact sealed samples and repeat-use evidence. Bounded unified lineage checks earlier completed fits plus sequence sources, masks, clocks, TRAIN fitting, laws, truths and diagnostics.

Predictive metrics do not establish profitability. Transaction-cost-aware evaluation remains AFRE-18; multiple testing AFRE-19; model selection AFRE-20; portfolio construction, risk optimization and execution remain downstream projects after AFRE.

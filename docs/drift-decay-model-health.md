# Drift, decay and model health

AFRE-22 measures a frozen producer across explicit reference/current windows. Engine 0.23.0 adds health schema 1.0 and store 1.22 / SQLite user_version=23. Earlier public schemas remain 1.0 and runtime dependencies remain empty.

Drift != failure. Input drift != error degradation. Input distributions, predictions, truth-dependent performance, calibration and parameter comparisons have distinct diagnostic kinds and immutable evidence. Positive changes in loss (MAE/MSE/RMSE/CRPS/NLL) mean worse; positive changes in R²/IC/rank IC mean better. Other changes have no intrinsic severity: the supplied rule sets the direction.

`MonitoredArtifactReference` pins native artifact and producer, model/signal identity, exact target/horizon, units, semantics, fold/dataset when available, source version and availability. Native references cover AFRE-5/6/7/9/10/11/12/13/14/15/16/17/18/20/21. Unsupported diagnostic/source combinations remain explicit. No adapter invents a law or target-unit bridge.

`HealthEngine` publishes references, observations, declarations, metrics, snapshots, fixed-reference trends and audits. It has no retrain, recalibrate, replace, promote, retire, route, trade or notification operation. Snapshot action is always `NONE_DESCRIPTIVE_ONLY`. No health probability, causal explanation, trading profitability or production SLA follows from these artifacts.

[Windows](health-windows.md), [rules](health-rules.md), [snapshots](health-snapshots.md) and [completion evidence](AFRE_22_COMPLETION_REPORT.md) describe the exact boundary. AFRE-23 owns Champion/Challenger & Shadow Evaluation; AFRE-24 owns the final forecast service boundary; AFRE-25 owns final integration/hardening. Portfolio construction, risk optimization and execution remain downstream.

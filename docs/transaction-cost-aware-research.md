# Transaction-cost-aware research

AFRE-18 is complete. Engine 0.19.0, transaction-cost-research schema 1.0, shared
store 1.18/SQLite 19; earlier schemas and implementations are preserved. Runtime is
stdlib-only. The roadmap freezes 26 distinct phases, AFRE-0 through AFRE-25.

The question is whether a supplied forecast or residual signal has positive hypothetical
arithmetic net contribution under a declared exposure rule and cost scenario. Cost artifacts
are separate from the original forecast, ranking, uncertainty and stability artifacts.

For each exact held-out sample, `gross = exposure × simple target return` and
`net = gross − total cost`. The target definition, horizon, origin, security, frozen producer,
fold, exact sample truth ID, rule, components, input vintages and clocks are fingerprinted.
Prediction/exposure/cost estimation runs under the inherited target-free read guard; truth
enters only later evaluation. The complete supplied per-security path is built before
exclusions or cohort slicing. No compounded capital/equity series is inferred.

Aggregates report matched included counts/exclusions, arithmetic sums and means, full-path
and included turnover, cost per turnover, positive gross/net fractions, cost-to-absolute-gross
ratio and positive-edge survival. All-truth gross is a separate field for cost-excluded rows.
Undefined ratios are null; insufficient support remains an explicit typed state. Positive-edge
survival is the fraction of included rows with gross > 0 whose net > 0, with null when
there is no positive-gross denominator. No invented net IC replaces raw forecast IC.

Point, probabilistic, calibrated, event, regime, mixture, nonlinear and sequence forecasts
are native sources. AFRE-16 available residuals retain their own threshold units. Optional
AFRE-15 decompositions must match exact forecast/sample/fold/target/horizon, one per sample,
and be actually available at evaluation; variance never creates an automatic cost. Native
AFRE-17 memberships supply event, hard/soft regime, sector, industry, historical universe,
time, quality and neutral/compound cohorts. Weights, minimum count and effective support
remain explicit. Actual 1h/1d targets are assessed separately without pooling.

Inputs/settings are caller-attested records. The contracts cannot authenticate provider
clocks, prove human predeclaration, or discover a disguised target-derived external scalar.
Provider review is still necessary. Settings and grids must be declared no later than the
frozen fold TRAIN cutoff; TEST receives a frozen scenario and a sealed assessment identity.
There is no API for model search, threshold optimization or choosing a winner.

Results do not establish executable fills, live PnL, capacity, profitability, causal proof,
significance, portfolio CAGR/Sharpe/drawdown, or a production SLA. Borrow carrying costs,
rank-bucket exposure, FX conversion, non-simple-return gross contributions, terminal
liquidation, per-origin notional optimization and inferred liquidity fallbacks are unsupported.
Orders, routing, sizing optimization and risk/portfolio construction are downstream projects.
No AME/MCE/EIE/options/TCA implementation is imported.

Persistence adds three immutable tables and indexed exact links/metadata transactionally
18→19. Safe canonical structured JSON verifies family/schema/hash, relational projections,
links and semantic replay against exact references. Computation occurs on pinned snapshots;
writer publication replays identical IDs atomically. New evidence produces new IDs while
old bytes remain fixed. Bounds cover 12 components, 2000 samples, 64 grid points, 32
participation levels/cohort requests, 20000 artifacts per family, 8 MiB payload/lineage,
100000 audit nodes and depth 64; callers may lower these limits.

See [scenarios](cost-scenarios.md), [exposure](research-exposure-rules.md),
[cost units](spread-fee-slippage.md), [impact](market-impact-research.md),
[turnover](turnover-diagnostics.md), [break-even](break-even-cost.md),
[sensitivity](cost-sensitivity.md), [profile](costs-profile.json) and
[the completion report](AFRE_18_COMPLETION_REPORT.md).

AFRE-19 is complete. Each inspected cost scenario is a separate declared research
opportunity; [multiple-testing controls](multiple-testing-controls.md) preserve its
native units, hypothetical contribution semantics and immutable evaluation evidence.
No Sharpe ratio or trading profitability is inferred from these arithmetic streams.

**Final scope: AFRE-25 — Final Integration, Hardening & Research Audit.** This completes the frozen 26-phase research architecture. Release decision and exact gate evidence are in [the final report](AFRE_25_COMPLETION_REPORT.md). Portfolio construction, risk optimization and execution remain downstream. Predictive metrics do not establish trading profitability.
AFRE-23 explicit champions/challengers, matched shadow evaluation and manual promotion/rollback advice are complete. AFRE-24 immutable snapshots, registry metadata and the read-only service boundary are complete; AFRE-25 completes the final integration and hardening audit.
AFRE-22 provides descriptive health; automatic lifecycle actions remain excluded. **Stop after AFRE-25.** Portfolio construction,
risk optimization and execution remain downstream projects after AFRE.

AFRE-19 integration: [declared controls](multiple-testing-controls.md) register exact native
source/truth, target/horizon, environment and cost-scenario opportunities without mutating
prior artifacts. [Registry snapshots](research-trial-registry.md) retain failed attempts,
TEST reuse and caller-recorded selection sets. Corrections do not establish independence,
causality or profitability, and no automatic model selection or pruning occurs.

## AFRE-21 integration

AFRE-18 accepts frozen AFRE-21 target-unit FusedForecast returns under separately declared hypothetical exposure and cost scenarios. The adapter preserves exact artifact/sample/origin/target/horizon and causal availability. Cost evaluation cannot select sources or refit weights. It remains research evaluation; portfolio construction, risk optimization and execution are downstream, and predictive metrics do not establish profitability. See [fusion evaluation](fusion-evaluation.md).

AFRE-22 [drift, decay and model health](drift-decay-model-health.md) uses frozen artifacts and predeclared windows/rules. Drift != failure; input drift != error degradation. Truth-dependent metrics retain native TEST seals and research history; health warnings do not erase overfitting concerns. No hidden thresholds, automatic retraining/recalibration, model replacement, weight changes, causal explanation or profitability claim. AFRE-17 environment research remains distinct from ongoing AFRE-22 monitoring. AFRE-20 model selection remains distinct from AFRE-21 ensemble construction; monitoring does not rerun selection. AFRE-18 hypothetical costs remain separate from downstream portfolio construction/risk/execution. AFRE-23 owns Champion/Challenger & Shadow Evaluation.

AFRE-23 [champion/challenger research](champion-challenger.md) is complete. Explicit participants and frozen criteria use exact common shadow evidence with immutable AFRE-18/19/20/21/22 context. Every assessment is MANUAL_ONLY; eligibility does not deploy, roll back, retrain, recalibrate or change fusion weights. TEST cannot redefine a program, and predictive metrics do not establish trading profitability. **Stop after AFRE-25. Final scope: AFRE-25 — Final Integration, Hardening & Research Audit.** AFRE-25 completes final integration and hardening.

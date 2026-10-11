# Invariance and stability research

AFRE-17 is complete. Engine 0.18.0 adds schema 1.0 and the additive store 1.17/SQLite user_version=18. All earlier contracts and schemas remain unchanged. The roadmap freezes 26 distinct phases, AFRE-0 through AFRE-25.

Observational stability across tested environments does not prove structural causal invariance. Every result is descriptive. There is no universal stability score, significance claim or claim of trading profitability. Distribution shift does not establish the cause of forecast degradation. Formal multiple-testing controls belong to AFRE-19.

The dedicated `afre.invariance` package separates declarations, PIT memberships, native forecast adapters, later evaluation, score arithmetic, comparisons, parameter diagnostics, feature distributions, ranks, uncertainty, storage, validation, lineage and orchestration. Analysis reads supplied frozen models; it cannot refit, recalibrate, prune, select or promote them. Portfolio construction, risk optimization and execution remain downstream projects after AFRE.

Start with [environment definitions](environment-definitions.md), [evaluation](stability-evaluation.md), [feature shift](feature-distribution-shift.md) and [degradation](forecast-degradation.md). Run `.venv311/bin/python -m examples.invariance_demo` for the 37-step offline walkthrough. The [75-entry A–BW report](AFRE_17_COMPLETION_REPORT.md) records all54 gates; the [profile](invariance-profile.json) separates the native workflow from the larger arithmetic workload.

No direct AME/MCE/EIE/options dependency is introduced. Providers supply neutral immutable evidence through existing AFRE availability contracts. There are zero runtime dependencies.

**Next scope: AFRE-24 — Forecast Snapshot, Registry & Service.**
AFRE-23 explicit champions/challengers, matched shadow evaluation and manual promotion/rollback advice are complete. AFRE-24 snapshot/registry/service remains future scope.
AFRE-22 provides descriptive health; automatic lifecycle actions remain excluded. **Stop after AFRE-23.** Portfolio construction,
risk optimization and execution remain downstream projects after AFRE.
AFRE-18 [explicit hypothetical cost research](transaction-cost-aware-research.md) now
evaluates frozen native forecasts/residual signals using separate exposure, cost and later
truth artifacts. Gross and net remain separate; PIT cohorts retain full-path trade deltas.
Uncertainty does not automatically become cost and ranking/stability definitions are unchanged.
Historical-causal versus ex-post evidence is explicit, and supplied grids cannot select TEST
settings. No execution, model selection, direct external-engine dependency or profitability
proof is added. AFRE-19 Multiple Testing & Research Overfitting Controls is complete; see [the control layer](multiple-testing-controls.md).

AFRE-19 integration: [declared controls](multiple-testing-controls.md) register exact native
source/truth, target/horizon, environment and cost-scenario opportunities without mutating
prior artifacts. [Registry snapshots](research-trial-registry.md) retain failed attempts,
TEST reuse and caller-recorded selection sets. Corrections do not establish independence,
causality or profitability, and no automatic model selection or pruning occurs.

## AFRE-21 integration

AFRE-21 can attach an exact target/horizon/sample/output EnvironmentMetric as separate post-hoc metadata. This cannot change fusion weights. Descriptive comparisons of supplied frozen fusion fits implement no AFRE-22 model-health automation. See [fusion evaluation](fusion-evaluation.md).

AFRE-22 [drift, decay and model health](drift-decay-model-health.md) uses frozen artifacts and predeclared windows/rules. Drift != failure; input drift != error degradation. Truth-dependent metrics retain native TEST seals and research history; health warnings do not erase overfitting concerns. No hidden thresholds, automatic retraining/recalibration, model replacement, weight changes, causal explanation or profitability claim. AFRE-17 environment research remains distinct from ongoing AFRE-22 monitoring. AFRE-20 model selection remains distinct from AFRE-21 ensemble construction; monitoring does not rerun selection. AFRE-18 hypothetical costs remain separate from downstream portfolio construction/risk/execution. AFRE-23 owns Champion/Challenger & Shadow Evaluation.

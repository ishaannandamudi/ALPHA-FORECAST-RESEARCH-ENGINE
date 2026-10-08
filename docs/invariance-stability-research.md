# Invariance and stability research

AFRE-17 is complete. Engine 0.18.0 adds schema 1.0 and the additive store 1.17/SQLite user_version=18. All earlier contracts and schemas remain unchanged. The roadmap freezes 26 distinct phases, AFRE-0 through AFRE-25.

Observational stability across tested environments does not prove structural causal invariance. Every result is descriptive. There is no universal stability score, significance claim or claim of trading profitability. Distribution shift does not establish the cause of forecast degradation. Formal multiple-testing controls belong to AFRE-19.

The dedicated `afre.invariance` package separates declarations, PIT memberships, native forecast adapters, later evaluation, score arithmetic, comparisons, parameter diagnostics, feature distributions, ranks, uncertainty, storage, validation, lineage and orchestration. Analysis reads supplied frozen models; it cannot refit, recalibrate, prune, select or promote them. Portfolio construction, risk optimization and execution remain downstream projects after AFRE.

Start with [environment definitions](environment-definitions.md), [evaluation](stability-evaluation.md), [feature shift](feature-distribution-shift.md) and [degradation](forecast-degradation.md). Run `.venv311/bin/python -m examples.invariance_demo` for the 37-step offline walkthrough. The [75-entry A–BW report](AFRE_17_COMPLETION_REPORT.md) records all54 gates; the [profile](invariance-profile.json) separates the native workflow from the larger arithmetic workload.

No direct AME/MCE/EIE/options dependency is introduced. Providers supply neutral immutable evidence through existing AFRE availability contracts. There are zero runtime dependencies.

**Next scope: AFRE-19 — Multiple Testing & Research Overfitting Controls.**
Multiple-hypothesis corrections, false discovery and family-wise error controls, repeated
research-trial accounting, selection-bias diagnostics, appropriate deflated statistics and
a research-trial registry with an explicit no-causal-proof boundary. Broad model selection
remains AFRE-20. **Stop after AFRE-18.** AFRE-19 is unimplemented. Portfolio construction,
risk optimization and execution remain downstream projects after AFRE.
AFRE-18 [explicit hypothetical cost research](transaction-cost-aware-research.md) now
evaluates frozen native forecasts/residual signals using separate exposure, cost and later
truth artifacts. Gross and net remain separate; PIT cohorts retain full-path trade deltas.
Uncertainty does not automatically become cost and ranking/stability definitions are unchanged.
Historical-causal versus ex-post evidence is explicit, and supplied grids cannot select TEST
settings. No execution, model selection, direct external-engine dependency or profitability
proof is added. AFRE-19 Multiple Testing & Research Overfitting Controls remains deferred.

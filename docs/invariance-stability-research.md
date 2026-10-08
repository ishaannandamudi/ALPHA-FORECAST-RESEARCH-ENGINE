# Invariance and stability research

AFRE-17 is complete. Engine 0.18.0 adds schema 1.0 and the additive store 1.17/SQLite user_version=18. All earlier contracts and schemas remain unchanged. The roadmap freezes 26 distinct phases, AFRE-0 through AFRE-25.

Observational stability across tested environments does not prove structural causal invariance. Every result is descriptive. There is no universal stability score, significance claim or claim of trading profitability. Distribution shift does not establish the cause of forecast degradation. Formal multiple-testing controls belong to AFRE-19.

The dedicated `afre.invariance` package separates declarations, PIT memberships, native forecast adapters, later evaluation, score arithmetic, comparisons, parameter diagnostics, feature distributions, ranks, uncertainty, storage, validation, lineage and orchestration. Analysis reads supplied frozen models; it cannot refit, recalibrate, prune, select or promote them. Portfolio construction, risk optimization and execution remain downstream projects after AFRE.

Start with [environment definitions](environment-definitions.md), [evaluation](stability-evaluation.md), [feature shift](feature-distribution-shift.md) and [degradation](forecast-degradation.md). Run `.venv311/bin/python -m examples.invariance_demo` for the 37-step offline walkthrough. The [75-entry A–BW report](AFRE_17_COMPLETION_REPORT.md) records all54 gates; the [profile](invariance-profile.json) separates the native workflow from the larger arithmetic workload.

No direct AME/MCE/EIE/options dependency is introduced. Providers supply neutral immutable evidence through existing AFRE availability contracts. There are zero runtime dependencies.

**Next scope: AFRE-18 — Transaction-Cost-Aware Research Evaluation.** **Stop after AFRE-17.**

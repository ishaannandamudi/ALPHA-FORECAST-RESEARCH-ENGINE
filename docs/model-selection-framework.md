# Hyperparameter & Model Selection Framework

AFRE-20 is a bounded orchestration layer around native AFRE fitting APIs. Engine
0.21.0, selection schema 1.0, store 1.20/SQLite21, Python 3.11+ and zero runtime
dependencies. Earlier public schemas remain unchanged.

TRAIN fits. VALIDATION selects. TEST evaluates only later through explicit native
evaluation/seal and AFRE-19 reuse accounting; SelectionEngine has no TEST evaluation
or final-refit operation. The winner references the immutable TRAIN-fitted model.
Selection on VALIDATION does not prove generalization or trading profitability.

Declare a [SearchSpace](search-spaces.md), exact fold/target/horizon/sample grid,
native recipes, criterion, tie rule, minimum support and [budget](resource-budgets.md).
SelectionEngine freezes the repository into a bounded isolated SQLite view, admits
the entire Cartesian grid before fitting, then performs separate guarded planning,
TRAIN fitting and VALIDATION scoring stages. Atomic publication preserves every
candidate outcome in a [registry snapshot](candidate-registry.md).

All inspected candidates count under AFRE-19, including failures, incompatible laws
and insufficient support. CandidateFamilyPlan freezes the complete roster before
fits; native trial plans freeze the full opportunity pool before truth scoring.
There is no hidden adaptive search, TEST tuning, automatic pruning, model promotion,
production deployment, automatic TRAIN+VALIDATION refit or ensemble fusion.

Supported criteria are MIN_MSE, MIN_MAE, MAX_R2, MIN_CRPS and MIN_NLL. See
[validation](validation-selection.md) for exact compatibility and support. Native
families 5, 6, 10, 11, 13 and 14 are integrated; AFRE-12 and automatic calibration
selection are deferred. Independent calls can select each walk-forward fold, with
no shared future-fold choices. Nested selection, coupled horizons, continuous,
random/Bayesian and partial search remain unsupported.

Run `PYTHONPATH=src:. .venv311/bin/python -m examples.selection_demo` for 35 verified
offline steps. See [profile](selection-profile.json), [reproducibility](selection-reproducibility.md)
and [A–CB completion report](AFRE_20_COMPLETION_REPORT.md).

**Next scope: AFRE-25 — Final Integration, Hardening & Research Audit.** Future scope covers
immutable public forecast snapshots, provider-neutral retrieval, model/artifact
registry and exact schema/version exposure. AFRE-23 champion/challenger evaluation is complete. AFRE-22 provides descriptive health; automatic lifecycle actions remain excluded.
**Stop after AFRE-24.** Portfolio construction, risk optimization and execution
remain downstream projects after AFRE.

## AFRE-21 integration

AFRE-20 owns selection among fusion candidates. AFRE-21 does not add another selector. The optional fusion-candidate adapter is unsupported; no post-VALIDATION TEST winner is inferred. An explicit upstream SelectionResult can record an already-selected contributor, but it never selects fusion weights. See [fusion evaluation](fusion-evaluation.md).

AFRE-22 [drift, decay and model health](drift-decay-model-health.md) uses frozen artifacts and predeclared windows/rules. Drift != failure; input drift != error degradation. Truth-dependent metrics retain native TEST seals and research history; health warnings do not erase overfitting concerns. No hidden thresholds, automatic retraining/recalibration, model replacement, weight changes, causal explanation or profitability claim. AFRE-17 environment research remains distinct from ongoing AFRE-22 monitoring. AFRE-20 model selection remains distinct from AFRE-21 ensemble construction; monitoring does not rerun selection. AFRE-18 hypothetical costs remain separate from downstream portfolio construction/risk/execution. AFRE-23 owns Champion/Challenger & Shadow Evaluation.

AFRE-23 [champion/challenger research](champion-challenger.md) is complete. Explicit participants and frozen criteria use exact common shadow evidence with immutable AFRE-18/19/20/21/22 context. Every assessment is MANUAL_ONLY; eligibility does not deploy, roll back, retrain, recalibrate or change fusion weights. TEST cannot redefine a program, and predictive metrics do not establish trading profitability. **Stop after AFRE-24. Next scope: AFRE-25 — Final Integration, Hardening & Research Audit.** AFRE-25 hardening remains deferred.

AFRE-24 publishes this completed native research evidence through the [immutable service boundary](afre-service-api.md). Exact requested health/challenge metadata is descriptive, retains NONE_DESCRIPTIVE_ONLY / MANUAL_ONLY and never changes forecast values. The registry records metadata without deployment; the read-only service never trains, selects, promotes or executes. Frozen catalogs and exact IDs have no hidden latest. AFRE-25 remains Final Integration, Hardening & Research Audit.

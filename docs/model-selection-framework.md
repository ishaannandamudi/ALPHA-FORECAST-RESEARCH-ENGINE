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

**Next scope: AFRE-22 — Drift, Decay & Model Health.** Future scope covers
input/prediction/calibration/residual drift, signal decay, coefficient/weight drift,
monitoring windows and warning/degraded states. Model-health automation belongs to AFRE-22.
**Stop after AFRE-21.** Portfolio construction, risk optimization and execution
remain downstream projects after AFRE.

## AFRE-21 integration

AFRE-20 owns selection among fusion candidates. AFRE-21 does not add another selector. The optional fusion-candidate adapter is unsupported; no post-VALIDATION TEST winner is inferred. An explicit upstream SelectionResult can record an already-selected contributor, but it never selects fusion weights. See [fusion evaluation](fusion-evaluation.md).

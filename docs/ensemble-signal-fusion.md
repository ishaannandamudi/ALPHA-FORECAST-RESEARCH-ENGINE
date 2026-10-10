# AFRE-21 — Ensemble & Signal Fusion

AFRE-21 creates an immutable fusion artifact from an exact, predeclared source set. A fusion artifact is distinct from every source artifact: fitting or applying fusion never overwrites constituent models, signals or forecasts.

`afre.fusion` separates typed contracts, source adapters, compatibility, fixed rules, TRAIN QR fitting, target-free application, exact probability mixtures, missingness, diversity, evaluation, AFRE-19 accounting, snapshots, lineage and SQLite persistence. Engine 0.22.0; fusion schema 1.0; store 1.21; SQLite user_version=22. Earlier public schemas remain 1.0; Python 3.11+; zero runtime dependencies.

Supported families are FIXED_WEIGHT_POINT, LEARNED_LINEAR_POINT, FIXED_PROBABILITY_MIXTURE and FIXED_SIGNAL_BLEND. Fixed weights are declarations. Learned weights are training. TRAIN_STANDARDIZE fits only centers/scales for a fixed signal blend; it reads no response. VALIDATION and TEST cannot refit weights or transforms.

The exact source set, target/horizon, kind, unit, fold/dataset, clocks, constraints, intercept, bounds, seed and implementation are identity-bearing. Frozen application requires a repository feature-only guard and cannot read TargetVintage, including cached truth. Fit/application/evaluation use consistent read snapshots and publish immutable results.

Every inspected fusion experiment counts under AFRE-19, including failed attempts. AFRE-20 owns selection among fusion candidates. The optional adapter for selecting fusion candidates is unsupported here; there is no hidden selector. A single final predeclared artifact can be sealed for TEST. Arbitrary post-VALIDATION winner selection is unsupported. Stacking, constrained learned weights, ridge, source-subset search and automatic calibration are unsupported.

AFRE-22 drift/decay/health, AFRE-23 champion/challenger, AFRE-24 registry/service and AFRE-25 hardening remain deferred. There is no automatic health/promotion, portfolio construction or execution. Fusion predictive metrics do not establish trading profitability.

See [sources](fusion-sources.md), [fixed weights](fixed-weight-ensembles.md), [learned weights](learned-fusion-weights.md), [probability](probabilistic-fusion.md), [missingness](fusion-missingness.md), [diversity](fusion-diversity.md), [evaluation](fusion-evaluation.md), and the [completion report](AFRE_21_COMPLETION_REPORT.md).

Run `PYTHONPATH=src:. .venv311/bin/python -m examples.fusion_demo` for the 41-step offline walkthrough. `--core` excludes the expensive native-family and actual-horizon fixtures; `--reverse` reverses insertion/request order. Run `PYTHONPATH=src:. .venv311/bin/python -m benchmarks.fusion_profile` for measured bounded operations. [Recorded profile](fusion-profile.json) is a small offline measurement, with no production SLA.

Non-target-unit scalar blends (including dimensionless standardized and ordinal rank signals) cannot enter target-error statistical trials or return-cost evaluation without an explicit unit bridge. Native target-metric adapters reject them. They remain valid frozen signal outputs; no automatic return interpretation is made.

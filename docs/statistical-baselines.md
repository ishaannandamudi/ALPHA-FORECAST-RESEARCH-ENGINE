# Statistical baseline models (AFRE-5)

`afre.statistical_models` adds deterministic point models to frozen AFRE-4 folds.
Engine 0.6.0 adds model schema 1.0 and shared SQLite store 1.5/user_version=6.
All earlier schemas remain 1.0, with zero runtime dependencies.

The ten typed families are unconditional mean, unconditional median, supplied
reference value, causal persistence, ordinary linear regression, ridge, lasso,
elastic net, cross-sectional linear and residual linear. Mean/median use only
admitted TRAIN responses. A reference value is a fixed supplied scalar. Linear
families use the exact supplied features; no correlation-based selection occurs.

BaselineModelSpec composes the unchanged foundation ModelSpec through its
`foundation_spec` property. Its richer identity additionally pins the exact
registered feature set, AFRE-2 target definition/horizon, fold, preprocessing states,
intercept, fixed L1/L2 penalties, solver/version, rank/conditioning/convergence and
missing policies, seed and implementation version. Every choice is explicit.
The seed is recorded; these deterministic solvers perform no random updates.

FittedModelArtifact is a separate closed coefficient contract. The original
foundation ModelArtifact remains safe metadata for its original foundation dataset
domain; AFRE-5 does not reinterpret a multi-universe research grid as that dataset.
The foundation ExperimentSpec and validation semantics remain unchanged.

Persistence requires an explicit PersistenceReference declaring a completed trailing
simple/log return over the same elapsed horizon. Its registered market feature must
have dimensionless units and sufficient lookback. The observed feature is causal at
each origin; no future target is fetched. Transforming return units is rejected.
Other target/horizon semantics fail explicitly. This contract cannot authenticate
an opaque provider's scalar; provider derivation evidence remains necessary.

Cross-sectional linear uses multiple stable securities/origins, equal row weights
and an explicit global or absent intercept. Within-origin intercept fitting is
rejected: a learned intercept for an unseen future origin has no supplied causal
meaning. Residual linear consumes exact AFRE-2 residual-return labels and their
supplied benchmark lineage. Supplied PIT factor features can enter the feature set;
AFRE-5 estimates no new factor model from held-out data.

Use ModelRepository and ModelEngine: `fit_model`, `model_artifact`, `predict`,
`predict_batch`, `predict_samples`, `evaluate`, `compare_models`, `model_audit`,
`prediction_audit` and `model_history`. See the [offline demo](../examples/statistical_baselines_demo.py),
[fit semantics](model-fit-semantics.md), [linear solvers](linear-models.md),
[regularization](regularization-semantics.md) and [evaluation](point-forecast-evaluation.md).
No family selection, hyperparameter search, probabilities, calibration, portfolios
or execution is implemented. Predictive metrics establish no trading profitability.

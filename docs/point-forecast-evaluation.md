# Point forecasts and honest evaluation

PredictionInput contains only exact origin, frozen feature join, optional research
sample identity and typed scope. It accepts no target value. Prediction construction
and publication never load TargetVintage; a guarded demo/test forbids every such
read. Rich feature/source/calendar/adjustment compatibility and immutable membership
indexes are checked. PointForecast pins model, target definition, stable origin,
input, scalar prediction, model availability and computation/final availability.

VALIDATION, TEST and OUT_OF_SAMPLE_OTHER require model and all feature/preprocessing
availability <= origin's information cutoff. The model's recorded fit cutoff must
therefore also be at or before the origin. Computation can be recorded later; final forecast
availability is that actual declared computation time. `historical_admissible` means
the information boundary is valid, not that a later reconstructed forecast was
literally observed by AFRE at its earlier origin. IN_SAMPLE diagnostics require an
explicit post-fit computation time and mark historical_admissible=false. Their
metrics cannot be mixed with OOS partitions. TEST cannot be relabeled other OOS.

Evaluation joins exact pinned truth only at an explicit later cutoff. Predictions
must already be available. Unavailable, missing or unverified truth has an explicit
exclusion rather than an invented value. PointEvaluation records every requested
prediction, exact used sample/target IDs, values, partition, target/horizon, cutoff
and metrics. Different models, partitions or target definitions cannot be pooled.

Errors are prediction − truth. COUNT, mean error, MAE, MSE and RMSE use the paired
observations. R² is 1 − SSE/SST against the evaluation-set target mean; constant
truth yields an unavailable CONSTANT_TARGET state. Pearson requires two finite
varying observations, with explicit constant-target/prediction states. Spearman
uses deterministic average ranks for ties. Directional accuracy compares signs,
counting zero only when both signs are zero; it is not profitability.

Per-origin Pearson IC and rank IC remain separate from the pooled point metrics.
Their summary records valid origin counts, means, medians and population standard
deviations, preserving unavailable small/constant groups. This is an evaluation
diagnostic, not an AFRE-9 ranking model or AFRE-17 stability study.

Comparisons require exactly the same dataset/fold, target/horizon, scope, cutoff,
paired sample/target evidence and exclusions. Delta metrics are candidate minus
reference; lower delta MAE/RMSE is better, higher delta R² is better. Metrics do not
select a model or mutate a spec. TEST evaluation requires an explicit access identity
and purpose, persisting the existing AFRE-4 TestEvaluation contract with reuse history.
Its ready grid may include other declared horizons; each point evaluation uses its
own exact target subset. The semantic seal is not authentication or AFRE-19 governance.

No positions, P&L, portfolio Sharpe, transaction-cost strategy or profitability claim
is produced from point forecasts.

AFRE-6 composes this unchanged feature-only point forecast into explicit probability
contracts. Its forecast path additionally blocks TRAIN-response evidence reads.
Proper scores and coverage/PIT diagnostics use a separate
[probabilistic evaluation](probabilistic-evaluation.md), retaining exact-sample and
TEST boundaries. Diagnostics do not fit calibration; AFRE-7 owns transformations.

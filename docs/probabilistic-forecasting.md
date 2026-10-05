# Probabilistic forecasting

AFRE-6 adds `afre.probabilistic` above completed AFRE-5 point models and AFRE-4
frozen research folds. The historical AFRE-6 baseline is probabilistic schema 1.0, engine 0.7.0 and
store 1.6 / SQLite user_version=7. AFRE-7 extends the shared store to 1.7 /
user_version=8 with engine 0.8.0 and calibration schema 1.0. All prior schemas remain 1.0; prior interfaces keep
their strict store boundary and historical snapshot engine metadata.

`ProbabilisticModelSpec` pins exact completed converged point artifact, rich target
and horizon, fold, training cutoff, family, observation policy, centering, scale,
quantile and threshold definitions, uint64 seed and numerical implementation versions.
There is no family/hyperparameter search, selection, fitted calibration or ensemble.

`POINT_MODEL_RESIDUALS` uses response minus fitted point value on exactly the ordered
TRAIN matrix rows admitted by AFRE-5. `TRAIN_TARGETS` uses those TRAIN responses
unchanged and requires an UNCONDITIONAL_MEAN point scaffold. This preserves identical
feature/missing/label admission and causal model clocks for unconditional comparisons.
It estimates an unconditional target distribution; its forward location ignores the
point value. VALIDATION, TEST, PURGED, EMBARGOED and INELIGIBLE responses cannot enter
uncertainty estimation. In-sample residual uncertainty can be optimistic; AFRE-6
neither replaces it with OOS residuals nor claims unbiased uncertainty.

Fit uses one pinned SQLite read snapshot. TrainingObservations retains exact sample,
target, response and optional point/residual values. ProbabilisticFitInputs retains
only reference IDs, TRAIN order, preprocessing and clocks. TrainingDistribution
retains the sorted uncertainty pool and exact diagnostics. Artifact references inputs
and state; completed FitRun references the result, avoiding circular hash identity.
Definitions, evidence, inputs, diagnostics, state, artifact and run publish atomically.
Concurrent later/backdated data or point corrections cannot alter a frozen fit.

Fit start >= training cutoff and point availability; completion >= start; final state
and artifact availability >= completion and every admitted input's availability.
Historical OOS origin requires probabilistic artifact, base point model, fitted state,
features and preprocessing available <= origin information cutoff. Equality is admitted.
Actual forecast computation/final availability remains recorded separately. A later
historical reconstruction is not evidence of literal earlier receipt or computation.
IN_SAMPLE diagnostics require explicit later computation and are marked retrospective.

Forecast construction and publication never load TargetVintage, TrainingObservations
or DesignMatrix responses. They use frozen distribution state and AFRE-5 feature-only
prediction validation. Target truth is joined only by later evaluation. A forecast
contains exact model/base forecast/target/input IDs, distribution parameters, requested
quantiles/events, meaningful moments, availability and historical-admissibility flag.
Batch requests are unique and ordered by origin/security/identity; duplicate or oversized
batches fail explicitly. No wall-clock time enters semantic identity.

See [families](forecast-distributions.md), [quantiles](quantile-forecasts.md),
[events](threshold-probabilities.md), [scores](proper-scoring-rules.md) and
[evaluation](probabilistic-evaluation.md). Run the offline
[demo](../examples/probabilistic_demo.py) and [profile](../benchmarks/probabilistic.py).
AFRE-6 evaluates calibration diagnostics but does NOT fit calibration transformations.
AFRE-7 owns Forecast Calibration. Predictive metrics do not establish trading profitability.
Portfolio construction, risk optimization and execution remain downstream projects.

AFRE-7's [separate calibration layer](forecast-calibration.md) references these raw
forecasts without rewriting them. Calibration cannot fit from TEST or from a raw
forecast reconstructed after its historical origin. Applying frozen calibration
reads no targets. The AFRE-6 distribution/scoring API retains its exact semantics;
partial calibrated marginals do not become a full calibrated density implicitly.

## AFRE-8 composition
AFRE-8 pins every horizon's exact AFRE-6 artifact separately. Its covariance is
descriptive matched TRAIN dependence, not a new joint density. Expectations remain
unsupported for sparse quantiles. The shared point backbone does not reuse uncertainty
fitted for a different model. See [multi-horizon
forecasting](multi-horizon-forecasting.md).

## AFRE-10 integration

AFRE-10 may translate the exact raw AFRE-6 distribution location while preserving shape/scale and original bytes. Sparse quantiles remain sparse, never an invented CDF. Event-conditioned uncertainty is not a joint horizon model or conditional variance estimator.
See [event-conditioned forecasting](event-conditioned-forecasting.md).

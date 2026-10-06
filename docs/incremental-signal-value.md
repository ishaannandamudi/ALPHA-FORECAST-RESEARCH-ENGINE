# Incremental signal value

The caller supplies the candidate and references. `fit_target_models` creates one immutable
`PredictiveModelPair` with two fixed TRAIN QR readouts: target on references, and target on references
plus raw candidate or frozen-projection residual. The paired artifact fingerprint pins both models'
coefficients/intercepts, representation policy, exact common TRAIN rows/target vintages/truths,
projection, fit cutoff and actual availability. The two named coefficient fields identify the base
and augmented readouts within that fingerprint; no native downstream model is replaced.

TRAIN truth must be completed and known at fit cutoff. Both models use the projection's TRAIN-fitted
reference preprocessing and explicit intercept/condition policy. The candidate projection response
remains the candidate itself. Target fitting is a separate API with separate truth access and at
most15 references (augmented design≤17 columns). Perfectly redundant candidates may make the
augmented design rank deficient; this fails explicitly rather than claiming incremental value.

VALIDATION/TEST evaluation applies frozen models that were available by every evaluated origin.
It pins exact residual/sample IDs and later known target vintages. Base and augmented point metrics
share one complete truth/sample intersection. Deltas are augmented minus base for MSE, RMSE, MAE,
centered R² and Pearson, with native undefined states. Negative loss deltas indicate lower observed
loss on that supplied set; they do not imply significance, causality, automatic acceptance or profits.

Candidate and residual IC/rank IC, including descriptive time slices, share identical truths. Cross-sectional mode requires
one full universe/origin context per timestamp; temporal slices group by timestamp and do not
claim complete-universe cross-sectional semantics.
Partial target diagnostics correlate the candidate residual with target minus the frozen base model.
Descriptive temporal slices are not silently given complete-universe cross-sectional semantics.
A TEST evaluation needs an explicit identity and the inherited exact fold/sample/cutoff seal.
TEST cannot fit, choose candidates/references, tune settings or select a survivor.

There is no broad combination search, significance testing, automatic pruning or general ensemble
construction. AFRE-19 retains multiple-testing/overfitting controls; AFRE-20 retains model selection;
AFRE-21 retains ensemble/signal fusion. Cost evaluation remains AFRE-18, separate from downstream
portfolio construction, risk optimization and execution. See [partial correlation](partial-correlation.md)
and [cross-sectional evaluation](cross-sectional-redundancy.md).

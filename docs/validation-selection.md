# VALIDATION selection protocol

TRAIN fits; VALIDATION selects; TEST remains outside selection. Native preprocessing
and fitted parameters are frozen at the TRAIN cutoff. VALIDATION forecasts use the
frozen transform and actual native causal input admission. No VALIDATION fitting,
validation-based early stopping or automatic final refit occurs.

| Criterion | Direction | Required native evidence |
| --- | --- | --- |
| MIN_MSE | minimize | finite point predictions and exact truth |
| MIN_MAE | minimize | finite point predictions and exact truth |
| MAX_R2 | maximize | point predictions and nonconstant matched truth |
| MIN_CRPS | minimize | Gaussian or empirical-residual probability law |
| MIN_NLL | minimize | Gaussian location/scale density |

Point-only forecasts cannot acquire a fabricated probability law. Empirical NLL,
IC/rank IC, AFRE-18 net-edge, composites and calibrated-candidate orchestration are
deferred. An unsupported compatible score yields INCOMPATIBLE, with no fallback to
MSE. Undefined R² on constant truth remains unavailable.

Every declared VALIDATION sample has either an exact pair or an explicit exclusion.
Truth must be verified, completed and known by the request cutoff with exact
origin/target/horizon/fold identity. Valid candidates must share the exact observed
sample/truth set; comparing candidates on different favorable subsets is rejected.
Minimum support is declared before fitting. Insufficient support, fit failure and
numerical failure remain separate recorded states.

Primary metric direction, optional predeclared secondary metric direction, then
canonical candidate fingerprint form the lexicographic ordering. There is no
post-hoc simplicity preference. The baseline is an explicit optional recipe reference,
not an automatic inclusion or winning override. SelectionResult preserves the full
ordering, exact immutable TRAIN model and resource summary.

SelectionRequest pins the evaluation truth cutoff separately from SearchSpace.
SelectionResult.selection_cutoff_ns is this truth cutoff; available_ns is the result's
declared availability clock. These are research/provenance clocks, not runtime
optimization timers. Different cutoffs require distinct AFRE-19 attempts.

Winning on VALIDATION does not establish generalization, causality, independent alpha
or profitability. Later TEST evaluation must disclose the entire inspected pool,
adaptivity and prior TEST reuse through the native evaluation and AFRE-19 contracts.

# Regime-conditioned forecasting

AFRE-11 adds `afre.regime_conditioned` above completed AFRE-0 through AFRE-10.
Engine0.12.0, regime-conditioned schema1.0, store1.11/user_version12. Earlier
schemas remain1.0 and their source/test semantics are preserved. The roadmap
freezes 26 distinct phases, AFRE-0 through AFRE-25. AFRE-11 is complete; current implementation stops after AFRE-12.

RegimeConditioningSpec pins exact native point model, rich target/horizon, taxonomy,
scope, admitted membership kinds, matching, maximum age, TRAIN/state/effective
support minimums, fallback, numerical seed and versioned weighting/calibration policy.
Matching checks full ResearchSample/fold/PIT eligible universe and retains every
supplied candidate, mapping and exclusion. GLOBAL, MARKET, SECURITY and PIT SECTOR
matching are supported. VENUE/CUSTOM remain metadata with explicit unsupported scope.

Three fixed families are implemented. REGIME_TARGET_MEAN estimates TRAIN response
means by hard state. REGIME_RESIDUAL_OFFSET estimates hard-state mean fitted residuals.
SOFT_REGIME_WEIGHTED_OFFSET estimates probability-weighted residual means and applies
sum(p_state * offset_state). Hard memberships contribute one-hot weights where allowed.
No REGIME_LINEAR, learned gating, state-specific residual law or model selection exists.

Residuals use the exact completed AFRE-5 artifact's intercept/coefficients and admitted
TRAIN matrix. They are **in-sample fitted residual diagnostics**, computed after fit
cutoff, never fictional historical forecasts or out-of-fold estimates. Every label
must be known by cutoff and every regime usable at its own sample origin. This can
underestimate future residual bias, especially with flexible base models. No held-out
label informs conditioning parameters. State outputs report exact IDs/weights/counts,
weight sums and Kish effective support. Scarce states retain insufficient-data records.

FAIL rejects, USE_BASE preserves the exact base value, and GLOBAL_OFFSET adds the
unweighted mean residual over matched distinct TRAIN samples. If any positive soft
state lacks support the whole forecast uses its declared fallback; no mass is dropped
or renormalized. The global offset still requires matched minimum TRAIN support.

Feature-only application reads no target vintage or TRAIN matrix. Base/model/snapshot
and actual computation must be usable by the full origin cutoff; computation is not
backdated. This initial historical application computes at the origin instant. It
preserves exact base bytes and emits a distinct forecast artifact. Optional raw AFRE-6
location translation preserves shape/scale and recomputes quantiles/thresholds; it
creates no covariance/joint law. AFRE-7 calibrated outputs are incompatible inputs.

An optional exact AFRE-10 base is supported only with REGIME_TARGET_MEAN and explicit
event model compatibility. Order is base → event → regime **location replacement**,
not additive event residual fitting or a commutativity claim. The event distribution's
shape survives, while its location shifts to the state mean. USE_BASE retains the
event output. Other event composition families fail. No event×regime interactions.

Later evaluation compares exact identical sample/truth vintages, uses AFRE-5 point
metrics and supported AFRE-6 proper scores, and records TEST seal/reuse evidence.
Hard state groups, membership kind, transition cohort, horizon and event-base status
are descriptive with minimum counts. Soft diagnostics report actual probabilities,
weighted MAE, effective support, entropy and low-confidence counts, without argmax.
Coverage uses all supplied eligible forecasts; scored diagnostics use matched known
truths. Native AFRE-9 ranking receives exact neutral derived score refs; its wrapper
preserves matched truth and TEST controls. Constant predictions yield undefined IC.

Immutable safe JSON, verified indexes, frozen reads, atomic publication and bounded
unified lineage persist under transactional11→12 migration. Historical completion
reports retain their phase-time versions. Predictive metrics do not establish trading
profitability. Portfolios, risk optimization and execution remain downstream.

See [snapshots](regime-snapshots.md), [membership](hard-soft-regimes.md),
[transitions](regime-transitions.md), [calibration](regime-conditioned-calibration.md),
[drift](regime-drift.md), [external integration](external-regime-integration.md),
[profile](regime-conditioned-benchmark.md) and [A–BK report](AFRE_11_COMPLETION_REPORT.md).

## AFRE-12 composition boundary

[Mixture of Experts](mixture-of-experts.md) preserves exact native/neutral producer identity,
target/horizon compatibility, receipt-aware availability, causal gating inputs and missingness.
Fixed gates and one TRAIN-only constant simplex fit remain explicit. TEST never changes weights.
Finite Gaussian/empirical laws preserve components; quantile averaging is invalid. Component
calibration != mixture calibration. Matched truth/contribution/correlation/drift diagnostics and
same-origin rankings remain descriptive and never refit/select. No independence or profitability
is claimed; expert weights are forecast-combination weights, never portfolio weights. Downstream
HFT integration supplies AME/MCE/EIE/options adapters without direct implementation dependencies.
Frozen snapshots, append-only corrections and bounded lineage preserve older artifact bytes.

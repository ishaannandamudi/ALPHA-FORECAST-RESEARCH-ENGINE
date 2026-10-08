# Multi-horizon forecasting

AFRE-8 adds `afre.multihorizon`, engine 0.9.0 and multi-horizon schema 1.0.
Earlier contracts stay 1.0. `MultiHorizonRepository` adds shared store 1.8,
SQLite user_version=9, through a transactional 8→9 migration. Earlier repository
interfaces remain strict readers of their own versions.

A `MultiHorizonModelSpec` maps each exact rich target to its feature set, point
spec/model, fold, cutoff, preprocessing, and optional probability/calibration
spec/state. Supplied finite nonnegative horizon weights and a uint64 seed enter
identity. Reversing unordered bindings does not change identity. Weights use the
canonical HorizonSet order; they are never estimated or used for selection.

`INDEPENDENT_PER_HORIZON` supports different features, folds and cutoffs.
`SHARED_FEATURES_SEPARATE_MODELS` requires the same feature definitions but keeps
coefficients and learned transforms separate. `SHARED_LINEAR_BACKBONE` fits one
coefficient vector with one intercept per horizon. Its weighted squared-sum loss
uses only the all-horizon TRAIN intersection, with optional supplied ridge penalty
on coefficients, unpenalized intercepts and the existing pivoted Householder QR.
Rank failure and ill conditioning reject; no hidden solver repair occurs.

Ownership is explicit for coefficients, intercepts, transforms, scales and
calibration. GLOBAL_SHARED, HORIZON_SPECIFIC and GROUP_SHARED are representable;
the supported architectures accept only their exact implemented ownership maps.
Group fitting and latent parameters are deferred. The backbone currently requires
raw features and no learned preprocessing: shared learned transforms would also
need intersection-specific TRAIN admission. It produces a distinct shared point
artifact. Its AFRE-5 scaffold supplies causal feature/fold evidence, and its value
is replaced explicitly by the shared coefficients. Existing AFRE-6/7 uncertainty
cannot be relabeled as uncertainty for that different model, so that architecture
exposes point forecasts with probability/calibration surfaces UNSUPPORTED.

A bundle pins the same complete ForecastOrigin and stable instrument across all
entries. Point, raw probabilistic and calibrated layers remain distinct. Declared
layers must be present for an AVAILABLE entry. MISSING or UNSUPPORTED horizons
remain explicit, yielding COMPLETE, PARTIAL or UNAVAILABLE. Model, calibration,
shared fit and dependence state must be known by origin cutoff. Included features
are checked by the existing target-free prediction/application functions.

Bundle computation and final availability retain their real physical clocks;
computation cannot precede any included artifact's availability, and final
availability is at least their maximum. A later
composition can describe information knowable at the old origin, but it does not
claim the bundle was physically emitted then. Calibration retains AFRE-7's stronger
requirement that its raw forecast existed at origin. No feature receipt is backdated.
`forecast_for_horizon` and `surfaces` return exact ordered entries, expectations,
medians, quantiles and horizon-qualified events with explicit missing/unsupported
values. Only IDENTITY calibration preserves an expectation from a full raw PDF.

Fits and assembly freeze one consistent read snapshot and publish atomically.
Immutable artifacts, verified relational indexes, safe canonical JSON and one
bounded lineage traversal provide replay and audit. Defaults: 16 horizons,
100,000 total TRAIN samples/results, 128 shared features, 4 million work cells,
10,000 evaluations, 100,000 audit nodes, depth64 and 8MiB payload/traversal bytes.
Hard limits are 64 horizons/depth and 16MiB canonical payload. Caller bounds may
be reduced. No provider I/O, executable artifacts or runtime dependency is added.

Run `PYTHONPATH=src:. .venv311/bin/python examples/multihorizon_demo.py` for the
causal two-horizon example; the [profile](multi-horizon-benchmark.md) distinguishes
large numerical kernels from its smaller persisted historical workload.
AFRE-9 adds independent rankings per horizon. Selection, ensembles, portfolios
and execution remain deferred.

## AFRE-9 boundary

AFRE-9 ranks each exact horizon independently. Point, raw probability and calibrated score sources retain their model/state/quantile/event identity. Unsupported statistics remain unavailable. No cross-horizon scalar fusion or aggregate rank is constructed. See [rankings](cross-sectional-ranking.md).

## AFRE-11 composition boundary

[Regime conditioning](regime-conditioned-forecasting.md) consumes exact causal
filtered hard/soft state evidence without changing this phase's contracts. As-of
is distinct from all six availability clocks. TRAIN state means/fitted-residual
offsets, fixed soft weighting and explicit fallback are horizon-specific. Application
preserves exact base bytes and reads no truth. Matched evaluation/ranking retains
PIT scope and TEST controls. Global calibration cannot silently transfer, and
descriptive regime drift never refits. MCE/AME remain external neutral data producers;
downstream HFT integration supplies adapters. Predictive metrics do not prove profitability.


## AFRE-14 sequence integration

Sequence specs, transforms, datasets and models remain independently target/horizon-specific; actual1h/1d identities stay distinct without inferred covariance.
See [temporal sequences](temporal-sequence-models.md) and [causal sequence training](causal-sequence-training.md).
AFRE-15 uncertainty decomposition is complete; AFRE-16 Signal Orthogonalization & Redundancy Analysis is complete; AFRE-17 Invariance & Stability Research is complete; predictive metrics do not establish profitability.

## AFRE-15 uncertainty integration

AFRE-15 pins each exact target/horizon and independently represents actual1h/1d uncertainty. No proportional time scaling, cross-horizon joint law or portfolio-risk interpretation is introduced. See [uncertainty decomposition](forecast-uncertainty-decomposition.md).

Predictive uncertainty does not establish trading profitability. These are descriptive forecast artifacts; portfolio construction, risk optimization and execution remain downstream projects after AFRE. AFRE-15 has no direct external-engine dependency.

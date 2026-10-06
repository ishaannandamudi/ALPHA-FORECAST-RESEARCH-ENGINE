# Event-conditioned forecasting

AFRE-10 consumes exact immutable provider-neutral events. Event extraction remains
upstream in EIE; the downstream HFT system implements adapters. AFRE imports no
EIE/AME internals and reads only its own registry. The frozen roadmap remains
26 distinct phases, AFRE-0 through AFRE-25. Stop after AFRE-10.

The `event_conditioned` package separates contracts, windows/matching, TRAIN fitting,
truth-free forecast application, later evaluation, the AFRE-9 bridge, persistence,
validation and bounded lineage. Engine0.11.0, event-conditioned schema1.0,
store1.10/user_version11; all prior public schemas remain1.0. Transactional10→11
adds tables, indexes and triggers without replacing older metadata or DDL.

`EventReference` pins event ID/revision, provider/version, class/subtype/tags,
subject, optional occurrence, six-clock availability, quality, source and optional
materiality/novelty/surprise. `SourceReference.event_snapshot` retains an existing
neutral EIE snapshot when supplied. No news parsing or event detection occurs.

A spec pins the exact completed AFRE-5 model and target/horizon, window, criteria,
attribute semantic keys/thresholds, reaction ScoreSpecs, overlap/minimum counts,
fixed numerical policies and approved historical-delivery attestors. Matching
uses the ResearchSample's exact full origin and fold, eligible PIT universe and
explicit issuer/group mapping vintages. There is no implicit latest revision.

Four conservative families are implemented: EVENT_CLASS_OFFSET,
MATERIALITY_LINEAR, SURPRISE_LINEAR and EVENT_FEATURE_LINEAR. They fit the target
response independently from exact admitted TRAIN matrix rows. Class conditioning
uses a TRAIN conditional target mean; its application shift is that mean minus
the exact base forecast. It does not claim an out-of-sample residual estimate from
in-sample base predictions. Linear fits use an intercept and declared attributes
or reaction features with deterministic QR. No base-prediction feature, arbitrary
interaction, nonlinear model, learned threshold, search or ensemble is implemented.

Model availability must follow completed baseline fitting and the training cutoff.
Every TRAIN event/reaction must be available at its own historical origin; every
label must be known at fit cutoff. Distinct sample/event/class minimums are explicit.
Unmatched observations remain recorded exclusions. An unseen or underpopulated
class yields an explicit unchanged-baseline fallback.

Application references exact point model/forecast, sample, partition and full origin.
It never reads TargetVintage values. The base point and raw probabilistic artifacts
remain byte-identical. Gaussian/empirical distributions translate location;
quantile-only forecasts translate supplied quantiles. Scale, shape and residual
samples stay fixed; thresholds are recomputed using the existing AFRE-6 semantics.
No joint distribution or conditional-variance model is claimed.

An AFRE-7 unconditioned calibration state is incompatible with this new statistic.
Conditioned calibration assessments admit unique non-TRAIN/non-TEST VALIDATION
samples from the exact conditioned model. They report insufficient data or
unavailable: conditioned calibration fitting is deferred. The API rejects a
SUPPORTED state and does not relabel unconditioned calibration as conditioned.

Physical forecast computation must follow all inputs and lie within the origin
cutoff. Because cutoff≤origin and computation≥origin, the implemented causal
composition occurs at origin=cutoff. Later reconstruction of forecast computation
itself is unsupported. Historical-delivery evidence for event data retains actual
later receipt/ingestion/computation and requires exact source/entity binding and
an explicitly approved attestor. Publication alone proves nothing about delivery.

CUSTOM scopes are representable metadata but have no implemented matching adapter.
Event windows use elapsed UTC nanoseconds only; session/bar event-window calculations,
event decay models, class-specific variance and fitted conditioned calibration are
unsupported. Provider claims cannot be authenticated by contracts alone.

Conditioned forecast != causal effect. Event-conditioned ranking != portfolio
construction. Predictive skill never proves profitability. AFRE-11 now adds a separate
[regime-conditioning layer](regime-conditioned-forecasting.md). Exact event bases
can precede regime target-mean location replacement under explicit compatibility.
Other event/regime compositions and learned gating remain unsupported. Portfolios, risk optimization and execution remain downstream.

See [clocks](event-time-semantics.md), [windows](event-windows.md),
[attributes](event-surprise-materiality-novelty.md), [overlap](event-overlap.md),
[reaction signals](event-reaction-signals.md), [evaluation](event-conditioned-evaluation.md),
[profile](event-conditioned-benchmark.md) and [A–BC report](AFRE_10_COMPLETION_REPORT.md).

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


## AFRE-13 composition boundary

[Nonlinear interactions](nonlinear-feature-interactions.md) consume these completed
contracts through exact neutral scalar references. Explicit definitions and TRAIN-only
knots/scaling/coefficients/tree splits preserve source availability and actual computation.
TEST cannot choose interactions/splits/knots. Event×regime, microstructure×context,
options×context and expert×state share the generic layer; no direct external-engine
implementation dependency exists. Target-free application, immutable source revisions,
matched later truth, AFRE-9 ranking and bounded replay preserve prior semantics.
Diagnostics are arithmetic/descriptive, not causal importance; no automatic pruning/model
selection or sequence modeling is implemented. Predictive metrics do not establish
profitability. AFRE-14 Temporal / Sequence Models remains deferred.

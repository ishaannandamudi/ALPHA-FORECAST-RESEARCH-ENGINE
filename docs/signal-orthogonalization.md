# Signal orthogonalization

AFRE-16 treats orthogonalization as a causal TRAIN-fitted transform. Orthogonal != independent:
zero linear correlation does not prove statistical or causal independence, a unique economic
source, or non-redundancy under nonlinear relationships. A residual signal is not guaranteed alpha.
Predictive metrics do not establish trading profitability.

`OrthogonalizationRepository` extends the unchanged AFRE-15 repository. The historical AFRE-16 checkpoint used engine 0.17.0,
orthogonalization schema 1.0, shared store 1.16/user_version17. Transactional 16→17 migration
preserves all prior rows, DDL, metadata and public schema versions. Runtime dependencies remain empty.

The dedicated package separates contracts, source extraction, alignment, correlations, QR fitting,
residual application, partial correlation, fixed target-model comparison, evaluation, descriptive
stability, explicit feature/ranking integration, persistence and bounded unified lineage.
`SignalReference` pins a source family and exact semantic/model/version key; `SignalObservation`
adds the exact source artifact, research sample, full origin, numerical presence and availability.
Original detailed quality states remain in the pinned source artifact; AVAILABLE means a numerical
value is present, not that the data or predictive claim is verified.

Supply a candidate and canonical reference set, one AFRE-4 fold, fit cutoff and target/horizon.
`OrthogonalizationSpec` pins intercept, explicit NONE or TRAIN_STANDARDIZE preprocessing,
equal-row weights, minimum support, rank tolerance, condition limit, seed and numerical version.
The deterministic solver uses AFRE-5 pivoted Householder QR and a Frobenius condition estimate
of its triangular factor. It rejects deficient/ill-conditioned designs; no pseudo-inverse or
implicit regularization is introduced. The candidate is the projection response, never forecast truth.

Only admitted complete TRAIN rows with origins before fit cutoff fit coefficients and preprocessing.
Every input was available by its origin. Missing TRAIN inputs fail without hidden dropping/imputation.
The matrix and projection are computed in one frozen read snapshot and published atomically.
VALIDATION/TEST cannot fit, choose references/candidates, tune preprocessing/thresholds or select lags.
Supplied multi-candidate requests fit independently in canonical request order without a survivor policy.

Two modes are implemented: TEMPORAL_PANEL and CROSS_SECTIONAL_HISTORICAL. The latter fits across
complete same-origin eligible TRAIN grids and applies the frozen fit within later origins. No
per-origin refitting mode is advertised. Equal-row weights imply that larger historical grids
contribute more observations; no hidden per-origin reweighting occurs.

Bounds: 16 references/candidates, 2000 rows, 2m work cells per calculation, 17 matrix columns,
32 stability windows, 20,000 artifacts per family, 8 MiB payload/lineage bytes, 100,000 lineage nodes
and depth 64. Incremental target readouts support at most 15 references because their augmented
intercept design is bounded to17 columns. Smaller caller bounds also apply on reads.

Use [the offline walkthrough](../examples/orthogonalization_demo.py),
[the profile](orthogonalization-profile.json) and [the completion report](AFRE_16_COMPLETION_REPORT.md).
See [redundancy definitions](signal-redundancy.md), [residual construction](orthogonal-signal-construction.md)
and [incremental evaluation](incremental-signal-value.md).

AFRE-17 remains Invariance & Stability Research across time, regimes, events, sectors/universes,
market environments and feature-distribution shifts, with coefficient/sign stability, degradation,
environment-conditioned diagnostics and an explicit no-causal-proof boundary. No such framework
is implemented here. No automatic pruning, broad reference-set search, downstream model replacement,
portfolio construction, risk optimization, execution or direct external-engine integration occurs.
The frozen roadmap remains 26 distinct phases, AFRE-0 through AFRE-25.

Direct ordinary-feature binding requires the security entity to match the origin. Source revision
selection remains with the upstream PIT store; AFRE-16 pins the caller-supplied admissible exact
source. Diagnostic definitions additionally pin probability/calibration producers, alternative
model sets, interval settings and the full supplied uncertainty policy through a stable digest.

Cross-sectional fitting, evaluation and ranking require one full universe/origin context per
timestamp. Distinct
universe, cutoff, session or build contexts at the same timestamp are rejected rather than pooled
into a single rank-IC slice.

AFRE-17 adds [declared environment stability research](invariance-stability-research.md) over frozen artifacts. PIT memberships, target/horizon compatibility, exact intersections and minimum counts remain explicit. Input shift and error degradation are separate; there is no causal-proof, significance, profitability, auto-refit/prune or promotion claim. AFRE-18 cost-aware research evaluation remains deferred.

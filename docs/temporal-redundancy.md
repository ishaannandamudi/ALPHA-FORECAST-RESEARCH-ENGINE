# Temporal redundancy

TEMPORAL_PANEL regresses a supplied candidate on supplied references across admitted historical
security/panel observations. Exact sample IDs and full origins are canonicalized by origin time,
stable instrument fingerprint and sample ID. One supplied fold partitions TRAIN/VALIDATION/TEST;
TRAIN sources must be causal at their original cutoff and origins must precede fit cutoff.
Equal-row weights are explicit. This is not a same-origin coefficient fit or an independence test.

TRAIN-only means/scales and QR coefficients are frozen. Held-out reference/candidate values and
later target corrections cannot change the fit. Missing TRAIN inputs fail; held-out missing inputs
produce absent residuals and explicitly excluded common-intersection samples. No implicit forward
fill, lag selection, unbounded history, target-derived feature, or hidden future context is added.

Event, regime, expert/mixture, nonlinear and sequence outputs can enter through closed scalar
adapters with exact model/semantic/unit and sample/target/horizon identities. Sequence hidden-state
vectors are unsupported. Uncertainty scalars require an identified or explicitly numerical proxy
component with exact measure/method/units/model/covariance policy; quality labels are not invented
variance or alpha. Ordinary features and neutral microstructure/context/options sources retain
receipt/reconstruction distinctions. No direct AME/MCE/EIE/options-engine dependency is introduced.

Supplied multiple candidates are independent requests, not an ordered orthogonal basis or search.
Lagged diagnostics, sequential basis construction, symmetric factors, nonlinear conditional
independence and incremental-value matrices are deferred. Actual 1h/1d targets, folds and metrics are
separate; no pooled predictive claim or horizon-time scaling is invented.

`RedundancyStability` summarizes caller-supplied compatible, ordered, disjoint known windows:
raw-unit coefficient ranges (undoing each TRAIN standardization), residual/candidate variance
ratios and raw-reference correlation values. It cannot refit, delete a signal, change a feature
set, promote survivors or modify downstream models. This bounded descriptive summary is not the
AFRE-17 environment/invariance framework, which remains deferred.

See [redundancy measures](signal-redundancy.md) and [AFRE-17 boundary](signal-orthogonalization.md).
Residuals are not guaranteed alpha. Predictive metrics do not establish trading profitability.

Direct ordinary-feature binding requires the security entity to match the origin. Source revision
selection remains with the upstream PIT store; AFRE-16 pins the caller-supplied admissible exact
source. Diagnostic definitions additionally pin probability/calibration producers, alternative
model sets, interval settings and the full supplied uncertainty policy through a stable digest.

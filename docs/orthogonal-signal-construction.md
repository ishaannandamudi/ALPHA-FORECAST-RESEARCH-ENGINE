# Orthogonal signal construction

An `OrthogonalSignalValue` pins the projection artifact, aligned row, sample, stable security/full
origin, raw candidate, projected component, residual, raw candidate unit, numerical presence and
actual computation/final availability. The aligned row pins every exact candidate/reference source
observation. The projection pins its spec, exact TRAIN rows/candidate values, preprocessing,
coefficients, intercept, rank/condition, VIF, TRAIN metrics and correlation matrix.

For complete inputs: `projected = intercept + standardized_references · coefficients` and
`residual = raw_candidate - projected`. NONE uses centers 0/scales 1; TRAIN_STANDARDIZE stores
population TRAIN means/scales and rejects constant references. With NO_INTERCEPT, TRAIN_STANDARDIZE
still explicitly centers references; NONE does not. Residuals retain candidate units; no held-out
or residual standardization is implicit. Missing candidate/reference input yields an explicit
MISSING artifact with all numerical payload fields absent, never zero.

`OrthogonalizationEngine.residual` uses feature-only reads and a frozen repository snapshot.
The internal application helper also requires the guard. Target vintages, response matrices and
paired target-model TRAIN truths are forbidden even when cached. Full audits and later evaluation
have separate, explicit truth access. The projection must be available by the application origin.
Final residual availability is at least every input, projection availability and actual computation;
it must be no later than the origin information cutoff. Later computation cannot backdate a residual.

For externally sourced values preserve upstream publication, upstream source availability, actual
AFRE receipt, ingestion, computation and final availability. A provider timestamp is not AFRE
availability. Publication 10:00/receipt 10:02 cannot serve origin 10:01. A historical archive downloaded
months later is unavailable at the old origin without qualified historical-delivery evidence.
Binding qualified reconstruction requires caller-approved attestors, exact source/entity evidence,
and preserves the actual later AFRE clocks. Qualified channel replay describes proved historical
channel availability; it does not claim AFRE literally ingested the record then. Trust in timestamp
honesty and attestor qualification remains an explicit boundary; typed evidence is not authentication.

Corrections create new source identities. A late correction is excluded from old-origin application;
a caller can build a new causal observation/residual at an admissible later origin. Old bytes remain
unchanged. Exact IDs and frozen SQLite snapshots isolate concurrent signal/projection/target corrections.

Explicit integration is available through `residual_vintage` and `engine.rank`. Feature export requires
a caller-named registered definition with matching units and exact projection fingerprint as version
and transformation identity, plus the derived source dataset. It publishes the computed residual as a
new source for subsequent AFRE-1 research, with actual clocks and UNVERIFIED research quality. Caller
registration/persistence is explicit; existing feature sets/models are never rewritten. The AFRE-9
bridge pins the exact projection version, residual artifact provenance and supplied historical groups.

See [cross-sectional semantics](cross-sectional-redundancy.md). A residual is a versioned transform,
not guaranteed alpha, uniqueness or independence; predictive metrics do not establish profitability.

Direct ordinary-feature binding requires the security entity to match the origin. Source revision
selection remains with the upstream PIT store; AFRE-16 pins the caller-supplied admissible exact
source. Diagnostic definitions additionally pin probability/calibration producers, alternative
model sets, interval settings and the full supplied uncertainty policy through a stable digest.

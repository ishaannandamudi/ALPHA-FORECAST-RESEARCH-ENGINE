# Forecast calibration — AFRE-7

Calibration data is fit data. `afre.calibration` creates a separate immutable
CalibrationState above a completed AFRE-6 probabilistic model. Raw forecasts and
all earlier contracts, schemas, rows and metadata remain unchanged. Calibration
schema is 1.0; engine 0.8.0; shared store 1.7 / SQLite user_version=8.

CalibrationSpec pins raw model/spec, rich target/horizon, method, explicit sample
reservation and origin range, cutoff, minimum count, selected events/levels,
fixed bins, optional interval/alpha, tie and extrapolation conventions, numerical
versions and seed. The seed is recorded; these deterministic methods do not use
randomness. No method or parameter is selected from evaluation scores.

Supported methods are IDENTITY, BINNED_PROBABILITY, ISOTONIC_PROBABILITY,
QUANTILE_OFFSET, CONFORMAL_ABSOLUTE_RESIDUAL and ROLLING_CONFORMAL. Asymmetric
conformal, adaptive bins, crossing repair and joint calibrated densities are not
advertised. See [probability](probability-calibration.md),
[quantiles](quantile-calibration.md), [conformal](conformal-calibration.md),
[partitions](calibration-partitions.md) and [drift](calibration-drift.md).

Fit reads one SQLite snapshot. A complete reservation/partition/TEST preflight
precedes calibration truth reads. Requests pin exact raw forecasts and exact
TargetVintage identities; corrected labels require explicit new requests. Each
raw forecast must have existed at its origin availability cutoff and be
historically admissible. Truth must be completed, verified and available at or
before the calibration cutoff. Future/unverified truth is excluded explicitly;
minimum count failures abort. Rolling selection occurs after truth eligibility.
Publication is one transaction, with deterministic semantic replay and bounds.

CalibrationState pins fit inputs/observations, raw model, target, mappings,
offsets/conformal scores, diagnostics, disjointness and cutoff/start/completion/
availability clocks. Its availability cannot precede fit completion or any used
truth/raw forecast. Fit diagnostics are explicitly retrospective on the fit
sample; they are not independent evidence.

Application reads only state metadata, spec, frozen transformations and the raw
forecast. It reads neither target truth nor calibration response sets. Both raw
forecast and state must be available by the origin's availability cutoff. The new
CalibratedForecast records actual computation/availability, references the raw
forecast and preserves all untouched marginals. IDENTITY preserves raw output
and its full distribution. Other methods define adjusted marginals or an interval,
not a coherent full density/CDF; calibrated NLL/CRPS/PIT/scale are unsupported.
Raw proper scores remain available separately. This conservative boundary avoids
inventing a PDF from independently adjusted probabilities or quantiles.

Independent evaluation uses the exact AFRE-6 raw evaluation and pinned later
truth, requires a single state/model/target/scope, and refuses calibration sample
reuse. TEST requires the existing explicit TEST access/reuse record. Comparison
requires identical raw forecast IDs, sample IDs, target IDs/values, exclusions,
cutoff and protocol. Brier/pinball/coverage/width deltas are descriptive; applicable
identity NLL/CRPS are preserved. Coverage-error deltas compare absolute nominal
gaps. No score accepts, replaces or refits a calibrator automatically.

One bounded audit traverses calibration, completed raw/point fits, folds and
upstream feature/target evidence. Calibrated-forecast lineage contains past
calibration truth; later deployment truth appears only in evaluation lineage.
Safe canonical JSON and domain-separated hashes establish consistency, not
provider authentication or protection against an administrator rewriting history.

Run `python -m examples.calibration_demo`, `pytest tests/calibration` and
`python -m benchmarks.calibration`. The [completion report](AFRE_7_COMPLETION_REPORT.md)
records actual gates and limits. Calibration, sharpness, discrimination, point
accuracy and proper scores are distinct. Predictive metrics alone do not establish
trading profitability. AFRE-8 now composes separate horizon forecasts;
portfolio construction, risk optimization and execution remain downstream projects.

## AFRE-8 composition
AFRE-8 preserves one exact CalibrationState per horizon. Raw and adjusted surfaces stay
distinct; adjusted marginals do not create a full calibrated PDF or expectation. No
cross-horizon calibrator pooling occurs. See [horizon-specific
calibration](horizon-specific-calibration.md).

## AFRE-10 integration

A changed event-conditioned statistic cannot silently inherit an unconditioned AFRE-7 state. AFRE-10 assessments require unique causal VALIDATION samples, separate from TRAIN/TEST; fitted event-conditioned calibration is unavailable rather than assumed.
See [event-conditioned forecasting](event-conditioned-forecasting.md).

## AFRE-11 composition boundary

[Regime conditioning](regime-conditioned-forecasting.md) consumes exact causal
filtered hard/soft state evidence without changing this phase's contracts. As-of
is distinct from all six availability clocks. TRAIN state means/fitted-residual
offsets, fixed soft weighting and explicit fallback are horizon-specific. Application
preserves exact base bytes and reads no truth. Matched evaluation/ranking retains
PIT scope and TEST controls. Global calibration cannot silently transfer, and
descriptive regime drift never refits. MCE/AME remain external neutral data producers;
downstream HFT integration supplies adapters. Predictive metrics do not prove profitability.

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

## AFRE-15 uncertainty integration

AFRE-15 assesses exact stored calibrated intervals at their nominal levels. Marginal calibration does not invent a full law or identify causal uncertainty sources; calibration and sharpness remain separate. See [uncertainty decomposition](forecast-uncertainty-decomposition.md).

Predictive uncertainty does not establish trading profitability. These are descriptive forecast artifacts; portfolio construction, risk optimization and execution remain downstream projects after AFRE. AFRE-15 has no direct external-engine dependency.

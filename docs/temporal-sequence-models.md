# Temporal / Sequence Models

AFRE-14 adds causal ordered predictor histories to AFRE-0 through AFRE-13. Engine **0.15.0**, sequence schema **1.0**, shared store **1.14**, SQLite **user_version=15**; all previous public schemas stay **1.0**. There are zero runtime dependencies.

`afre.sequence` separates immutable definitions, observations, windows, datasets, transforms, models, forecasts, evaluation, diagnostics and persistence. `SequenceEngine` computes in frozen read transactions and publishes validated artifacts atomically through `SequenceRepository`. Canonical JSON, exact fingerprints and relational projections bind every dependency. Semantic replay checks masks, ordering, readout parameters and evaluation results.

Only `EXPONENTIAL_DECAY_LINEAR` and `LINEAR_STATE_SPACE` are implemented. Supplied dynamics feed a TRAIN-fitted linear readout using existing AFRE-5 pivoted QR and optional fixed ridge. There is no broad model search, learned recurrent network, attention, bidirectional future context or executable provider payload. The state dimension equals the pinned feature dimension, with a hard maximum of 16.

Observation time != availability time. A token is selected only when its observation timestamp meets the declared window and final source availability is at or before the exact origin cutoff. An earlier upstream publication timestamp does not override actual AFRE receipt. Qualified historical delivery requires explicitly approved attestors and preserves actual later ingestion/computation evidence.

Candidate evidence must already be available at actual construction. TRAIN snapshots may be reconstructed later with their actual construction clocks retained. Forecasting requires the model, transform, snapshot, optional probability base and actual computation to be available by the application cutoff. No forecast reconstruction contract silently backdates an output. Application is restricted to admitted VALIDATION/TEST samples and enforces a target-free repository guard.

[Windows](sequence-windows.md), [masks](sequence-masking.md), [time encoding](sequence-time-encoding.md), [causal fitting](causal-sequence-training.md), [families](sequence-model-families.md), [neutral sources](external-sequence-integration.md), [evaluation](sequence-evaluation.md), [profile](sequence-benchmark.md), [A–BT report](AFRE_14_COMPLETION_REPORT.md).

AFRE-15 Forecast Uncertainty Decomposition is complete; AFRE-16 Signal Orthogonalization & Redundancy Analysis is complete; AFRE-17 Invariance & Stability Research is complete. Predictive metrics do not establish profitability. Portfolio construction, risk optimization and execution remain downstream projects after AFRE.

## AFRE-15 uncertainty integration

AFRE-15 supports declared fixed-design unpenalized sequence-readout covariance, conditional on fixed dynamics and TRAIN transforms. It estimates no uncertainty over hidden dynamics or model selection. See [uncertainty decomposition](forecast-uncertainty-decomposition.md).

Predictive uncertainty does not establish trading profitability. These are descriptive forecast artifacts; portfolio construction, risk optimization and execution remain downstream projects after AFRE. AFRE-15 has no direct external-engine dependency.

## AFRE-16 integration

Exact causal sequence forecasts can enter temporal/historical cross-sectional redundancy as scalars. Hidden-state vectors, lag search and nonlinear conditional-independence claims remain unsupported. The sequence model/history is pinned and cannot be refit by redundancy diagnostics.

See [signal orthogonalization](signal-orthogonalization.md). Supplied candidate/reference sets are fixed;
no automatic pruning or broad signal search occurs. Orthogonal != independent, residuals are not
guaranteed alpha, and predictive metrics do not establish trading profitability. The frozen roadmap
remains26 distinct phases, AFRE-0 through AFRE-25; AFRE-17 Invariance & Stability Research is complete.

AFRE-17 adds [declared environment stability research](invariance-stability-research.md) over frozen artifacts. PIT memberships, target/horizon compatibility, exact intersections and minimum counts remain explicit. Input shift and error degradation are separate; there is no causal-proof, significance, profitability, auto-refit/prune or promotion claim. AFRE-18 cost-aware research evaluation remains deferred.

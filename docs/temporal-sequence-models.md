# Temporal / Sequence Models

AFRE-14 adds causal ordered predictor histories to AFRE-0 through AFRE-13. Engine **0.15.0**, sequence schema **1.0**, shared store **1.14**, SQLite **user_version=15**; all previous public schemas stay **1.0**. There are zero runtime dependencies.

`afre.sequence` separates immutable definitions, observations, windows, datasets, transforms, models, forecasts, evaluation, diagnostics and persistence. `SequenceEngine` computes in frozen read transactions and publishes validated artifacts atomically through `SequenceRepository`. Canonical JSON, exact fingerprints and relational projections bind every dependency. Semantic replay checks masks, ordering, readout parameters and evaluation results.

Only `EXPONENTIAL_DECAY_LINEAR` and `LINEAR_STATE_SPACE` are implemented. Supplied dynamics feed a TRAIN-fitted linear readout using existing AFRE-5 pivoted QR and optional fixed ridge. There is no broad model search, learned recurrent network, attention, bidirectional future context or executable provider payload. The state dimension equals the pinned feature dimension, with a hard maximum of 16.

Observation time != availability time. A token is selected only when its observation timestamp meets the declared window and final source availability is at or before the exact origin cutoff. An earlier upstream publication timestamp does not override actual AFRE receipt. Qualified historical delivery requires explicitly approved attestors and preserves actual later ingestion/computation evidence.

Candidate evidence must already be available at actual construction. TRAIN snapshots may be reconstructed later with their actual construction clocks retained. Forecasting requires the model, transform, snapshot, optional probability base and actual computation to be available by the application cutoff. No forecast reconstruction contract silently backdates an output. Application is restricted to admitted VALIDATION/TEST samples and enforces a target-free repository guard.

[Windows](sequence-windows.md), [masks](sequence-masking.md), [time encoding](sequence-time-encoding.md), [causal fitting](causal-sequence-training.md), [families](sequence-model-families.md), [neutral sources](external-sequence-integration.md), [evaluation](sequence-evaluation.md), [profile](sequence-benchmark.md), [A–BT report](AFRE_14_COMPLETION_REPORT.md).

AFRE-15 Forecast Uncertainty Decomposition remains deferred. Predictive metrics do not establish profitability. Portfolio construction, risk optimization and execution remain downstream projects after AFRE.

# Causal sequence training

Each model binds one exact target/horizon, AFRE-4 fold and training cutoff. `SequenceTransformArtifact` must name the complete target-specific admitted TRAIN sample set with exact snapshot bindings. Duplicate, missing, VALIDATION and TEST bindings fail. Every source token is checked against its own sample origin, not merely the later training cutoff. Expert/mixture features, including experts nested inside nonlinear outputs, must match the exact target/horizon. Historical delivery attestors must be explicitly approved in the model spec.

`STANDARDIZE` learns population means and population standard deviations from unmasked TRAIN tokens. Overlapping histories count once per bound sample/token, so repeated tokens receive the explicitly declared sample weighting. Zero standard deviation fails; there is no scale replacement. `NONE` records zero centers/unit scales. No clipping, projection or time normalization is learned. Transform start/completion/availability preserve actual construction clocks.

`SequenceDataset` pins exact sample/snapshot/target IDs, fold, feature order, transform, target and horizon. Labels are accessed only for admitted TRAIN rows and must be completed and available by fit cutoff. QR learns only intercept and linear readout coefficients; supplied window, decay, state transition, gain, dimension and ridge never change from held-out data. Held-out values/labels do not alter fitted state or models.

Forecast application does not read TargetVintage, SequenceDataset, SequenceTrainingRow or earlier nonlinear training matrices/rows. It reads immutable model parameters, transform state, admitted sample metadata and causal predictor snapshots. Later truth is read only for explicitly separate evaluation/calibration assessment. TRAIN forecasts are rejected. TEST fitting and calibration are rejected; evaluation reuses the existing seal and reuse evidence.

[Model families](sequence-model-families.md), [evaluation](sequence-evaluation.md).

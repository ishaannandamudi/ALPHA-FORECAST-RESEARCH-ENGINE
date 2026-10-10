# Fixed weight ensembles and scalar signals

A fixed FusionSpec declares every finite weight before outcome assessment. SIMPLEX requires nonnegative weights summing to one within the pinned tolerance. EXPLICIT_SIMPLEX normalization is identity-bearing; NONE never silently rescales weights. SIGNED_LINEAR permits signed point/signal combinations and explicitly makes no probability-mixture claim.

Point output is `intercept + sum(weight * source value)`. NO_INTERCEPT requires zero. WITH_INTERCEPT pins the fixed intercept. Every point contribution stores its source/output, original value, transformed value, effective weight and weighted value. FusedForecast records the actual intercept used, including zero on fallback. The contributions and intercept reconstruct the output.

FIXED_SIGNAL_BLEND accepts scalar signals with exact units. TRAIN_STANDARDIZE stores population centers/scales from the complete admitted TRAIN grid and produces an explicitly dimensionless output. Constant columns fail; no VALIDATION/TEST recomputation occurs. Standardization plus fallback is unsupported without a normalized fallback bridge. Cross-sectional rank signals require a declared ordinal-rank unit and a scalar-signal blend; they are not automatically target-unit point forecasts or probabilities. No automatic neutralization or return interpretation occurs.

Each horizon has a separate source set, spec, artifact and output. Actual 1h/1d tests use independent native graphs. Fusion never manufactures a joint law across horizons. Weight dominance is descriptive; simplex effective count and entropy do not measure forecast quality or independence.

# Feature distribution shift

Feature selectors are frozen in `StabilityAnalysisSpec`. `FeatureShiftDiagnostic` uses exact AFRE-16 `SignalObservation` references with provider/version/semantic identity/unit and origin bindings. It records the two environment populations, every supplied observation, values including explicit missingness, counts, Type7 quantiles, population mean/std and final research availability. Missing observations are represented as missing values rather than dropped silently.

Distances are environment B minus A mean/std, each declared quantile shift, missing-fraction delta, signed standardized mean difference using sqrt((stdA²+stdB²)/2), exact empirical KS sup|FA−FB| and average absolute declared-quantile distance. A zero/tiny pooled scale makes standardized mean difference unavailable. Each numeric distribution requires minimum observed feature N. Empty/all-missing cohorts remain insufficient. No KS p-value or significance claim is attached.

COMMON_INTERSECTION for a feature pair requires the entire declared set to be that pair. PAIRWISE_INTERSECTION uses the pair's common sample IDs; PER_ENVIRONMENT_NATIVE retains distinct populations. Soft cohorts retain source records but cannot claim weighted distribution distances. Source observations must be causally available at their full origins; a later archive download cannot be silently backdated.

Input shift is stored separately from error degradation. Prediction mean is a distinct native environment metric; target distribution reconstruction and broader prediction-distribution summaries are deferred. No target is read in feature-shift construction or forecast metadata. A shift does not prove that forecast performance degraded or explain its cause.

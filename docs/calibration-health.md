# Frozen calibration health

Coverage compares known truth to an exact native interval at the requested levels. Coverage error is absolute observed-minus-nominal coverage. Interval width is sharpness only, not proof of calibration. Unsupported intervals remain UNAVAILABLE; a point value does not invent a predictive law.

For threshold events, HealthDiagnosticRequest pins the threshold and reliability edges. Events use strict greater-than. Reliability bins are left-closed/right-open, with the final bin also including probability 1. Each bin preserves count, mean forecast probability, observed event frequency and absolute gap. ECE weights gaps by support; MCE takes the maximum populated-bin gap. Empty bins remain empty. Gaussian/empirical/eligible finite mixtures retain native analytic CRPS/NLL; density/atom semantics are not mixed or replaced by jitter.

The calibrator is frozen. Health evaluation does not refit it, change probabilities or mutate intervals. Separate tests compare calibrator/native forecast bytes before and after monitoring. Calibration diagnostics require known-at-cutoff truth and native TEST seals when applicable.

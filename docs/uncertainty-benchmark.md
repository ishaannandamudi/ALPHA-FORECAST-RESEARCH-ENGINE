# Bounded uncertainty profile

Run `PYTHONPATH=src:. .venv311/bin/python -m benchmarks.uncertainty_profile` offline.
The recorded [profile](uncertainty-profile.json) blocks seven socket/DNS entry points.
It includes44 VALIDATION and4 TEST causal decompositions from11 native source families,
three eligible TRAIN covariance estimates with12 rows each, independent covariance/prediction
oracles, intervals, coverage/sharpness, deterministic buckets, two-window descriptive drift,
canonical persistence/restart and unified lineage. These are neutral synthetic research fixtures.

The profile separates real artifact counts from200 repeated QR calculations and1000 repeated
mixture moment calculations. Those repetitions are arithmetic work, not independent forecasts
or enlarged out-of-sample evidence. Timings measure component construction, covariance fitting
and QR arithmetic, decomposition replay validation, interval extraction, evaluation, drift,
audit, serialization, idempotent persistence, restart and SQLite storage including open WAL.
No production SLA or throughput claim follows from this bounded local run.

Runtime QR and prediction quadratic variance are compared with an independent developer-only
Gauss-Jordan normal-matrix OLS oracle. The oracle is never imported by the runtime package.
Independent tests also cover sigma², population empirical moments, mixture within/between,
supplied state weighted spread/entropy, expert disagreement, closure, inclusive interval
coverage, Pearson/Spearman, rank buckets and zero-total shares. Maximum absolute covariance/
prediction error is recorded in the JSON; pass tolerances for small fixtures are1e−12.

Uncertainty and predictive metrics do not establish profitability. Portfolio construction,
risk optimization and execution remain downstream projects after AFRE. AFRE-16 Signal
Orthogonalization & Redundancy Analysis remains deferred.

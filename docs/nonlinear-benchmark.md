# Nonlinear offline profile

Run `python -m benchmarks.nonlinear_profile`; results are persisted in
[profile JSON](nonlinear-profile.json). Sockets and DNS are blocked in the profile.
The causal workflow builds exact admitted AFRE-4 TRAIN evidence and all three families,
fits knots, constructs matrices, predicts, ranks, evaluates, audits, persists and restarts.

Separate2000-row QR/tree arithmetic kernels and40000 transform applications measure
bounded computation. Those arithmetic rows are explicitly not historical causal TRAIN
samples. Runtime bounds are not overridden to claim scale. The report separates actual
causal TRAIN rows, artifact/node/storage counts, numerical coefficient error, replay
identity and per-stage elapsed seconds. Local machine measurements provide no production
SLA. The causal fixture remains deliberately small; deployment-scale performance is
unverified. No external engine implementation or runtime dependency is used.

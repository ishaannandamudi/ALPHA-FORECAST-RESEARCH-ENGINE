# Bounded offline mixture profile

Run `PYTHONPATH=src:. .venv311/bin/python -m benchmarks.mixture_profile docs/mixture-profile.json`.
The [measured profile](mixture-profile.json) records machine-local elapsed times and storage.
Sockets and DNS are blocked. This is no production latency or throughput SLA.

The causal fixture contains12 admitted TRAIN rows,6 point experts,3 probabilistic experts and
origins60/80. It profiles exact expert lookup, fit replay, fixed composition,1000 external revision
publications, finite-law scores/moments, matched evaluation, ranking/IC, diagnostics/drift,
unified lineage, deep audit, persistence, restart and storage. Independently labelled kernels
exercise10000 synthetic arithmetic rows and50000 weighted point sums; those rows are not extra
causal TRAIN evidence. No benchmark silently duplicates labels to claim research sample size.

Independent arithmetic checks report maximum absolute errors for fixed point output, known
simplex solution, Gaussian CDF, weighted expectation, total variance, threshold/CDF complement
and effective expert count. Additional pytest oracles verify Gaussian/empirical event edges,
CRPS, NLL, matched deltas and pairwise correlations. Bounds are explicit and failure is atomic.

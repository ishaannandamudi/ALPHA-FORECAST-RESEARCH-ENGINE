# Regime-conditioned offline profile

Run `PYTHONPATH=src:. .venv311/bin/python -m benchmarks.regime_conditioned_profile docs/regime-conditioned-profile.json`.
The [saved profile](regime-conditioned-profile.json) measures the exact causal hard/soft
TRAIN workflow, eight additional taxonomy versions, 1,000 additional neutral snapshots,
a ten-transition history, point/raw-probability applications, matched state/transition
metrics, same-origin ranking/IC, TEST evaluation, drift, bounded lineage, full audit,
SQLite storage and restart. The separate 50,000-row weighted residual kernel measures
arithmetic throughput; those rows are not claimed as admitted causal TRAIN samples.

Independent arithmetic/statistics oracles check state residual means, soft offsets,
weighted shifts, vector sum/mass change, matched MSE delta, Pearson IC and state
probability drift. State target means and actual1h/1d identities also have focused
fixtures. Maximum absolute error is recorded and required <1e-12. Timings include
validation and publication where named and depend on host/workload. There is no
production SLA, trading strategy, portfolio return or profitability claim.

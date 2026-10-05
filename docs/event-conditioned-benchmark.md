# Bounded AFRE-10 offline profile

Run `PYTHONPATH=src:. .venv311/bin/python -m benchmarks.event_conditioned_profile docs/event-conditioned-profile.json`.
The [recorded profile](event-conditioned-profile.json) measures one synthetic causal
workflow: 100 extra event references, 100 separate overlap observations, nearest
selection, class replay, two linear models, four conditioned forecasts, matched
comparison, AFRE-9 rank/IC, bounded lineage, full audit, persistence and restart.
A separate kernel makes50,000 window checks over500 origins; it excludes storage
and semantic admission and is never presented as end-to-end throughput.

Timings and file sizes are observations from this local run, outside artifact
identity. Full audit verifies earlier phases too. Independent stdlib linear-regression
oracles report the maximum coefficient absolute error. Tests separately check class
means, matched deltas, subgroup counts, IC and exact probability translation.
No production latency/SLA, capacity estimate, HFT readiness or profitability claim.

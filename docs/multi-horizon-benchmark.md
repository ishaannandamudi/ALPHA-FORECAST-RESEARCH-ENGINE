# Multi-horizon profile

Local run on 2026-10-04, Python3.11.16, standard-library runtime only. No SLA.

The synthetic numerical workload has 3,000 residual rows and four horizons with
known linear covariance. A separate set-intersection kernel matches 2,997 keys.
These kernel rows do not claim historical AFRE delivery evidence. The complete
persisted workload uses two causal typed horizons, eight matched TRAIN rows,
100 forecast bundles, raw/calibrated surfaces, independent evaluation, 357 audit
nodes and 113 multi-horizon artifacts. Repeated bundles retain real later
composition clocks; paired evaluation uses one bundle per exact origin.

| Operation | Seconds |
| --- | ---: |
| aligned shared fit and persistence | 0.131391 |
| bounded lineage and persistence | 0.259505 |
| bundles and persistence | 2.916641 |
| causal covariance and persistence | 0.197511 |
| causal upstream fixture | 3.480264 |
| covariance 3000 by 4 and psd | 0.003545 |
| evaluation and persistence | 0.074816 |
| horizon set 100 | 0.000488 |
| idempotent persistence | 0.036116 |
| raw and calibrated surfaces | 0.129603 |
| restart and full audit | 1.856477 |
| synthetic intersection 3000 | 0.001987 |

SQLite size: 9,875,456 bytes. Maximum covariance error against
its independently specified matrix: 0.0. Weighted MSE aggregate error: 0.0.
PSD validation passed for the singular rank-one reference. Correlation is not
exposed. Audit and restart validated identical serialized bundle bytes.

Publication timings include semantic validation, serialization and indexes.
The separate idempotent persistence timing measures repeats of existing artifacts.
Neither timing isolates a production storage subsystem or establishes scale limits.
The 3,000-row results measure numerical kernels, not a full 3,000-row ingestion
and persistence pipeline. Financial forecasting quality or profitability is not
inferred from these timings.

Reproduce with `PYTHONPATH=src:. .venv311/bin/python benchmarks/multihorizon.py`.
See [machine-readable measurements](multihorizon-profile.json) and
[architecture limits](multi-horizon-forecasting.md).

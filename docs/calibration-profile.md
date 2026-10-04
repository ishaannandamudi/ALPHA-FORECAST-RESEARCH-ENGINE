# Offline calibration profile

Run `.venv311/bin/python -m benchmarks.calibration` from the repository root.
The benchmark emits JSON measurements and a cProfile summary. Timings are local,
not a production SLA, and exclude no correctness checks from persistence.

The computational fixture generates 5,000 typed observations, four exact event
comparisons and three quantile levels. These exercise PAV/isotonic, conformal,
quantile offsets and before/after diagnostics. They are deliberately separate
from causal repository evidence and are not persisted as admitted observations.
The real store fixture builds all prior causal layers, fits all six methods on
seven reserved observations and applies seven later forecasts per method. It
measures independent evaluation, comparison, rolling diagnostics, complete audit,
persistence, byte-identical restart and storage.

Local run measured 2.958 seconds for isotonic plus diagnostics, 0.859 seconds for
conformal plus diagnostics and 2.212 seconds for quantile offsets plus diagnostics
on 5,000 generated observations. The four isotonic mappings contain 7, 6, 12 and
9 blocks. Sorting precedes linear PAV pooling; queries use binary search, avoiding
quadratic block copying and scanning. Numerical fixtures give zero absolute error
for PAV rate, conformal rank/q_hat and interval coverage; actual residual-offset
fit error is 2.220446049250313e-16 and ECE error is 5.551115123125783e-17.

| Persisted causal operation | Local seconds |
| --- | ---: |
| Prior causal scaffold | 3.969 |
| Calibration sample construction | 0.101 |
| Per-method fit, validation and publication | 0.440–0.516 |
| Seven-forecast application and publication | 0.031–0.040 |
| Per-method evaluation and publication | 0.152–0.160 |
| Per-method comparison | 0.044–0.045 |
| Rolling diagnostic and publication | 0.072 |
| Full forecast lineage audit and publication | 1.060 |
| Whole-store semantic audit | 8.527 |
| Restart and exact byte replay | 0.010 |

The store contains 100 calibration artifacts, 343 forecast-lineage evidence
nodes and 13,463,552 SQLite bytes after closing. cProfile identifies canonical
structured-data decoding, strict contract validation and whole-store semantic
audit as the dominant persisted-work costs. Bounds cap samples, bins, blocks,
levels/events, scores, rolling windows, forecasts/evaluations/diagnostics, payload
bytes, total window work and shared audit traversal. Overflow explicitly rejects;
there is no silent truncation. Larger causal persistence workloads and production
throughput remain future engineering work.

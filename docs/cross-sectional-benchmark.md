# Cross-sectional profile

Local offline run on 2026-10-04, Python3.11.16, standard-library runtime only.
Timings are measurements of this bounded fixture, not a production SLA.

The numerical workload repeats 1,000-security kernels across 12 synthetic vectors
(12,000 security-origin cells), with 20 groups. These vectors measure ranking,
z-score, median/MAD, percentile, group demeaning and Pearson IC only. They do
not claim PIT universe ingestion, historical delivery evidence or persisted
1,000-security rankings.

A separate causal pipeline persists four eligible securities, three ranked
securities and two actual origins, including explicit late-signal exclusion,
external lookup, peer/group transforms, truth, IC, buckets, stability and bounded
lineage. The pipeline stores 56 cross-sectional artifacts and an 82-node audit.
Atomic persistence timings include validation, serialization and index writes.

| Operation | Seconds |
| --- | ---: |
| causal atomic persistence and validation | 0.057745 |
| causal bounded audit and persistence | 0.139071 |
| causal external lookup | 0.000276 |
| causal ic buckets truth and persistence | 0.035679 |
| causal materialization including peer transforms | 0.016987 |
| causal second origin stability and persistence | 0.134614 |
| causal upstream and four security fixture | 3.644392 |
| restart and full registry audit | 1.896556 |
| synthetic group demean 12 by 1000 | 0.303679 |
| synthetic ic 12 by 1000 | 0.004054 |
| synthetic mad and percentile 1000 | 0.043842 |
| synthetic rank 12 by 1000 | 0.006797 |
| synthetic zscore 12 by 1000 | 0.260047 |

| Independent numerical oracle | Maximum error |
| --- | ---: |
| group demean | 0 |
| mean std zscore | 0 |
| median mad | 0 |
| pearson | 1.1102230246251565e-16 |
| percentile | 1.1102230246251565e-16 |
| spearman stability | 1.1102230246251565e-16 |
| top bottom spread | 0 |

SQLite size: **9,326,592 bytes**. Maximum numerical error:
**1.1102230246251565e-16**. The references use the closed-form population
variance of 0 through 999, median499.5, MAD250, exact percentile and group means,
standard-library Pearson correlation, known Spearman -0.5 and exact target
differences. These fixtures establish numerical correctness for their stated
inputs; they do not establish predictive quality or trading profitability.

Run `.venv311/bin/python -m benchmarks.cross_sectional` from the repository root.
See [machine-readable measurements](cross-sectional-profile.json),
[rankings](cross-sectional-ranking.md) and [completion evidence](AFRE_9_COMPLETION_REPORT.md).

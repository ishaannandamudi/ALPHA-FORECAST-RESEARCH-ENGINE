# AFRE-2 offline target profile

Measured on this local checkout with Python 3.11 on 2026-10-04. Run
`PYTHONPATH=src:. .venv311/bin/python -m benchmarks.targets`. Inputs are synthetic;
the caller chooses a temporary SQLite store, which is removed after the profile.
There is no network, fitted model, predictive-performance claim or production SLA.

Workload: **20,000 raw source observations**, **12,000 label rows**, 20 stable
securities, 1,000 observations/security and 4,000 explicit origins. Three targets
use elapsed horizons 2/4 nanoseconds: simple return, log return and close-based
maximum adverse excursion with sampling interval 1. Tiny time units keep this a
deterministic synthetic exercise; they are not a realistic exchange data frequency.
`TargetBounds(origins=5000)` explicitly accommodates the batch; remaining bounds
use their defaults. The profile intentionally queries a bounded security subset.

| Operation | Local seconds |
| --- | ---: |
| Source object construction | 0.506 |
| Store initialization/migration | 0.004 |
| Source validation, immutable persistence and commit | 5.499 |
| Freeze exact 20,000-vintage source build | 3.901 |
| Construct, recalculate, validate and persist 12,000 labels + dataset | 23.220 |
| Indexed known-by-cutoff retrieval, 600 rows with frozen dataset filter | 0.853 |
| Revalidate/idempotently persist those 600 rows | 0.342 |
| One label lineage/audit, 8 nodes | 0.203 |
| Deep store validation/recalculation, 32,011 artifacts | 22.812 |
| Restart and validate frozen dataset manifest | 0.674 |
| Restart query/retrieval with byte-identical 600-row replay | 0.884 |

Closed SQLite storage: **162,521,088 bytes** (~155 MiB), including canonical
evidence, immutable label payloads and indexes. Construction and initial persistence
are measured together because the trusted batch API atomically recalculates and
validates every persisted label; the separate idempotent pass measures persistence
validation of existing exact rows. Cutoff 1000 returns no labels; final availability
1001 equals the eligible cutoff. Every queried row and the complete dataset manifest
are canonical-byte identical after restart.

`EXPLAIN QUERY PLAN` reports
`SEARCH target_vintages USING INDEX target_known_idx (definition_id=? AND available_ns<?)`.
The cutoff API applies SQL predicates/indexes before decoding bounded candidates;
it does not scan/decode every target. Bar lookup uses frozen build/security/completion
indexes. Snapshot-local source identity reuse avoids rehashing the complete source
manifest per label while retaining read/payload/index and deep replay validation.

Frozen dataset:
`afre.target_dataset:1.0:2491217da14fc7b440f08322ee9607b08d1726a60fee1e191ccc2618874e133b`.
Timings depend on local hardware, filesystem and instrumentation; they are acceptance
evidence for this bounded workload, not latency/throughput guarantees.

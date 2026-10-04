# Offline feature-store benchmark

Local run: 2026-10-04. Python 3.11.16; SQLite 3.53.4; Darwin arm64.
Zero runtime dependencies. One synthetic run in a temporary caller-owned SQLite
WAL store; no networking. These are observations, not production SLA claims.
Run `PYTHONPATH=src:. .venv311/bin/python benchmarks/feature_store.py` to reproduce
the workload. Timings vary by machine, cache and load; no statistical speed claim
is made.

Workload: **20,000 vintages**, five registered definitions, 20 stable security IDs,
200 observations per definition/security. Single lookups repeat 200 times; the
historical batch joins 40 origins across 200 cells. The benchmark freezes/reloads
a materialization and asserts byte-identical replay. Its source lineage has two
nodes; the separate deterministic walkthrough exercises a 14-node derived DAG.

| Operation | Wall seconds |
| --- | ---: |
| Initialize/migrate new SQLite store | 0.001817 |
| Construct, validate and insert 20,000 vintages; transaction commit | 16.956329 |
| 200 single PIT lookups | 0.182935 |
| 40-origin × 5-feature historical join (200 cells) | 0.244884 |
| Join and persist frozen materialization | 0.799511 |
| One two-node source lineage query | 0.000895 |
| Full validation of 20,007 persisted artifacts | 22.103530 |
| Restart and canonical materialization reload | 0.320828 |

SQLite file after checkpoint/close: **114,429,952 bytes**
(109.13 MiB). Rows embed immutable
contracts/provenance for self-contained validation; this is not a compressed
columnar-storage benchmark. Insertion includes construction, canonical hashing,
validation, index/trigger work and persistence, not raw SQL insertion alone.
Full audit intentionally traverses all artifacts; normal PIT lookup does not.

Observed query plan:

```text
SEARCH fs_vintages USING INDEX fs_pit_idx (definition_id=? AND entity_id=? AND available_ns<?) | USE TEMP B-TREE FOR LAST TERM OF ORDER BY
```

The plan uses the feature/entity/availability index. SQLite additionally sorts
fingerprints for deterministic equal-time candidate enumeration; conflicting ties
still require explicit predecessor precedence. Each historical cell uses indexed
retrieval rather than scanning every stored vintage.

Materialization fingerprint:
`afre.fs_materialization:1.0:41e985de32d2246595c47ae718566e5e47654b2e09b26cbddae1088d7b8473d2`.

Exact raw measurements:

```json
{
  "batch_join_cells": 200,
  "batch_join_seconds": 0.24488370900508016,
  "batch_origins": 40,
  "construction_validation_insertion_commit_seconds": 16.956328833010048,
  "features": 5,
  "full_validation_seconds": 22.103530124993995,
  "initialization_migration_seconds": 0.0018172080162912607,
  "join_and_persist_materialization_seconds": 0.7995114169898443,
  "lineage_nodes": 2,
  "lineage_seconds": 0.0008950419723987579,
  "lookup_query_plan": "SEARCH fs_vintages USING INDEX fs_pit_idx (definition_id=? AND entity_id=? AND available_ns<?) | USE TEMP B-TREE FOR LAST TERM OF ORDER BY",
  "materialization_fingerprint": "afre.fs_materialization:1.0:41e985de32d2246595c47ae718566e5e47654b2e09b26cbddae1088d7b8473d2",
  "observations_per_feature_security": 200,
  "restart_and_materialization_replay_seconds": 0.32082808297127485,
  "securities": 20,
  "single_lookup_count": 200,
  "single_lookup_seconds": 0.1829351249616593,
  "sqlite_bytes_after_checkpoint_close": 114429952,
  "validated_records": 20007,
  "vintages": 20000
}
```

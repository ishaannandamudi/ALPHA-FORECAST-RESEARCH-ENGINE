# AFRE-3 offline universe benchmark

Run: `PYTHONPATH=src:. .venv311/bin/python -m benchmarks.universes`.

Local Python 3.11.16 measurement on 2026-10-04. Synthetic offline workload; these
are observations, with no production SLA. Tests also ran on this workstation during
part of the measurement. The first snapshot includes cProfile overhead; the repeated
snapshot does not. Correctness assertions cover exact membership/resolution,
repeated snapshot bytes and restart reload.

Workload: 2,000 stable securities and issuers, 2,000 separate listings, 2,000
historical symbol records, 2,000 membership vintages, 2,000 tradability records,
one supplied calendar/complete coverage and 8,000 AFRE-1 price/volume vintages.
Each security has two completed observations per market feature. Explicit common
stock, price, mean dollar volume, listing session age and market-history rules apply.

| Operation | Seconds |
| --- | ---: |
| Initialize and migrate | 0.008 |
| Ingest 2,000 securities and their histories | 22.462 |
| Freeze 20,002 input evidence/vintage IDs | 10.621 |
| 20 symbol/venue as-of resolutions | 4.431 |
| 20 stable-security membership queries | 5.925 |
| Full snapshot, including profiler overhead | 52.473 |
| Repeated full snapshot without profiler | 16.470 |
| 20 eligibility evaluations in one pinned read | 0.364 |
| Persist snapshot with deterministic replay checks | 26.060 |
| One security audit and lineage | 1.876 |
| Full integrity/calculation audit | 47.177 |
| Restart and exact snapshot reload | 1.653 |

Database: 119,549,952 bytes after close/checkpoint. Snapshot:
5,245,921 bytes; input build: 1,740,433 bytes; security audit:
17 nodes; full audit: 24,008 artifacts. All fit the default
2,000-security / 100,000-input / 8 MiB universe artifact bounds.

| Table | Rows |
| --- | ---: |
| u_artifacts | 16,005 |
| u_records | 12,002 |
| u_build_records | 12,002 |
| u_build_features | 8,000 |
| fs_vintages | 8,000 |
| u_eligibility | 2,000 |

Query plans confirm indexed retrieval:

| Query | Plan |
| --- | --- |
| symbol | SEARCH u_records USING INDEX u_symbol_idx (type_name=? AND symbol=? AND venue=? AND known_ns<?) |
| member | SEARCH u_records USING INDEX u_membership_idx (type_name=? AND owner_id=? AND security_id=? AND known_ns<?) |
| price | SEARCH fs_vintages USING INDEX fs_history_idx (definition_id=? AND entity_id=? AND effective_ns<?) |

The snapshot profile reports 187,446,710 calls (175,990,680 primitive).
Eligibility, validated artifact resolution, canonical deserialization and per-observation
market lookup dominate cumulative time. Registry reads validate payload, hash and
indexes; no unaudited scalar shortcut is used. Transaction-scoped identity caching
avoids repeatedly hashing the same large coverage/input manifest and is cleared
on exit. Single calls still validate their exact input manifest; serving optimization,
incremental builds, paginated bulk APIs and live feed adapters are future work.

Snapshot identity: `afre.u_snapshot:1.0:961db642134d18335f7c552a6b7f95d844924d1f0da25e984e46addda17de4ea`.

Contract regression tests cover temporal ticker change/reuse, announced future
changes, corrected histories, reverse insertion and concurrent writes separately.
No market realism, predictive fitting, portfolio, execution or profitability claim
is implied. See [PIT universes](point-in-time-universes.md) and
[eligibility](security-eligibility.md).

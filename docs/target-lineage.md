# Target isolation, lineage and persistence

All new identity domains begin `target_`: definitions, policies, source bars/builds,
calendars, actions/streams, benchmark/returns, vintages, sets, datasets and audits.
Canonical JSON, the closed class/enum registry, finite scalars and domain-separated
SHA-256 follow the existing foundation rules. No generic float wrapper crosses the
feature/target boundary. The AFRE-1 feature repository rejects target artifacts;
feature DAGs require feature definitions, normalization requires exact feature
vintages, and source references recursively reject target namespaces. All previous
transitive provenance checks remain intact and their tests are unmodified.

`audit_target` returns the immutable vintage and exact bounded lineage IDs. The
vintage resolves the target/window, full origin, source build, selected P0/P1/path,
actions, benchmark, completion, clocks, quality and absence reason. Source-build
lineage includes the neutral upstream source, calendar and action stream. The
compact manifest pins every admitted observation; the audit expands the used price
evidence and predecessor chains, not every unused bar in the source universe.
Dataset audits additionally traverse exact rows/set/universe. Benchmark returns
retain exact supplied source/window/version evidence; no benchmark constituent
construction is implied. Builder identity is in definition/vintage/dataset metadata.

Normal reads validate bounded canonical payloads, fingerprints, types and indexes.
`audit()` validates every persisted artifact and recursively checks referenced
evidence. Target vintages are deterministically recalculated on insertion and deep
audit, including policies, actual selections, values, clocks, quality and universe
eligibility. A plausible but fabricated value fails replay. Explicit lineage rejects
cycles and excessive depth/nodes/bytes. A cache is confined to one pinned transaction
or read snapshot; it reuses only validated immutable source identities and is cleared
on exit. It is not a cross-snapshot cache hiding later storage corruption.

`TargetRepository` upgrades store 1.1/user_version=2 to **1.2/user_version=3** in an
additive transaction. Foundation schema 1.0, feature-store schema 1.0, old tables,
payload bytes, original metadata and historical migration code remain unchanged.
New target engine/store/schema metadata identifies the extension. The strict old
repositories reject the upgraded future layout; use TargetRepository for shared
AFRE-0/1/2 access. Failure rolls back to the valid prior layout; unknown future
versions/layouts fail closed.

Immutable artifact and membership tables have UPDATE/DELETE/replacement-insert
protections; exact repeated insertion is idempotent only after stored-data validation.
Definition logic conflicts fail. Startup compares exact DDL/indexes/triggers/metadata.
Read/audit detects tampered payload/hash/type/temporal indexes, malformed build/dataset
membership and orphan records. Hashes prove content consistency, not provider
authenticity or protection against a malicious administrator rebuilding the whole file.

Indexes cover source cutoff, build/security/bar completion, definition/availability,
full origin identity and timestamp, intervals, source/benchmark, target set and frozen
dataset rows. Queries restrict candidate rows in SQL. `TargetBounds` explicitly limits
origins, instruments, definitions, rows, source/path observations, lineage depth/nodes
and serialized bytes; excess fails rather than truncates. The canonical decoder's
16 MiB/depth-64 global envelope bounds also apply. Large workloads must be explicitly
partitioned into appropriately bounded materializations/queries.

Concurrent writers cannot alter immutable frozen membership. Read snapshots ensure
consistent batch visibility; later corrections/rebuilds have new content identities.
The [demo](../examples/target_demo.py), [tests](../tests/target_engine),
[profile](target-benchmark.md) and [completion report](AFRE_2_COMPLETION_REPORT.md)
record offline replay, migration, corruption and isolation evidence.

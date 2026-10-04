# Point-in-time joins, scopes and frozen rows

`point_in_time_join(origins, dataset, features)` returns immutable
`PointInTimeJoinResult` records: an unchanged AFRE-0 `ForecastFeatureRow` and one
audit per definition. Every selected projection must equal the audited exact
vintage under the recorded policy, and every absence retains its explicit state.
The complete definition set must match the dataset; origin range, universe,
calendar, adjustment and source compatibility are validated. A dataset may contain
AFRE-0 target specifications as metadata, but no target observations enter lookup.

Single lookup, multiple features at one origin and historical joins share
`select_as_of`. A join begins one SQLite read transaction and pins a snapshot
before reading cells. Concurrent later or even backdated inserts cannot enter
that in-progress join. A later fresh query may see a newly inserted historically
admissible record. `materialize` seals the exact selected rows, audit vintages,
policies, creation time and implementation identity; future inserts cannot mutate
it. Materialization treats origin results as a sorted semantic set and rejects
duplicate origins. Serving rows and research rows have identical selection bytes.

## Indexed bounded retrieval

SQLite indexes `(definition_id, entity_id, available_ns DESC, effective_ns)` and
history `(definition_id, entity_id, effective_ns, available_ns)`, plus dataset,
build, source, predecessor and historical scope relationships. Each cell uses an
indexed cutoff lookup; it does not load all vintages. Equal-time candidates have
an explicit bound and require precedence. Batch work is one indexed retrieval per
cell rather than an unbounded Cartesian scan of every stored vintage.

Default bounds: 1,000 origins; 1,000 instruments; 256 features; 100,000 cells;
128 tie/scope candidates; 5,000 history records; lineage depth 64; 10,000 lineage
nodes; 8 MiB serialized bytes. Exceeding a bound raises a contract error rather
than truncating. Callers may supply positive `QueryBounds`; the foundation JSON
envelope still has its own 16 MiB/64-level hard limits. History returns all known
vintages including future-effective KNOWN_FACT observations; computation supplies
an explicit effective window to history.

## Explicit scope relationships

SECURITY keys are stable instrument IDs. ISSUER, SECTOR, MARKET and MACRO values
have explicit stable entity IDs. A historical `ScopeBinding` relates a security
to an entity/scope with [start, end) validity, AFRE knowledge cutoff and source
evidence. `known_ns` means the supplied relationship was legitimately known to
AFRE then; it is not a publication timestamp. The caller must establish delivery
evidence for externally supplied relationships. Missing mapping yields
NOT_APPLICABLE, never a broadcast. Conflicting equally known entities fail.
An issuer feature cannot reach an unrelated security; market/macro broadcasts
also require explicit relationships. Cross-scope computation is unsupported.

An audit records mapping fingerprint, selected vintage/source, full clocks,
freshness/state, policy and reason. A conflict raises `VintageConflict` before
producing a misleading row. Missing lookup does not inspect later vintages to
infer future values or expose them through an audit.

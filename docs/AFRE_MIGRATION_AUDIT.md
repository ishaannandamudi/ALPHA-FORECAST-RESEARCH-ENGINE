# Final migration audit

Final store is 1.24 / SQLite user_version=25. Engine 1.0.0 does not require store 1.25 or schema 26: release audit documents and a deterministic file manifest introduce no new persisted contract. A meaningless migration would add compatibility risk without a storage need. API, snapshot, registry and every earlier public schema stay 1.0.

`tests/release/test_migration_chain.py` invokes all 25 actual repository constructors in sequence from an empty schema-zero database. It carries a nonempty foundation feature definition from schema1 and actual source/feature/vintage rows from schema2 through every migration, comparing every prior table row, DDL definition and metadata value. This is a real migration chain, not a PRAGMA-only simulation. Reopening the final store preserves the complete rows.

An injected failing additive 24→25 migration rolls back DDL, metadata, rows and user_version with nonempty data; future schema26 rejects. Earlier phase tests independently verify migration success/rollback, immutable triggers and corrupted/future metadata. Existing fully populated native service fixtures test publication, semantic corruption, valid-hash forgery, restart and snapshot isolation.

Immutable phase creation metadata is preserved, including service_engine_version=0.25.0. Current VersionInfo reports engine1.0.0 while saved historical public versions retain0.25.0. The compatibility fix changes recorded-version replay only; no historical DDL/rows are rewritten. Back up the complete SQLite database using a consistent SQLite backup before any adoption/upgrade. Rollback means retaining the prior immutable file and original software, not editing published records.

# Public versions and capabilities

AFRE-24 exposes engine **1.0.0**, forecast service schema **1.0**, `AFRE_SERVICE_API_VERSION=1.0`, `FORECAST_SNAPSHOT_SCHEMA_VERSION=1.0`, registry schema **1.0**, shared store **1.24** and SQLite `user_version=25`. Earlier public schemas stay 1.0. Python minimum is 3.11; runtime dependencies are empty.

`VersionInfo` supplies the complete public schema catalog without internal DDL. It exposes implemented POINT, PROBABILISTIC_GAUSSIAN, PROBABILISTIC_EMPIRICAL, PROBABILISTIC_MIXTURE, QUANTILE_ONLY, CALIBRATION, MULTI_HORIZON, RANKING, EVENT_CONTEXT, REGIME_CONTEXT, UNCERTAINTY, ORTHOGONAL_CONTEXT, FUSION, HEALTH and CHALLENGE_METADATA capabilities. A requested capability absent from a particular snapshot returns UNAVAILABLE, even when the engine supports it generally.

Every snapshot and reply carries explicit version/schema identity. Selectors carry API 1.0 and reject version mismatch. API, artifact schema, engine implementation and store versions have separate meanings.

The SQLite24→25 migration adds only service tables, exact indexes, links, immutable triggers and metadata. Existing DDL, metadata and rows remain unchanged. DDL failure rolls back the complete additive transaction; future versions fail closed. AFRE-25 audits the complete schema/version chain.

## Engine 1.0 compatibility

API and public schemas remain 1.0. New publications and response envelopes identify engine 1.0.0. The closed compatibility catalog admits recorded engine 0.25.0 snapshots, audit records, version catalogs and response payloads. Saved canonical payloads deserialize unchanged. Semantic replay uses the snapshot's recorded engine, rather than relabeling old evidence. A fresh response envelope describes the serving engine; its embedded historical snapshot retains 0.25.0. Republishing under 1.0.0 creates a new identity because engine version is part of snapshot content.

Store 1.24 / SQLite25 is final. Immutable `service_engine_version=0.25.0` is migration-creation provenance. It does not advertise the currently serving engine. Earlier phase schema metadata remains unchanged. No table, migration or public schema is added just to increment a version. `service-profile.json` is the measured AFRE-24 benchmark; final measurements are recorded separately in `release-profile.json`.

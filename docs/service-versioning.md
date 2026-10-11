# Public versions and capabilities

AFRE-24 exposes engine **0.25.0**, forecast service schema **1.0**, `AFRE_SERVICE_API_VERSION=1.0`, `FORECAST_SNAPSHOT_SCHEMA_VERSION=1.0`, registry schema **1.0**, shared store **1.24** and SQLite `user_version=25`. Earlier public schemas stay 1.0. Python minimum is 3.11; runtime dependencies are empty.

`VersionInfo` supplies the complete public schema catalog without internal DDL. It exposes implemented POINT, PROBABILISTIC_GAUSSIAN, PROBABILISTIC_EMPIRICAL, PROBABILISTIC_MIXTURE, QUANTILE_ONLY, CALIBRATION, MULTI_HORIZON, RANKING, EVENT_CONTEXT, REGIME_CONTEXT, UNCERTAINTY, ORTHOGONAL_CONTEXT, FUSION, HEALTH and CHALLENGE_METADATA capabilities. A requested capability absent from a particular snapshot returns UNAVAILABLE, even when the engine supports it generally.

Every snapshot and reply carries explicit version/schema identity. Selectors carry API 1.0 and reject version mismatch. API, artifact schema, engine implementation and store versions have separate meanings.

The SQLite24→25 migration adds only service tables, exact indexes, links, immutable triggers and metadata. Existing DDL, metadata and rows remain unchanged. DDL failure rolls back the complete additive transaction; future versions fail closed. AFRE-25 audits the complete schema/version chain.

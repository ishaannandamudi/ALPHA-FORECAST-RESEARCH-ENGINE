# Immutable forecast snapshots

AFRE-24 is the final forecast service boundary. `ForecastSnapshot` pins one exact native forecast, its stable security, origin, target and horizon, producer, contributing model/source IDs, registry entries, output, universe and bounded lineage. Engine 1.0.0, API 1.0, snapshot schema 1.0 and store 1.24 are part of its identity.

`SnapshotPublisher.publish(SnapshotPublication(...))` validates and appends immutable bytes. Exact republish is idempotent. Publication version, publication time and every requested context section participate in the domain-separated SHA-256 snapshot identity. A source or context correction creates a new identity; old publications remain readable. The fingerprint is also an immutable ETag-like content identifier.

Final forecast availability includes every used forecast-time context and must not exceed the origin cutoff. Publication time is a separate later clock. Health and challenge metadata require explicit historical/evaluation requests; their own availability must precede publication, and they never change forecast values or forecast-time availability. The output retains its own identity when context changes.

Gaussian location/scale, actual empirical atoms and exact finite mixture components remain intact. Quantile-only output is a quantile set, without an invented CDF. GT/GE/LT/LE distinguish empirical ties. Calibrated marginal quantiles/probabilities and intervals remain separate from complete laws; no recalibration occurs.

The public API exposes independent horizon snapshots and explicit COMPLETE/PARTIAL/UNAVAILABLE bundles. No predictive metric establishes trading profitability. Portfolio construction, risk optimization and execution remain downstream. AFRE-25 completes Final Integration, Hardening & Research Audit.

Final engine 1.0.0 audit: [architecture](AFRE_FINAL_ARCHITECTURE.md), [API](AFRE_PUBLIC_API.md), [reproducibility](AFRE_REPRODUCIBILITY_AUDIT.md), [release evidence](AFRE_25_COMPLETION_REPORT.md). Historical public records retain their recorded versions; current API/schema1.0 and store1.24/SQLite25 remain unchanged.

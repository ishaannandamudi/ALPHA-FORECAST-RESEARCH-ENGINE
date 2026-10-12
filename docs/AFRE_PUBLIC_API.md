# Public API 1.0

Use documented imports from `afre.service`: `ForecastServiceProvider`, `AFREService`, `ForecastSnapshot`, `SnapshotQuery`, `MultiHorizonSnapshot`, `RegistryQuery`, `RegistryPage`, `ServiceReply`, `ServiceStatus`, `VersionInfo`, `canonical_json` and `deserialize`. Full exports and schemas are pinned in [the release manifest](afre-release-manifest.json). Existing export paths, fields, enum values, errors and method signatures remain unchanged.

The protocol offers get_snapshot, get_snapshot_for_origin, get_multi_horizon_snapshot, get_registry_entry, get_registry_entry_for_artifact, list_registry_entries, get_health_metadata, get_challenge_metadata, get_version_info, get_capability_catalog and get_audit. Exact IDs or a frozen PublicationCatalog plus exact producer/target/horizon/origin/universe/as-of selector govern reads. Ambiguous origin matches reject; there is no hidden latest or mutable active pointer. Pagination cursors pin the complete query and frozen catalog.

Read native point, Gaussian, empirical, finite-mixture and quantile-only representations honestly. Quantile-only output cannot answer an arbitrary full-CDF/density query; calibrated metadata pins the exact method/state without inventing a full law. Health is descriptive, challenge action MANUAL_ONLY. Unsupported capabilities are explicit; public errors sanitize storage details.

`SnapshotPublisher` and `ServiceRepository` are public administrative APIs, not consumer requirements. The illustrative external consumer in [downstream_client.py](../examples/downstream_client.py) imports only public contracts and accepts the read-only protocol. [Its contract test](../tests/release/test_external_consumer.py) exercises actual snapshots, probability laws, independent horizons, contexts, versions, capabilities, pagination, errors, corrections and canonical bytes.

See [compatibility rules](service-versioning.md). Saved 0.25.0 public records remain readable; current response headers identify 1.0.0 while historical snapshot contents preserve their original engine.

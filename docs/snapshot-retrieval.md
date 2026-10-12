# Frozen snapshot retrieval

Exact snapshot-ID retrieval replays canonical native forecast values, registry metadata and all included contexts before returning public bytes. Source corrections append new identities. A request uses one frozen SQLite read snapshot; all constituent reads see the same state.

Origin lookup requires `SnapshotQuery`: exact catalog, producer, target, horizon, origin, universe, as-of publication cutoff and API version. The only selection policy is EXACT_ONE_V1. Zero matches return NOT_FOUND; multiple compatible publications return INCOMPATIBLE, never an arbitrary latest. Catalog identity freezes membership. As-of cannot exceed the catalog cutoff, and publication must precede query as-of. Source and forecast-time context availability must precede the forecast-origin cutoff regardless of later publication.

`get_multi_horizon_snapshot` accepts bounded exact selectors sharing origin/security, universe, catalog and as-of. Actual 1h and 1d native targets remain independent. Canonical horizon-fingerprint order does not pool, interpolate, recalibrate or invent horizons. Missing matches produce explicit PARTIAL or UNAVAILABLE bundle metadata; corrupt or incompatible data fails the entire request.

Registry pagination uses a frozen catalog and a query-bound keyset cursor. Append new catalogs to expose corrections; old queries remain stable. No mutable latest/active pointer exists. See [registry](artifact-registry.md) and [errors](service-errors.md).

AFRE-25 completes final integration/hardening; portfolio, risk optimization and execution stay downstream.

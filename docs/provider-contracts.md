# Provider contracts and upstream boundary

AFRE declares Python protocols, not adapters. The foundation imports no code,
tables, filesystem paths or databases from EIE, MCE, the options engine or AME.
All APIs accept stable `InstrumentId` and integer UTC `known_as_of_ns`.

| Protocol | Neutral boundary |
| --- | --- |
| FeatureProvider | `get_features(instrument, definitions, known_as_of_ns)` → typed immutable feature tuple |
| MarketDataProvider | FeatureProvider with point-in-time price/action vintage obligations |
| EventIntelligenceProvider | `get_event_snapshot(instrument, known_as_of_ns)` → EventSnapshotRef or None |
| MarketContextProvider | FeatureProvider for regime/breadth/correlation/context |
| OptionsFeatureProvider | FeatureProvider for implied volatility/skew/surface context |
| MicrostructureFeatureProvider | FeatureProvider for order flow/spread/depth/queue context |

`EventSnapshotRef` retains stable instrument, external snapshot ID, upstream
cutoff, snapshot availability, engine version, sorted component schema versions,
and component provenance references containing IDs/source versions/byte hashes.
Availability cannot exceed its declared as-of cutoff. `validate_snapshot_as_of`
checks it against the requesting cutoff. It preserves EIE's final snapshot
boundary without assuming any internal EIE representation. Provider compatibility
is semantic at this foundation stage; no live EIE adapter or integration test is
claimed. A later adapter must map the upstream published contract and validate
instrument agreement as well as cutoff and complete component lineage.

Providers must distinguish publication, receipt, computation and revisions;
return conservative availability when ordering is uncertain; preserve historical
adjustment streams; and never reconstruct old features from current data without
proof. The caller validates every returned value at the origin through a feature
row. Interfaces cannot prove an upstream provider told the truth. Provider audits,
latency evidence, authentication and timestamp reconstruction checks remain
required before real-data research.

AFRE-1 may add audited adapters, EIE snapshot-to-feature transformations and
optional MCE/options/AME adapters, retaining availability and transformation
lineage. It must not import sibling implementations or couple to EIE SQLite.

# Provider contracts and upstream boundary

AFRE declares neutral Python protocols and offline AFRE-1 adapters. It imports no code,
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

AFRE-1 adds `SourceVintageProvider` and neutral market/EIE/MCE/options/microstructure
extensions returning typed `FeatureVintage` records. The offline market adapter
extracts only close/volume from completed immutable `MarketBar` artifacts, pinning
exact source, dataset, timestamp convention, calendar, build and adjustment.
The offline EIE adapter extracts materiality, information surprise and novelty from
`SuppliedEIEFeatures`, preserving final snapshot ID/as-of/availability, engine/schema
versions, component digests and separate uncertainty categories. Other optional
providers remain protocols only. No live networking or sibling database access exists.

Adapter clocks distinguish publication/source availability from actual AFRE receipt,
ingestion/computation and final availability. Unqualified months-later downloads
cannot serve an earlier causal origin. Explicit locally approved delivery evidence
can establish qualified historical knowability while preserving actual later receipt
and reconstruction; it does not assert literal historical ingestion by this instance.
See [delivery evidence](feature-vintages.md). This is a validation boundary, not a
certification of an external provider's clock/evidence authenticity.

# Feature contracts

AFRE-2 target-only bars, definitions, vintages, sets, datasets and audits remain in
`afre.target_engine`. They cannot enter AFRE-1 feature persistence, DAG inputs or
normalization samples. Existing recursive target-provenance exclusions and feature
clock contracts are unchanged. Future label data is usable only as label truth after
its completion/availability, never as a forecast-time input. See
[target lineage and isolation](target-lineage.md).

`FeatureDefinition` fixes name/version, semantic family, scalar value type, unit,
entity scope, lookback, publication/computed availability rule, absence handling,
transformation version and feature-definition dependencies. `FeatureSet` sorts
by content identity and rejects conflicting name/version definitions.

`FeatureValue` embeds that definition and preserves stable instrument identity,
effective/observed/available clocks, typed value, absence state, source/version,
quality and immutable lineage. Numeric features reject booleans and nonfinite
numbers. Integer, boolean and text contracts are distinct. All containers are
immutable tuples; dictionaries/lists cannot be artifact fields.

| State | Contract |
| --- | --- |
| PRESENT | A correctly typed value, including numeric zero |
| MISSING | Expected observation absent |
| NOT_APPLICABLE | Definition does not apply to the entity |
| NOT_AVAILABLE_YET | Observation expected but not usable at this origin |
| STALE | Observation withheld because it exceeded freshness policy |
| INVALID | Observation withheld because validation failed |
| UNKNOWN | Absence cause unresolved |

Every absence has `value=None`; PRESENT requires a value. INVALID quality cannot
be PRESENT. Missing policy can reject absence or preserve explicit states. No
imputation occurs. AFRE-1 vintages implement explicit freshness thresholds.
A placeholder for NOT_AVAILABLE_YET must itself be knowledge available at origin;
a future observation must not be included just to tag it as unavailable.

`FeatureLineage` retains upstream artifact IDs and byte digests, declared feature
references, dependency availability, transformation version, scalar parameters,
build context and code version. Computed definitions require dependencies and a
computation clock. Referenced definitions must agree exactly. Availability is no
earlier than the latest dependency or computation, with an explicit reconstruction
proof as the only historical computation exception.

`ForecastFeatureRow` embeds the dataset manifest and origin, requires the complete
exact definition set (absence represented explicitly), rejects duplicates, checks
historical universe membership and range, checks stable identity, and rejects any
feature after the cutoff. Target objects and target IDs cannot be used as feature
values or dependencies. A provider could falsely label a target-derived scalar as
a feature: schema separation cannot detect that lie. Adapters/DAG audits must
verify source lineage, clocks and exclusion of target-window inputs.

AFRE-0's definition/value semantics remain unchanged. AFRE-1 wraps definitions in
`RegisteredFeatureDefinition`, persists immutable `FeatureVintage` records and
projects exact selected vintages into these existing values/rows. Freshness and
query policy participate in projection identity; stale audit values remain retained
while the foundation value is withheld. Full physical delivery and reconstruction
clocks remain in the referenced vintage. See [vintages](feature-vintages.md),
[DAG computation](feature-computation-dag.md), [joins](point-in-time-joins.md) and
[supplied normalization](feature-normalization.md). Labels remain AFRE-2.

AFRE-3 eligibility consumes exact AFRE-1 security-scoped feature vintages and pins
their IDs in a frozen input build. A complete causal universe snapshot projects to
the unchanged foundation UniverseManifest at exactly one origin nanosecond. Feature
rows use that manifest fingerprint and stable instrument identity; wrong security,
universe or cutoff is rejected by the existing row contract and AFRE-3 compatibility
helper. No old feature row is rewritten. See [PIT universes](point-in-time-universes.md).

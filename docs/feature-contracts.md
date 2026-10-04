# Feature contracts

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
imputation occurs. Freshness thresholds will be implemented with AFRE-1 vintages.
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

AFRE-0 registers definition *artifacts* only. Feature vintages, retrieval indexes,
point-in-time joins, normalization, computation DAG execution and materialization
are deliberately deferred to AFRE-1.

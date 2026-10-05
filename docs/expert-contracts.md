# Expert contracts

ExpertReference identifies an independent producer with semantic expert ID, ExpertKind,
provider/version/schema, rich TargetDefinition (including Horizon), exact model/artifact
identity, output, availability, source evidence and quality. ExpertForecastBinding records
the exact forecast ID, full origin, target ID, availability, quality, scalar/expectation,
component distribution, as-of and native ResearchSample ID where applicable.

ExpertKind supports AFRE_POINT, AFRE_PROBABILISTIC, AFRE_EVENT, AFRE_REGIME,
EXTERNAL_MICROSTRUCTURE, EXTERNAL_CONTEXT, EXTERNAL_OPTIONS and EXTERNAL_GENERIC.
POINT and raw PROBABILISTIC output are supported. CALIBRATED_PROBABILISTIC is a typed
reserved boundary and fails explicitly. Native producer availability and exact model target
are verified against existing artifacts; event/regime observation IDs retain exact sample identity.

ExpertSet canonicalizes by producer fingerprint. Duplicate semantic IDs and aliases of the
same kind/model/output are rejected. All experts must have identical rich target/horizon
and output semantics. Different durations, return transforms, residual/raw definitions and
benchmarks cannot be pooled. A global fixed/learned gate can apply to several securities;
security-specific gating has no separate supported contract. Each horizon has its own set/gate.
The actual1h/1d example reuses AFRE-8 independent horizon architecture.

Quality is VALID, MISSING, STALE, DEGRADED, UNSUPPORTED or INVALID. Missing inputs retain
None; provider validity is distinct from as-of freshness and final availability. Binding to
an available artifact does not imply it was available at a particular historical origin.
Exact source/evidence hashes verify structure, never provider authenticity.

All contracts are frozen typed data with canonical serialization and domain-separated hashes.
Completed earlier schemas remain1.0. New contracts use mixture schema1.0 and safe data only.

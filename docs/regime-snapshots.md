# Regime snapshots and matching

RegimeProviderReference pins provider/version/schema, taxonomy ID/version, optional
method and exact SourceReference. RegimeTaxonomy pins ordered state IDs, matching
labels/descriptions, category and dimensionality. Names are provider data, with no
provider-specific behavior. Corrections/version changes create new identities.

RegimeSnapshot separates as-of/observation, upstream publication, source availability,
actual AFRE receipt, ingestion, computation and final availability. **As-of time !=
availability.** Publication10:00, receipt10:02 is unusable at10:01. A later download
of an old archive retains its actual later clocks. Historically knowable does not mean
historically observed by AFRE. Qualified reconstruction reuses AFRE-1 exact source/entity
binding, recorded historical delivery/computation and locally approved attestors; actual
later reconstruction clocks remain intact. Provider timestamps alone cannot backdate.
AFRE validates the evidence's consistency, not the authenticity of external claims.

FILTERED states may condition causal forecasts. SMOOTHED and EX_POST can be stored as
research data but are excluded from causal matching. VALID is required; STALE, MISSING,
DEGRADED, UNSUPPORTED and INVALID preserve typed exclusions. Maximum age is elapsed
origin minus as-of, inclusive at the declared limit; receipt/availability must also
be <= origin cutoff. Same-time evidence is accepted.

LATEST_AVAILABLE sorts descending(final availability, as-of) and fails equal-clock
revision ambiguity. EXACT_AS_OF requires exactly one snapshot at the origin;
FAIL_ON_MULTIPLE requires at most one admissible snapshot. No hidden fingerprint
winner. Every request pins its explicit candidate set and PIT mappings. Indexed
history queries return bounded causal FILTERED/VALID records; callers still declare
staleness, subject, attestor and selection policy. They do not silently select revisions.

GLOBAL broadcasts to eligible samples; MARKET pins exact universe definition;
SECURITY pins stable security; SECTOR uses exact AFRE-9 membership/provider/taxonomy,
valid-at-origin and known-by-cutoff evidence. Conflicting active group mappings fail.
Later sector corrections cannot replace old frozen mappings. VENUE/CUSTOM adapters
are not implemented. All bindings retain the complete AFRE ForecastOrigin.

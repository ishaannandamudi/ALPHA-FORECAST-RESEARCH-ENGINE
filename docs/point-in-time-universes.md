# Point-in-time universe snapshots

`UniverseDefinition` pins semantic name/version, neutral membership source and
source category, separate EligibilityPolicy, supplied exchange calendar and trusted
builder version. `UniverseEngine.universe_as_of(definition,valid_at,known_as_of)`
freezes an exact UniverseInputBuild and assembles one consistent SQLite read snapshot.
The explicit input_build_id option replays a previously frozen build. Actual
constructed_ns is caller-supplied; no wall-clock time enters identity.

UniverseInputBuild pins sorted exact universe evidence and AFRE-1 market vintage
IDs admitted by the cutoff, actual construction and QueryPolicy. Default freezing
covers the repository's admitted records across sources; it is deliberately coarse.
It does not authenticate timestamps or silently ignore unapproved reconstruction.
Row/byte bounds prevent unbounded manifests. Source providers are data-only protocols
with immutable offline implementations; no network providers are installed.

UniverseSnapshot pins definition, valid/known/construction times, input build,
coverage, sorted stable-security membership and eligibility grids, exact evidence
references, builder/engine versions and content identity. COMPLETE requires explicit
complete source coverage with no unknown/conflicted/not-yet-available decisions.
Incomplete coverage remains KNOWN_GAPS or UNKNOWN. Uncertain securities remain in
the result grid rather than silently disappearing.

`persist_snapshot` validates deterministic replay against exact frozen inputs before
writing members, eligibility and snapshot in one transaction. An old build never
consults newly inserted sources, including backdated corrections. New source builds
and revised snapshots have distinct identities. Bounded `security_history`,
`universe_history`, `snapshot_history`, `resolve_security` and `audit_security`
expose evidence; query overflow fails instead of truncating.

`to_universe_manifest(snapshot)` projects a nonempty COMPLETE causal snapshot into
the unchanged foundation UniverseManifest. Only ELIGIBLE stable instruments enter
that manifest. Its validity is exactly [T,T+1 nanosecond), source is snapshot
fingerprint and knowledge is the pinned cutoff. It cannot infer eligibility at
another instant or accept known_as_of>T. `validate_snapshot_origin` checks exact
manifest, stable security, origin and cutoff. Rich snapshots retain excluded,
unknown and conflicted results for audit.

The manifest fingerprint binds downstream feature/target dataset identity to exact
membership and eligibility. Existing contracts remain unchanged. AFRE-4 composes
these snapshots into PIT samples, folds, embargo/purge and contamination audits in
a separate [research dataset package](research-datasets.md). It preserves excluded
and unresolved snapshot cells and never substitutes the current universe. See [membership](universe-membership-vintages.md), [eligibility](security-eligibility.md),
[identity](security-identity.md) and [reproducibility](research-reproducibility.md).

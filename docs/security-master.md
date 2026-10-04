# Point-in-time security master

AFRE-3 uses `afre.universe`, universe schema 1.0, engine 0.4.0 and additive SQLite
store 1.3/user_version=4. `UniverseRepository` provides shared access to the existing
foundation, feature and target artifacts. Previous schemas remain 1.0.

`IssuerRecord` and `SecurityRecord` have distinct stable identities, explicit
jurisdiction/type/share class/asset class/currency/country and source evidence.
Their immutable classification does not change implicitly after a merger. One
issuer can issue many securities; an ADR, preferred or warrant remains a distinct
security. No fuzzy name matching or inferred identity continuity exists.

`ListingId` identifies a listing separately. `ListingRecord` versions venue,
currency, primary status, calendar and [start,end) validity/knowledge. A security
can have several listings; a definition selects a primary listing or an explicit
listing ID. Multiple admissible choices are CONFLICTED. New venue/primary evidence
must supply its historical interval; current metadata cannot amend older rows.

`SymbolAssignment`, `ExternalIdentifier`, `SecurityRelationship`, `LifecycleEvent`
and `TradabilityRecord` retain independent temporal source evidence. Identifier
kinds include CUSIP, ISIN, FIGI, CIK, SEDOL and provider ID. Authoritative overlapping
identifier assignments produce a conflict during eligibility, without merging
securities. Source authority is supplied, not independently authenticated.

All records use `UniverseEvidence`: independent valid and knowledge intervals,
neutral source reference/version, physical and upstream clocks and optional explicit
predecessor. A compatible later predecessor chain supersedes the old assertion,
including corrected validity, only in a build containing that later knowledge.
Identity master conflicts fail rather than overwrite. Merger/spinoff/successor
relationships connect original identities without rewriting their histories.

Immutable tables/indexes reject UPDATE, DELETE and replacement. Deep audit checks
payload/hash/index/source integrity and recalculates snapshots against their frozen
inputs. Histories and lineage enforce row, node, depth and byte bounds.
See [identity](security-identity.md), [membership](universe-membership-vintages.md)
and [eligibility](security-eligibility.md).

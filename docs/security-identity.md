# Stable security, issuer and listing identity

`StableSecurityId(namespace,value)`, `StableIssuerId` and `ListingId` are typed,
opaque identities supplied by a persistent authority. Their canonical domain hashes
are distinct. Security and issuer IDs cannot denote the same foundation instrument.
`StableSecurityId.instrument` is the exact existing AFRE-0 InstrumentId projection.
No ticker, company name, exchange display name or fuzzy heuristic establishes identity.

`resolve_security(symbol,venue,valid_at,known_as_of)` considers only symbols and
listing evidence admitted to the exact frozen build and active in both intervals.
A missing mapping returns no security/listing. Several admissible security/listing
pairs return explicit conflict. Venue is mandatory. A ticker change can preserve a
stable security when evidence says so; reused ABC after an unrelated IPO resolves
to a different security. Both old histories remain stored.

Dual listings remain distinct even when linked to one security or issuer. Primary
status is historical. Eligibility can pin `selected_listing`; it never silently
chooses among several admissible listings. ADR, SPAC, underlying common stock and
post-merger identities are not collapsed by their names or relationships.

Membership APIs require a typed stable security, rejecting a ticker string.
Feature and target rows continue to join on full stable instrument, forecast origin,
cutoff, build context and universe fingerprint. A symbol change cannot alter that
key. The compatibility tests exercise actual AFRE-1 feature rows and AFRE-2 labels
with a projected universe snapshot and reject wrong securities/universes.

Identity authenticity remains a provider responsibility. Temporal contracts and
hashes prove consistent declarations, not that a supplied opaque ID denotes a real
security. See [security master](security-master.md) and
[survivorship protection](survivorship-bias-controls.md).

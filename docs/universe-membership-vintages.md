# Bitemporal membership vintages

`UniverseMembershipVintage` pins universe definition, stable security, INCLUDED,
EXCLUDED, UNKNOWN or CONFLICTED, and immutable `UniverseEvidence`. Validity and
knowledge are half-open [start,end) intervals. `known_as_of` admits only evidence
whose final availability is at or before the cutoff and whose knowledge interval
has not ended. Valid membership must also contain `valid_at`.

The six clocks are upstream publication, upstream source availability, AFRE receipt,
ingestion, computation and final availability. Upstream clocks may be absent where
no evidence exists. Live/unqualified final availability cannot precede actual
computation or receipt. Publication at 10:00 with receipt at 10:02 cannot inform a
10:01 query. An archive downloaded months later remains later knowledge.

Qualified historical reconstruction reuses AFRE-1 QualifiedHistoricalDelivery,
bound to exact source/entity and a locally approved attestor. It can establish a
historical processing bound while actual later receipt/ingestion/computation remain
recorded. `constructed_ns` must cover that physical reconstruction. Publication
alone, or an unapproved self-attestation, cannot authorize backdating.

`membership_as_of(universe,security,valid_at,known_as_of)` returns a typed selection
with exact input build, used records, future records and coverage identity. An
announcement before an inclusion's effective start enters `future_record_ids`;
it does not confer current membership. A late correction creates another vintage.
Compatible predecessors supersede old assertions in later builds; highest final
availability determines competing active assertions. Contradictory equal-precedence
states are CONFLICTED. Identical independent assertions retain all evidence.

`ConstituentCoverage` supplies a closed candidate set, temporal evidence and explicit
COMPLETE/KNOWN_GAPS/UNKNOWN guarantee. Missing membership means UNKNOWN unless the
source explicitly guarantees complete coverage, in which case absence is EXCLUDED.
Rule-based/exchange-listing definitions use their supplied coverage candidate set
before separate eligibility checks. INDEX_MEMBERSHIP and ETF_CONSTITUENT remain
separate source categories. CURRENT_CONSTITUENTS definitions are rejected.

Membership history is indexed and bounded. Immutable frozen builds preserve old
selections even when a newly inserted correction claims an earlier cutoff.
See [snapshots](point-in-time-universes.md) and [survivorship](survivorship-bias-controls.md).

# Temporal semantics

AFRE-2 adds exact (T,T+H] target windows and a separate reference-price policy.
Foundation TargetSpec's first-after-origin convention remains unchanged. Every
label retains nominal and actual endpoints, completion and six availability clocks.
Final label availability follows endpoint/path/action/benchmark delivery and actual
computation; publication alone cannot backdate a reconstructed label. Equality at
training cutoff is eligible for verified complete labels. Exact supplied session
grids distinguish elapsed/session/bar horizons and exclude declared market closures.
See [target windows](target-window-semantics.md) and
[target availability](target-availability.md).

Time is a UTC integer nanosecond in [0, 2⁶³−1]. Booleans, floating timestamps,
negative values and naive datetimes are rejected. `datetime_to_ns` uses integer
arithmetic; `ns_to_datetime` rejects nanoseconds that Python's microsecond datetime
would truncate. Datetime is an edge conversion, not an internal clock.

An immutable `ForecastOrigin` fixes stable security identity, origin timestamp,
market-session identity, build context, historical universe fingerprint and
availability cutoff. The cutoff is at or before origin. Feature admissibility is
`available_ns <= availability_cutoff_ns <= timestamp_ns`. Equality is deliberate:
a source must establish availability at that instant, including delivery and
processing latency. If clock resolution/order is uncertain, the provider must
apply a conservative latency; AFRE cannot infer it from a published date.

| Clock | Meaning | Example |
| --- | --- | --- |
| effective | Time the fact pertains to | End of Q1 |
| observed | Time the source observed/published the fact | Earnings release |
| available | Earliest time the research process could use it | Release plus delivery/processing |
| computation available | Time a derived result became usable | Completion of a transformation |

Effective time can follow observation for scheduled facts. Observation cannot
follow availability. A derived value cannot precede any dependency or its
computation. An explicit `ReconstructionProof` records original reproducible
computation availability, later reconstruction time and evidence provenance. It
can substitute the historical computation clock, never a future input clock.
Proof authenticity and timestamp accuracy are provider responsibilities.

`TimeRange` is **[start, end)** for origin ranges, memberships and symbol mappings.
A foundation target's `window` uses those two boundary values but its `TargetSpec` explicitly
assigns price-selection semantics **(origin, endpoint]**. No price at origin is
selected as the entry; the first admissible observation strictly after origin and
last admissible observation at/before endpoint define the eventual target.

Elapsed horizons use a positive nanosecond duration. A UTC day is 86,400 seconds.
Trading-session horizons use a positive session count and versioned calendar ID.
Bar horizons additionally require a bar-definition ID. Calendar DST, holidays,
halts, partial sessions and endpoint price admissibility are resolved explicitly
by AFRE-2; foundation rows require the supplied resolver reference.
A target row checks exact elapsed endpoint, or requires resolver evidence for a
session/bar endpoint; it never treats a session as an elapsed day.

Target availability must be at or after completion. Training eligibility requires
an origin strictly before fit cutoff, window completion at/before cutoff, data
availability at/before cutoff, a finite value, and verified quality. The pure
`validate_training_pair` also checks matching origins, declared target and declared
market source. Future labels fail even when the feature row itself is admissible.

Split metadata requires disjoint ordered train/validation/test origin ranges,
explicit fit/evaluation cutoffs, mandatory future interval purging, and embargo
spacing. Purging is a recorded requirement in AFRE-0, not an implemented splitter.
AFRE-4 implements exact interval purging and elapsed/session/bar embargo, and fits
simple normalization using only TRAIN data and labels known at the training cutoff.
Feature selection remains deferred. See [fold semantics](leakage-safe-splitting.md).

## AFRE-1 physical delivery and reconstruction

`AvailabilityEvidence` preserves six separate clocks: upstream publication and
source availability (optional evidence), actual AFRE receipt, ingestion,
computation/reconstruction, and final feature availability. For live and unqualified
reconstructed records, final >= computation >= ingestion >= receipt. Publication
at 10:00 with receipt at 10:02 cannot serve 10:01. An archive downloaded months
later does not inherit its earlier publication time as AFRE availability.

Only explicit qualified historical delivery bound to exact source/entity and a
locally approved attestor can substitute historical processing availability.
Actual later receipt/ingestion/computation remain recorded; historical channel
knowability is separate from literal observation by this system. This AFRE-1
contract strengthens adapter evidence while preserving AFRE-0 `ReconstructionProof`
and `FeatureValue.observed_ns` semantics. See [feature vintages](feature-vintages.md).

Validity and knowledge remain independent: interval features use [effective, end),
rolling computation uses effective observations in (T-lookback, T] with each input
available by cutoff, and explicit KNOWN_FACT features may represent a scheduled
future-effective fact. Corrections never overwrite vintages; snapshot joins and
frozen materializations preserve exact selections across concurrent/later inserts.

AFRE-3 applies independent [start,end) valid and knowledge intervals to listings,
symbols, identifiers, relationships, lifecycle and membership. Six delivery clocks
reuse AFRE-1 AvailabilityEvidence. An announcement of future inclusion is retained
as future_record_ids and does not confer current membership. Membership and
eligibility are different decisions. Market eligibility admits only effective time
<= T and final availability <= min(T,known_as_of), using (T-lookback,T] for liquidity.
A later reconstruction keeps its physical receipt/ingestion/computation clocks;
qualified historical evidence requires an explicitly approved attestor. Revised
history with knowledge>T cannot serve a historical forecast. See
[membership vintages](universe-membership-vintages.md).

AFRE-4 information intervals record endpoint inclusion explicitly: target intervals
are (actual origin close, actual endpoint close], while full information intervals
include the earliest declared feature lookback and bounded dependency/bar lineage. Prepared transformations require a
state available at the application time; retrospective training preprocessing does
not backdate a learned statistic into the raw historical feature.

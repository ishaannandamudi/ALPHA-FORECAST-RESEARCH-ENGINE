# Temporal semantics

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
A target's `window` uses those two boundary values but its `TargetSpec` explicitly
assigns price-selection semantics **(origin, endpoint]**. No price at origin is
selected as the entry; the first admissible observation strictly after origin and
last admissible observation at/before endpoint define the eventual target.

Elapsed horizons use a positive nanosecond duration. A UTC day is 86,400 seconds.
Trading-session horizons use a positive session count and versioned calendar ID.
Bar horizons additionally require a bar-definition ID. Calendar DST, holidays,
halts, partial sessions and endpoint price admissibility belong to future resolvers.
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
AFRE-4 will remove rows whose label intervals overlap held-out windows and fit all
normalization/selection using only training data and available completed labels.

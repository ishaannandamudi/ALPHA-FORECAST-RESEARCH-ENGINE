# Event time and causal availability

Occurrence != publication != receipt != availability. The occurrence is optional
and describes the event, never automatic permission to use its content. Reuse
AFRE-1 AvailabilityEvidence: upstream publication/source availability, actual AFRE
receipt, ingestion, computation and final availability. Live final availability
cannot precede actual receipt or processing. Same-time final availability==cutoff
is accepted by the existing <= rule; cutoff cannot exceed forecast origin.

Publication10:00 / receipt10:02 is unusable at10:01. An archive published10:00 and
downloaded months later is unavailable historically unless an explicit qualified
historical-delivery contract proves the earlier reproducible information state.
Such evidence binds the exact source and security, pins historical delivery clocks,
qualification/version/channel/attestor, and must use an approved attestor in the
spec. Actual later AFRE receipt/ingestion/computation remains preserved. Historically
knowable, historically observed by AFRE and reconstructed later stay distinguishable.
A qualified contract is evidence supplied by the provider, not authenticated truth.

Scheduled pre-event information may be available before occurrence. Event content
received later remains excluded. Every attribute and reaction has independent
clocks; surprise requires both actual and exact expectation. Physical forecast
application cannot backdate its own computation. A later correction creates a
new reference, observation and forecast; frozen old artifacts keep their exact
vintages. [Windows](event-windows.md) specify the relation separately from availability.

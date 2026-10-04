# Label availability and historical reconstruction

Label time differs from forecast time. The label for T can use future observations
only inside the target subsystem. A 10:00 origin, 11:00 endpoint and receipt at
11:00:02 cannot produce a usable label at 11:00:01. Equality at the training cutoff
is eligible once the complete label is verified and all processing is complete.

`AvailabilityEvidence` preserves, where upstream evidence exists:

1. upstream publication;
2. upstream source availability;
3. actual AFRE observed/received;
4. actual AFRE ingestion;
5. actual AFRE computation;
6. final availability.

These are independently serialized clocks, not an alias for provider time.
Without qualified historical delivery, final source availability is at least actual
AFRE computation, which follows ingestion and receipt. A bar cannot be available
before its period completes. A source build admits only bar/action/benchmark/calendar
evidence available by its explicit cutoff. Publication is not proof of AFRE receipt.

A target additionally records label completion and its own physical creation clocks.
Completion waits for the window and every required input's availability and physical
processing; absent outcomes do not claim completed labels. Its
availability cannot precede nominal/actual endpoint completion, any used bar/path,
supplied benchmark, calendar or required action-stream availability. Its actual
computation cannot precede actual source reconstruction computation or source cutoff.
Action policy knowledge also must be admitted by that cutoff. Supplied clocks are
validated, not replaced with implicit wall-clock reads or automatically repaired.

An archive downloaded months later remains a later reconstruction. The existing
qualified historical-delivery contract may establish that an exact source/entity
was historically delivered, retaining actual later receipt/ingestion/computation.
AFRE-2 can use that qualified source in a reconstructed dataset, but **does not
backdate target computation**. A new label generated today is available today even
if its source was historically knowable. Target outputs, benchmarks, action streams
and calendars reject historical backdating until a separate qualified target-computation
contract is implemented. This deliberately distinguishes historical knowability,
literal observation by this system, and later reconstruction. AFRE-1's local
attestor approval rule and feature delivery semantics remain unchanged.

`target_known_by_cutoff` is pure. It admits only PRESENT, VERIFIED, complete values,
origin strictly before cutoff, nominal end/completion/final availability ≤ cutoff,
and no partial path. Indexed `targets_known_by` applies these predicates and exact
origin/set/instrument/dataset filters. A fully completed but undelivered endpoint
remains ineligible. Reconstructed later labels cannot enter an earlier training fit.
Revision and reconstruction flags are independently visible; neither is evidence
that prediction metrics imply trading profitability.

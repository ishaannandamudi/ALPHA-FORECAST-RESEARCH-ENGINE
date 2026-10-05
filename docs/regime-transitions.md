# Causal regime transitions

RegimeTransition pins exact consecutive snapshots in the **explicit supplied causal
history**, taxonomy/subject, full previous/current membership, current as-of transition
time, maximum input availability, change flag and total-variation mass change
0.5*sum(abs(previous weight-current weight)). B→B is a stable adjacency. Soft vectors
remain soft; no invented hard switch. A membership-kind change is explicit even if
its one-hot vector equals a soft vector. Numerical tolerance metadata is not a switch.

Matching excludes unavailable/future/retrospective/stale histories. The current
state must be available before a transition is usable. Equal-as-of histories fail
ambiguity. The versioned history policy retains the latest causal delivery for each
as-of; equal-clock revision ambiguity fails. The transition chain contains only snapshots up through the selected
state and is revalidated on replay. This does not prove provider history completeness.

Elapsed observed state duration is origin minus the most recent known changed-state
as-of, or minus the first supplied snapshot when no change is seen. It is a **lower
bound on observed elapsed persistence**, not total completed regime duration. Future
switches and future completed durations are never included. A single supplied snapshot
has unknown transition status even though its observed elapsed duration is recorded.

Cohorts are transition (known switch at origin), recent (switch within fixed inclusive
recent window), stable (causal adjacencies but no recent switch) or unknown (no chain).
Metrics have minimum counts. Timing describes provider state evidence rather than
causal attribution of forecast errors to the switch.

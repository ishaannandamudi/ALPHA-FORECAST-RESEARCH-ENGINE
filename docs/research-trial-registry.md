# Research trial registry

TrialSpecification is a planned opportunity; ResearchTrial is its one immutable
completion. Separate IDs avoid inventing completed outcomes during target-free planning.
Exactly one completion per plan is enforced both semantically and by a unique SQLite
index. Identical republish is idempotent; reevaluation requires a new explicit attempt.

Identity includes hypothesis/family context, native phase and source artifact, exact
left/right source streams, dataset/fold/sample grid, preprocessing/model references,
caller choices, environment memberships, cost scenario, declaration/adaptivity and known
parent trial IDs. Same signal with another horizon, threshold, preprocessing choice,
environment or cost scenario remains a separate opportunity.

TrialRegistrySnapshot pins all registered plans/families, all visible completions and
chronology, caller selection events and native TEST seals by completion cutoff. A new
snapshot cannot select an outcome-dependent subset. Earlier snapshots replay only their
pinned membership and do not expand when a same-clock writer appends another attempt.
Native unregistered assessments remain visible as untracked history; AFRE cannot infer
research that was never registered.

Plans and hypotheses register under the target-free guard, including cached reads.
Adaptive parent availability is checked from bounded registry metadata without loading
TargetVintage. Completed evidence may read exact later truth; no latest correction is
silently substituted. Family assignment and rejection outputs are immutable.

Store1.19/SQLite20 adds four tables, nine indexes and ten immutable triggers. Transactional
19→20 migration adds three metadata keys and preserves every prior table, row, DDL and
metadata value. Future versions, layout drift, hashes, raw payload bounds, projections,
links and semantically forged results fail closed. Audit follows exact native TRAIN fit
witnesses, sources, costs, environments, truth and seals under node/depth/byte bounds.

Default ceilings: 2000 plans/trials per family and snapshot, hypotheses and samples,
16 distinct metrics, 2000 TEST history entries, 256 selection events and snapshots,
20000 artifacts per type, 8 MiB payload/audit bytes, 100000 lineage nodes and depth64.
Callers may lower them. Whole historical TEST enumeration is bounded, including seals
later than the requested cutoff; it fails rather than silently truncating history.

See [controls](multiple-testing-controls.md) and [TEST reuse](test-reuse.md).

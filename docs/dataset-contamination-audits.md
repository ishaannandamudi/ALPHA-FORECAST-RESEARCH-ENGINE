# Dataset and fold contamination audits

Each cell receives SampleContaminationAudit with its exact sample/dataset, state,
direct upstream evidence and checks. Optional `audit_sample(...,fold_id)` additionally
verifies its persisted partition, purge/embargo boundary and TRAIN target cutoff.
Exclusions retain their states instead of claiming successful causal admission.

`audit_dataset` checks the exact origin/security/target grid, source/calendar/adjustment
contract, historical snapshot/eligibility, full stable origin, exact AFRE-1 feature set,
cutoff admissibility and frozen feature/vintage selection, exact AFRE-2 target evidence,
explicit missing states, construction clocks, canonical ordering and completeness.
It expands bounded upstream lineage and replays label and universe evidence against
frozen input builds. It never reruns a latest live feature selection.

`audit_fold` additionally recomputes disjoint partitions, scoped purge and all declared
embargo fences, label-known-by-cutoff admission, parent TRAIN boundary and train-only
preprocessing statistics. ContaminationAudit stores counts, exclusion identities,
lineage and named checks. A persisted audit pins its preprocessing-state IDs so a later
additional fit cannot mutate old audit evidence. None of these checks asserts trading
profitability or proves that an opaque provider scalar was truthfully described.

DatasetBounds limits origins, securities, samples, features, targets, folds, interval
comparisons, audit nodes, lineage depth and serialized bytes. Overflow fails explicitly;
there is no silent truncation. Default artifact/export budget is 8 MiB, with the existing
closed JSON decoder's 16 MiB/64-level ceiling. Caches are transaction-scoped and clear
on exit. Large exports and lineage expansions must use a caller-declared bounded
workload; a streaming matrix/service API is deferred.

Startup compares exact DDL/index/trigger SQL, all historical/new metadata and integer
version. Payload reads verify family/schema/hash and relational indexes, including
ordered dataset/split memberships. Whole-store audit additionally rejects orphan
indexes and recomputes sample/fold/state/audit semantics. Tests tamper payloads,
indexes, metadata and triggers, inject migration failure, insert a backdated correction
from another connection while a read is pinned, and verify deterministic restart.

The offline [profile](../benchmarks/research_datasets.py) measures an actual synthetic
multi-security/multi-horizon pipeline separately from a 100,000-interval indexed purge
workload, using an explicit 16 MiB serialized/lineage budget for the profile.
It reports assembly, PIT joins, persistence, split generation, embargo,
preprocessing, partition retrieval, contamination audit, restart and disk bytes with
cProfile hotspots. These are local observations, not a production SLA. Existing AFRE-1
join artifacts embed their foundation universe; large universes can therefore duplicate
provenance and cost more than the indexed purge itself. The profile does not claim
end-to-end scaling to its independent interval count.

Historical delivery attestors and provider clocks require external qualification.
The semantic TEST seal records access/reuse but is not authentication. Multiple testing,
model selection, ensembles, transaction-cost-aware research and forecast serving remain
separate later phases; portfolio/risk optimization and execution stay downstream projects.

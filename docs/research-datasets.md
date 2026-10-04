# Research datasets (AFRE-4)

`afre.research_datasets` joins existing AFRE-1 point-in-time features, AFRE-2
label vintages and AFRE-3 frozen universe snapshots. Engine 0.5.0 adds dataset
schema 1.0 and shared SQLite store 1.4/user_version=5. Earlier contract schemas,
artifact payloads and creation metadata stay unchanged. Runtime dependencies are empty.

`ResearchDatasetDefinition` declares the exact FeatureSetManifest, TargetSetManifest,
source allowlist, calendar identities, feature and target adjustments, missing policy,
query policy and optional typed historical group bindings. `ResearchOriginRequest`
pins a persisted snapshot, session/build context, target dataset and requested stable
securities; an empty security tuple means that snapshot's complete evidence grid.
There is one request per snapshot and one cell per stable security/origin/target.
The current universe and ticker text never select samples.

The builder invokes AFRE-1 `FeatureStore.point_in_time_join` directly inside one
outer SQLite read snapshot. Its private scoped repository adapter reuses this
snapshot for the upstream join; ordinary nested reads still fail. Exact selections
are frozen before publication in one atomic writer transaction. Concurrent later
inserts, including backdated corrections, cannot enter the in-progress build.
Physical construction must follow all pinned feature, target and snapshot construction.

`ResearchSelection` retains snapshot/eligibility, security, origin/cutoff, exact join
and historical purge groups. Failed eligibility retains a selection without a
foundation forecast origin or feature row: that foundation contract requires an
eligible member. Incomplete snapshots cannot project to a causal foundation universe.
The failed cells stay visible. Ambiguous AFRE-1 vintages fail the build explicitly;
AFRE-4 does not invent a tie-breaking feature selector.

`ResearchInputBuild` pins exact selection IDs and processing/construction cutoffs.
`ResearchSample` pins this build, selection, security/origin/universe, feature set,
join and selected feature vintages, exact target definition/vintage, intervals,
label availability, state and drop trace. Target values are copied from the pinned
AFRE-2 vintage; AFRE-4 computes no labels. Target dataset origins must match the
snapshot's foundation projection exactly. Different origins may use separate
immutable target datasets because each snapshot has a different universe identity.

| State | Meaning |
| --- | --- |
| AVAILABLE | Causal features and verified present target available by dataset processing cutoff |
| FEATURE_INCOMPLETE | At least one absent, stale or unverified feature |
| TARGET_NOT_AVAILABLE_YET | Pinned truth absent/pending or unavailable by processing cutoff |
| TARGET_MISSING | Explicit missing/invalid target observation |
| INELIGIBLE | Historical membership or eligibility excludes the security |
| UNIVERSE_UNKNOWN | Causal membership/eligibility or source completeness unresolved |
| CONFLICTED | Conflicted historical universe decision |
| INVALID | Unverified target or invalid research evidence |

State precedence preserves failed universe decisions first, then incomplete features,
then target status; all exact feature/label evidence remains inspectable. Dataset
COMPLETE means every cell AVAILABLE, KNOWN_GAPS means explicit failed cells, UNKNOWN
means unresolved universe decisions. These are construction states; each fold checks
label readiness again at its own training cutoff. Missing, pending or unverified
target truth does not remove otherwise causal VALIDATION/TEST origin membership.

FAIL rejects any incomplete cell. DROP_SAMPLE marks cells as dropped but preserves
their identities and exclusion audit. PRESERVE_MISSING retains absent values and
permits otherwise causal cells with ready labels into TRAIN. Train-only fitting
skips missing feature observations explicitly. IMPUTE_TRAIN_ONLY is a reserved enum
and fails until implemented; no implicit global or future-value imputation occurs.

`DatasetColumnManifest` sorts explicit typed feature/target/identifier/metadata
columns. A target-definition ID cannot enter a feature column. `export_rows` returns
canonical-key JSON with scalar values, roles, types, missing states and sample IDs,
without pandas. Historical issuer/sector/market groups are metadata columns. Labels
and their missing/quality evidence are exposed only when their final availability
is at or before the explicit export cutoff; known missing truth remains missing.
The separate target-known-by-cutoff flag indicates verified training readiness.
Optional preprocessing records its state and application time separately from raw
PIT features and requires both state and input feature availability by that time.
Dataset export is an explicit research inspection API, not an access
control system; use the separate fold APIs for training and held-out evaluation.

Every materialized cell also receives an immutable SampleContaminationAudit,
including exclusions. `audit_sample` can additionally pin fold admission and label
readiness. Dataset and fold audits expand the deeper shared lineage.

`DatasetRepository` supplies shared access to all five layers. Six new immutable
artifact/index tables support dataset/sample order, security/origin, target interval,
label availability, fold, split and partition retrieval. UPDATE, DELETE and replacement
inserts fail; exact insertion is validated and idempotent. Migration 4→5 validates the
prior layout and adds DDL/metadata transactionally; injected failure rolls back and
unknown future versions fail closed. Earlier repository interfaces remain strict.

Use `DatasetEngine.build_dataset`, `dataset_samples`, `build_split`, `folds`,
`partition_samples`, `training_samples_for_fold`, `validation_samples_for_fold`,
`test_samples_for_fold`, `fit_preprocessing`, `audit_sample`, `audit_dataset`, `audit_fold` and
`export_rows`. Run the [offline demo](../examples/research_dataset_demo.py) and
[profile](../benchmarks/research_datasets.py). See [splitting](leakage-safe-splitting.md),
[preprocessing](fold-local-preprocessing.md) and [audits](dataset-contamination-audits.md).

AFRE-5 consumes these exact TRAIN partitions and pinned preprocessing states in a
separate [statistical model layer](statistical-baselines.md). One target definition
is modeled at a time; held-out responses never enter the design matrix. Later target
revisions require a new dataset/spec/fit identity. The dataset schema stays 1.0.

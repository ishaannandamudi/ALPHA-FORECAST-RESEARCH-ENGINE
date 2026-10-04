# Research reproducibility

Engine: **0.3.0**. Foundation, feature-store and target schemas: **1.0**.
SQLite target store: **1.2**, represented by `PRAGMA user_version=3`, extending
feature-store schema 1.1/user_version=2 additively.
The original `ArtifactStore` keeps its strict 1.0/user_version=1 interface.
Processing, model, label, calendar, source and selection
implementation versions are recorded separately. No wall-clock time or implicit
randomness enters an artifact. Every stochastic model spec records a uint64 seed;
experiment seed must agree. Names are human labels and participate in content
identity; fingerprints are the reproducible artifact IDs.

Identity is domain-separated SHA-256 over a canonical JSON envelope. The prefix
is `AFRE\0{schema}\0{domain}\0`; the external ID is
`afre.{domain}:{schema}:{lowercase digest}`. Envelopes have exact type/enum tags,
schema version, explicit field values, sorted keys and compact UTF-8 JSON. Finite
floats are required, signed zero is normalized, and int/float representations stay
distinct. Python hash randomization does not enter identities. Unicode is preserved
as supplied; no silent normalization is applied. Parameter tuples and semantic
sets sort deterministically and reject duplicates.

A dataset commits to universe, feature set, targets, source artifact IDs, origin
range, calendar, adjustment/missing policies, processing version and engine version.
A model commits to features, target/horizon, hyperparameters, training policy, seed
and implementation. An experiment embeds the dataset/model, split/cutoff policy,
evaluation, research costs, seed and code version and checks agreement. Model
metadata records dataset/fit cutoff, byte digest, safe format and metric references.
Completed/failed/planned results are separate immutable artifacts; failure needs a
reason and completion needs a model artifact reference and completed evaluation.
`validate_result_model` checks resolved model reference, spec, dataset, fit cutoff
and availability agreement. Reference existence and model-byte authenticity remain
caller responsibilities; AFRE-0 does not load model bytes or execute a result.

SQLite's seven artifact tables plus metadata form an append-only registry.
Writes require an explicit `transaction()`; exception handling rolls back the
entire batch. Repeat insertion is idempotent only after validating the existing
artifact. UPDATE, DELETE and duplicate-insert triggers protect artifacts and
metadata, including against replacement inserts. Migration 0→1 executes atomically
and only on an empty database. Startup compares full fixed
schema and metadata, rejecting unknown versions or altered protections.

Replay reconstructs only statically registered contract classes and re-runs their
invariants. It checks exact canonical payload, class/schema indexes and content
fingerprint. `audit()` checks every persisted artifact and store layout. No pickle,
executable serialization, dynamic imports or source-controlled paths exist.
JSON input is bounded to 16 MiB and a 64-level artifact nesting budget. Hashes
prove consistency, not who supplied bytes; authentication/signatures and physical
file access controls belong to deployment hardening.

Tests exercise all persistable families, restart, corruption, migration rollback,
immutability, four Python hash seeds and order independence. The deterministic
example uses synthetic values and metadata, never a fitted model. Future AFRE-24
adds the forecast snapshot, registry and service boundary with artifact replay,
content-addressed model bytes and provenance linking. AFRE-25 performs final
integration, hardening and research audit. Multiple-testing/overfitting controls
and model-selection history remain explicit in AFRE-19 and AFRE-20 respectively.

AFRE-1 migration 1.0→1.1 adds only feature-store artifacts, lookup/spec/receipt/scope
indexes, immutable triggers and explicit version metadata in one transaction.
Foundation payload bytes, foundation schema metadata and original engine-creation
metadata remain untouched. New `store_schema_version`, `feature_store_schema` and
`feature_store_engine_version` identify the additive extension. Failed migration
rolls back to the valid legacy layout; unknown future layouts/versions fail closed.

The feature-store example verifies hash seeds, exact input/state/receipt lineage,
unchanged old selections after revisions, serving/batch parity and byte-identical
restart. Tests additionally reverse insertion/origin order, interleave a second
SQLite writer inside an actual historical join and corrupt ancestor provenance.
All tests block sockets/DNS. The feature benchmark records at least 20,000 vintages
over multiple features/securities and verifies indexed retrieval/restart; timings
are local observations with no production SLA. AFRE-1 performs no model fitting,
label computation or global/fold normalization fitting.

AFRE-2 migration 2→3 adds target artifacts and immutable temporal/membership
indexes without changing any prior payload/table/metadata value. The strict prior
repositories reject this future store; TargetRepository supplies shared access.
Target datasets pin full forecast-origin identities, supplied universe, exact source
build, calendar/action/benchmark vintages, rows, source cutoff, actual construction
time and engine/builder versions. Four hash seeds, reverse bar order, concurrent
future inserts and restart preserve canonical bytes. Corrections create new builds.
Deep audit recalculates labels and checks indexed evidence. New caches last only
one pinned snapshot. The target benchmark records 20,000 observations/12,000 labels
and indexed cutoff queries. AFRE-1's demo explicitly keeps its engine-0.2.0 fixture
to preserve its old frozen identity; the completed tests/contracts are unchanged.
See [target lineage](target-lineage.md) and [availability](target-availability.md).

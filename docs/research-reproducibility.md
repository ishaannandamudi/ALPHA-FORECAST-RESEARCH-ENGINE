# Research reproducibility

Engine: **0.1.0**. Foundation schema: **1.0**. SQLite schema: **1.0**, represented by
`PRAGMA user_version=1`. Processing, model, label, calendar, source and selection
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

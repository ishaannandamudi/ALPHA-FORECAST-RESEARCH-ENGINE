# AFRE-0 completion report

AFRE-0 is complete in this standalone repository. No sibling repository was
modified. No commit or push was made. AFRE-1 and all predictive modeling remain
deferred. The master specification preceded contract implementation and freezes
the advanced roadmap of 26 distinct phases, AFRE-0 through AFRE-25.

| Item | Delivered result |
| --- | --- |
| A — Architecture | Immutable contracts → pure validation → deterministic identity → transactional artifact registry; neutral upstream protocols |
| B — Package structure | `src/afre` has 19 modules and `py.typed`; tests, docs, examples, benchmark and repository-check script |
| C — Master specification | `AFRE_MASTER_SPEC.md` covers mission, architecture, clocks, research hygiene, lifecycle, boundaries, security and frozen roadmap |
| D — Versions | Engine 0.1.0; foundation schema 1.0; store schema 1.0 (`user_version=1`) |
| E — Forecast origin | Stable instrument, UTC nanoseconds, explicit cutoff, session/build context, historical universe fingerprint |
| F — Horizons | Elapsed nanoseconds, session counts and bar counts; explicit calendar/bar identity and endpoint convention |
| G — Targets | Eight target types; exact `(T, endpoint]` price-selection semantics; residual benchmark required; no label computation |
| H — Features | Versioned typed definitions and values; source/version/quality; immutable scalar parameter tuples; six distinct absence states |
| I — Availability | Same-time availability accepted; origin cutoff enforced; observed time cannot follow availability |
| J — Derived lineage | Dependency and computation clocks establish availability floor; evidence-bound historical reconstruction contract |
| K — Feature rows | Exact complete definition set; duplicate/security/range/universe checks; future features rejected |
| L — Target rows | Exact elapsed endpoint or nonelapsed resolver evidence; completion/data availability; verified-label fit eligibility |
| M — Dataset manifests | Universe, features, targets, sources, ranges, calendar, adjustments, missing policy, processing and engine versions determine identity |
| N — Universe manifests | Membership valid intervals and independent knowledge times; immutable historical selection identity |
| O — Survivorship protections | Current-constituent reconstruction prohibited; future-known and expired memberships excluded; stable IDs separate reused tickers |
| P — Corporate actions | RAW, SPLIT_ADJUSTED, TOTAL_RETURN, EXPLICIT_ADJUSTMENT_STREAM; explicit source/cutoff; future adjustment vintage rejected |
| Q — Providers | Feature, market data, EIE, MCE, options and microstructure protocols; no concrete adapters |
| R — EIE boundary | Neutral final-snapshot reference retains ID, cutoff, availability, engine/schema versions and component digests; no internal-table coupling |
| S — Experiment identity | Dataset/model/split/evaluation/cost/seed/code-version fingerprint with cross-contract agreement checks |
| T — Model specs | Family, immutable parameters, feature set, target/horizon, training policy, explicit uint64 seed and implementation version |
| U — Model artifacts | Metadata for spec, dataset, fit cutoff, byte digest, explicit format, metric refs and availability; result/model lineage validator; no loading/fitting |
| V — Serialization/hashing | Exact canonical UTF-8 JSON; finite values; explicit safe tags; domain-separated SHA-256; order and hash-seed independence |
| W — Persistence/migration | Seven artifact tables plus metadata; explicit atomic transactions; immutable update/delete/duplicate-insert triggers; deterministic 0→1 migration; future versions fail closed |
| X — Validation | Constructors enforce strict runtime types and pure invariants; pure feature/training/snapshot/result-model checks |
| Y — Leakage safeguards | Future feature/derived input/adjustment/universe/label exclusion; feature/target namespace separation; target provenance forbidden; ordered split/cutoff/embargo policy |
| Z — Security | Closed decoder; no package eval/exec/pickle/dynamic import/shell/network; no source-selected paths; bounded JSON; corruption/schema checks |
| AA — Documentation | README, master specification and five detailed contract/semantics guides, plus this report; documentation reviewed |
| AB — Tests added | 137 offline tests across identity, temporal semantics, lifecycle, persistence, serialization and reproducibility |
| AC — Full pytest | 137 passed on Python 3.11.16; sockets and DNS blocked in every test |
| AD — Coverage | 99.81% combined statement/branch coverage: 929/930 statements and 109/110 branches; threshold 95% passed |
| AE — Ruff | Lint and format checks passed |
| AF — mypy | Strict checking passed for package, tests, examples, benchmark and repository-check script |
| AG — Diff review | All deliverables reviewed, including untracked content; `git diff --check` and complete-file whitespace scan passed; status remains uncommitted |
| AH — Secret/unfinished-work scan | Offline credential-pattern and unfinished-marker scan passed; package executable/import boundary test passed |
| AI — Benchmark | 100,000 contracts ≈1.777 s; 1,000 manifest hashes ≈0.076 s; persistence + 100 reloads ≈0.064 s; local timings only |
| AJ — Dependencies | Zero runtime dependencies. Pinned pytest 8.4.2, pytest-cov 7.1.0, Ruff 0.16.10 and mypy 1.19.1 are development tools |
| AK — Remaining limits | Provider truth/authenticity, adapters, feature store, calendar/label engines, actual purging/preprocessing, fitting, calibrated predictions and execution are outside AFRE-0 |
| AL — Exact AFRE-1 scope | Point-in-time feature store only; details below |

## Verification evidence

The full socket-blocked pytest suite also includes four separate Python hash seeds
(0, 1, 42 and random), restart replay across every stored artifact family, payload
and index corruption, unknown schemas, migration rollback, replacement-insert
protection, target leakage and the README example. The example independently
reopened SQLite and preserved six fingerprints; it rejected a feature available
one nanosecond after origin and excluded the not-yet-completed target at origin.

Coverage's single unexercised statement/branch is the defensive migration return
when another initializer finishes between the initial version read and acquisition
of the writer lock. The primary empty-store migration, replay path and atomic
migration failure are exercised. No production concurrency guarantee is claimed.

The project uses a separate `.venv311` for Python 3.11 because the pre-existing
`.venv` used Python 3.9. Development tools are isolated from runtime dependencies.
Package tests and examples use no network; dependency installation is a separate
setup operation. Credentials and model bytes are neither required nor loaded.

## Remaining limitations

Typed clocks and lineage validate declared facts; they cannot prove a provider
reported a publication time honestly, authenticate reconstruction evidence, or
identify a future target disguised as an ordinary scalar. Future adapter and DAG
audits must establish those facts. Adjustment contracts declare vintages but do
not process actions. Universe contracts support immutable historical membership,
while real constituent ingestion/revision handling belongs to AFRE-3.

Split policies describe purging and embargo but do not execute a walk-forward
splitter. Metric records and model artifacts are metadata only. Registry references
are not foreign-key-enforced across embedded artifacts; callers resolve referenced
model metadata and can use `validate_result_model` for consistency. Artifact hashes
prove byte consistency, not authenticity. Direct file administrators can remove
protections; replay/audit rejects detected inconsistencies.

## Exact AFRE-1 scope (deferred)

- Feature registry and immutable observation/revision vintages.
- Computation DAG with input availability, versioned parameters and lineage audits.
- Point-in-time joins and efficient historical batch retrieval.
- Explicit stale/missing policies and materialization.
- Market and EIE snapshot features with conservative publication/delivery clocks.
- Optional provider-neutral MCE/options/AME adapters, without sibling imports.
- Training/serving parity and fold-local normalization lineage.
- Target provenance exclusion and future-input leakage tests.

AFRE-1 does not expand into full label construction, dataset splitting, model
training, portfolios or execution. **Stop after AFRE-0.**

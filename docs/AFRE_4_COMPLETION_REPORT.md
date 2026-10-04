# AFRE-4 completion report

AFRE-4 implements **Dataset Builder & Leakage-Safe Splitting**. AFRE-0 through
AFRE-3 contracts remain stable; the only earlier engine edit preserves historical
snapshot engine metadata during replay after the version bump. No predictive model
is fitted. Changes remain unstaged and uncommitted on main. Verification results are
recorded below.

| Item | Topic | Result |
| --- | --- | --- |
| A | Architecture | Separate research layer composes exact AFRE-1 joins, AFRE-2 labels and AFRE-3 snapshots; one pinned upstream read and atomic publication. |
| B | Package structure | `afre.research_datasets`: schema, definitions, samples, manifests, intervals, splits, splitting, preprocessing, fitting, storage, repository, materialization, validation, audits and engine. |
| C | Dataset schema | New dataset schema 1.0; earlier foundation/feature-store/target/universe schemas remain 1.0. |
| D | Engine/store versions | Engine 0.5.0; research store 1.4; SQLite user_version=5. Earlier creation metadata preserved. |
| E | Research samples | Exact stable security, origin/cutoff, snapshot/eligibility, feature set/join/vintages, target definition/vintage/window/availability and build/group evidence. |
| F | Sample states | AVAILABLE, FEATURE_INCOMPLETE, TARGET_NOT_AVAILABLE_YET, TARGET_MISSING, INELIGIBLE, UNIVERSE_UNKNOWN, CONFLICTED, INVALID. Failed cells remain explicit. |
| G | Sample identity | Canonical domain-separated SHA-256; exact frozen input and upstream selections participate. No ticker key or implicit current universe. |
| H | Dataset manifests | Definition/input build, typed column schema, semantically ordered complete sample grid, completeness, processing/construction times and versions. |
| I | Dataset materialization | Exact security × historical origin × requested target grid; no target recomputation; explicit prior target dataset per snapshot. |
| J | Completeness | COMPLETE for all available cells; KNOWN_GAPS for explicit failures; UNKNOWN for unresolved universe decisions. |
| K | Feature joins | Direct AFRE-1 point_in_time_join under outer pinned read; exact feature set, scope bindings, vintage clocks and query policy retained. Feature conflicts fail explicitly. |
| L | Target joins | Full matching forecast-origin/universe and exact TargetSetManifest; pinned AFRE-2 rows/source builds; no global latest truth substitution. |
| M | Universe/eligibility joins | Exact AFRE-3 snapshot projection; failed/unknown/conflicted cells preserved without pretending to be eligible foundation origins. |
| N | Target intervals | Actual resolved price endpoints and explicit inclusion; default (origin close, endpoint close]; full declared information interval includes feature lookback. |
| O | Split strategies | FIXED_HOLDOUT, WALK_FORWARD, ROLLING_WINDOW, EXPANDING_WINDOW; versioned explicit schedules. |
| P | Folds | Dataset/split/ordinal, exact origin ranges, training cutoff, common sealed TEST and inherited policies/preprocessing specs. |
| Q | Partition semantics | Exactly one TRAIN/VALIDATION/TEST/PURGED/EMBARGOED/INELIGIBLE record per sample/fold, with reason and semantic replay. |
| R | Purging | NONE/target/full information rule, security/issuer/sector/market/global scope; sorted unions and binary search, bounded comparisons. Unknown protected intervals fail. |
| S | Embargo | Elapsed nanoseconds, supplied regular sessions or declared bars; BEFORE/AFTER/BOTH, exact half-open fences, previous validation windows included. |
| T | Training cutoffs | Train end <= cutoff <= validation start; cutoff <= frozen dataset processing cutoff. |
| U | Target-known-by-cutoff | Existing AFRE-2 completion/quality/window/availability helper; equality admitted, later truth rejected. |
| V | Fold-local preprocessing | AFRE-1 NormalizationSpec/State; TRAIN-only mean/population standard deviation, median/IQR, min/max range or winsor quantiles; exact fit/skipped research IDs. |
| W | Missing-data policy | FAIL, retained DROP_SAMPLE trace, PRESERVE_MISSING; IMPUTE_TRAIN_ONLY reserved and rejected. No implicit global imputation. |
| X | Contamination audits | Each materialized cell has a frozen SampleContaminationAudit; optional fold admission audit; dataset/fold audits recompute grid, compatibility, label evidence, disjoint partitions, purge/embargo and TRAIN statistics. |
| Y | Test-set boundary | Common final TEST never feeds training/validation; separate explicit evaluation identity/purpose/cutoff records reuse. Semantic seal, not authentication or AFRE-19 governance. |
| Z | Multi-security/cross-sectional support | Stable IDs, PIT broadcast features, typed historical groups, global/group purging and prepared WITHIN_ORIGIN/WITHIN_ORIGIN_GROUP preprocessing scopes; actual transforms deferred. |
| AA | Multi-horizon support | Exact requested target definitions and individual actual intervals; target horizons do not duplicate preprocessing observations. |
| AB | Compatibility validation | Explicit neutral source allowlist, pinned universe/target calendars, feature/target adjustment identity or declared intentional difference, full origin/universe/build agreement. |
| AC | Persistence/migration | Six immutable research tables/index families; additive transactional 4→5, rollback/future rejection, idempotence and corruption checks. |
| AD | Indexes/performance | Dataset/order, security/origin/target interval/availability, fold/split/partition; sorted indexed purge; scoped validated-object/projection/eligibility caches. |
| AE | Deterministic replay | Four Python hash seeds, reverse upstream/request insertion, same-input idempotence, restart and frozen corrections tested byte-for-byte. |
| AF | Concurrency | Actual second-connection backdated insert during pinned read excluded from current build; subsequent build gets a new identity. |
| AG | Security | Closed data-only serialization, static contracts, fixed DDL, explicit bounds, no runtime networking/shell/eval/exec/pickle/provider-selected code or paths. |
| AH | Documentation | Six required new documents, README/master/temporal/reproducibility/feature-store/target/universe integration and this report. Advanced roadmap stays 26 distinct phases, AFRE-0 through AFRE-25. |
| AI | Tests added | 129 focused AFRE-4 tests passed in 50.48 s, including migration/corruption, hash seeds 0/1/42/random, reversed insertion, restart, concurrent write, cutoff equality, purge/embargo, TRAIN-only preprocessing, survivorship, ticker reuse and compatibility. All 30 prior test files are byte-unchanged; their 381 tests remain in the full suite. |
| AJ | Full pytest | 510 passed in 218.68 s. Every test and seed child blocks socket construction/connection, socketpair and DNS entry points. All 381 prior tests pass with the 129 new AFRE-4 tests. |
| AK | Coverage | Branch-enabled combined statement/branch coverage 99.17%, exceeding the >=95% gate: 6,160 statements, 25 missed; 1,460 branches, 34 partial. |
| AL | Ruff | Lint passed; format check passed for all 167 Python files. |
| AM | mypy | Strict full-repository check passed: 130 source files, no issues. |
| AN | Diff review | Tracked changes and all new source/tests/docs/demo/profile reviewed; git diff --check passed. 11 modified and 32 new files; no staged changes. main HEAD remains 5e55c8c; no commit/push. |
| AO | Secret/TODO scan | Existing check_repository.py passed: 170 deliverables checked for secrets, TODO/FIXME/unfinished work and whitespace. Documentation check passed: 37 documents, exact 26-phase roadmap, versions, links and all A–AS items. |
| AP | Benchmark/profile | Passed: 32 securities × 8 origins × 2 horizons = 512 samples, 3 folds, actual pipeline/restart/audits; independent 100,000-interval workload used exactly 100,000 comparisons. cProfile run 92.887 s; SQLite 51,204,096 bytes; explicit 16 MiB serialized/lineage budget. Measurements below; no production SLA or claim of a 100,000-sample end-to-end build. |
| AQ | Dependencies | Zero runtime dependencies; existing pinned development tools unchanged. |
| AR | Remaining limitations | No predictor, imputer, learned selector/neutralizer or statistical model selection; semantic TEST seal only; bounded in-memory export/lineage; existing AFRE-1 embedded universe provenance can dominate large builds; provider authenticity remains external. |
| AS | Exact AFRE-5 scope | Statistical Baseline Models: unconditional mean/median, persistence/reference, linear/ridge, small trusted lasso/elastic-style regularization, cross-sectional linear and factor/residual baselines, deterministic training, point prediction, fit metadata and out-of-sample evaluation. No probabilistic calibration yet. Deferred; not implemented. |

The dataset construction state does not imply that every label was known at every
historical fit cutoff. TRAIN admission uses that fold's exact cutoff. Validation and
TEST membership are historical-origin decisions; evaluation truth needs an explicit
later cutoff. Prepared normalization occurs at its declared availability/application
time and cannot change raw feature causality. All observations are synthetic fixtures.

The offline demo passed all grid, label-cutoff, purge/embargo, TRAIN-statistics,
frozen-correction, contamination-audit and restart assertions. Its first-fold TRAIN
mean is 17.0 despite validation/test outliers. Known missing later observations for a
delisted security stay missing; ticker reuse does not merge stable security identities.

Profile observations on this local Python 3.11 run, with cProfile enabled:

| Operation | Seconds |
| --- | ---: |
| Synthetic upstream fixture setup | 26.032047 |
| Dataset assembly | 3.757672 |
| PIT joins | 1.263006 |
| Dataset persistence, including per-sample audits | 16.882774 |
| Dataset build total | 21.903812 |
| Split generation and persistence | 1.468012 |
| TRAIN preprocessing | 4.550716 |
| Partition retrieval | 3.900631 |
| Exact embargo fence generation | 0.000106 |
| Dataset/fold contamination audits | 30.772164 |
| Restart replay | 0.991959 |
| Independent 100,000-interval indexed purge | 2.296354 |

Serialization, immutable-object validation and existing embedded upstream universe
provenance dominate the profile. The interval workload measures indexed purge scaling
separately. No performance threshold or production throughput is inferred from it.

No AFRE phase claims trading profitability from predictive metrics. AFRE-18 evaluation,
AFRE-19 overfitting controls, AFRE-20 model selection, AFRE-21 ensembles, AFRE-22 health,
AFRE-23 champion/challenger, AFRE-24 forecast service and AFRE-25 final hardening remain
separate. Portfolio construction, risk optimization and execution stay downstream.
**Stop after AFRE-4. No commit or push.**

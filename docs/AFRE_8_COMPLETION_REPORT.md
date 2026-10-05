# AFRE-8 completion report

Scope: Multi-Horizon Forecast Architecture. Stop after AFRE-8.
No commit or push is performed. AFRE-9 remains deferred.

| Item | Area | Evidence / result |
| --- | --- | --- |
| A | Architecture | Additive AFRE-8 composition above unchanged AFRE-0–7 contracts; exact independent/shared-feature/shared-backbone modes. |
| B | Package | 18 bounded modules in `afre.multihorizon`; separate alignment, fitting, covariance, bundle, evaluation, repository and audit paths. |
| C | Multi-horizon schema | 1.0; all earlier public schemas remain 1.0. |
| D | Engine/store versions | Engine 0.9.0, shared store 1.8, SQLite user_version=9; zero runtime dependencies. |
| E | HorizonSet | One exact rich TargetDefinition per typed ForecastHorizon; duplicate semantic horizons reject. |
| F | Ordering | Comparable elapsed durations or compatible counts sort canonically. Mixed bases require explicit canonical order. |
| G | Target mapping | Exact target, feature set, point/probability/calibration specs and artifacts validated per binding. |
| H | Architecture types | INDEPENDENT_PER_HORIZON, SHARED_FEATURES_SEPARATE_MODELS, SHARED_LINEAR_BACKBONE; no speculative JOINT_LINEAR. |
| I | Independent models | Own exact AFRE-5/6/7 artifacts, feature mappings, folds and cutoffs; independently admissible labels. |
| J | Shared features | Exact feature-set equality; learned parameters remain separate. Different feature sets are supported by independent mode. |
| K | Shared parameters | Real weighted pooled QR coefficient vector with per-horizon intercepts; explicit GLOBAL_SHARED/HORIZON_SPECIFIC/GROUP_SHARED contracts. Group fitting is not advertised. |
| L | Fit-run identity | Per-horizon model/matrix/fold/preprocessing/TRAIN IDs, intersection rows, shared state and supplied physical clocks. |
| M | TRAIN intersections | Full ForecastOrigin/security intersection of existing admitted TRAIN matrices, with every required label known by shared cutoff. |
| N | Cutoffs | Independent cutoffs may differ. Shared cutoff cannot exceed any contributing horizon cutoff. |
| O | Long-horizon leakage | Origin30 short label is known at35, long at45: it cannot enter the shared cutoff40 intersection; held-out perturbation does not alter coefficients. |
| P | Forecast bundles | Exact common stable instrument/full origin, ordered layers, fit/architecture and optional dependence evidence. |
| Q | Completeness | COMPLETE/PARTIAL/UNAVAILABLE; no missing horizon is dropped. Included required layers and all availability clocks are checked; computation cannot precede included artifact availability. |
| R | Vectors | Ordered expectation and median with explicit missing/unsupported values. Adjusted marginals do not invent a calibrated expectation. |
| S | Quantile surface | Exact horizon×level raw/calibrated surfaces; within-horizon monotonicity preserved without cross-horizon ordering constraints. |
| T | Event surface | Exact target/horizon plus threshold/comparison; identical GT0 thresholds at two horizons remain distinct events. |
| U | Dependence | NONE or explicit EMPIRICAL_RESIDUAL_COVARIANCE. No joint PDF, causal claim or implicit copula. |
| V | Covariance | Matched TRAIN residual rows, mean centering, N/N−1 denominator, ordered matrix, cutoff, availability and numerical version pinned. |
| W | PSD | Symmetry, nonnegative diagonal and bounded deterministic Cholesky-like tolerance check; no hidden covariance repair. |
| X | Calibration by horizon | Own AFRE-7 state/raw chain; wrong-horizon calibration rejects. No cross-horizon pooling. |
| Y | Consistency | Typed family/unit, benchmark, adjustment, common origin and nested exact elapsed-window diagnostics; compatible expected differences only, including explicit volatility annualization compatibility. |
| Z | No naive scaling | No nested simple-return addition, quantile addition, five-times-return law or proportional variance assumption. |
| AA | Per-horizon evaluation | Reuses AFRE-5 metrics, AFRE-6 proper scores and AFRE-7 scoring/diagnostic references; each truth has its own availability cutoff. |
| AB | Aggregates | Supplied weighted MSE is descriptive, not selection. Missing positive-weight metrics yield None; paired metrics use exact origin intersection. |
| AC | TEST boundary | Independent explicit per-horizon access identities/seals and prior reuse references; exact repeat idempotent, changed evidence rejects. |
| AD | Audit | Replay checks exact mappings, TRAIN evidence, fit clocks, covariance, layer identity, truth scoring and historical availability. |
| AE | Lineage | One bounded root-to-calibration/probability/point/shared/dependence/fold/TRAIN/features/targets traversal; evaluation adds its pinned truth. |
| AF | Persistence/migration | Immutable canonical artifacts and three additive tables; transactional8→9, rollback, future rejection and prior rows/DDL/metadata preservation tested. |
| AG | Indexes/performance | Verified horizon-set/architecture, target/horizon/model/fold/cutoff, origin/security/availability and dependence/evaluation indexes. |
| AH | Replay | Restart, canonical reverse binding/insertion order and fresh process hash seeds0/1/42/random; deterministic full artifacts. |
| AI | Concurrency | A second writer inserts corrected longer-horizon truth during a frozen bundle read. The read cannot see it; the old bundle bytes remain unchanged. |
| AJ | Numerical accuracy | Independent known covariance and pooled slope/intercept references; population/sample denominators, singular PSD and invalid matrices tested. |
| AK | Security | Closed registered JSON, finite values and bounded resources; no executable plugins, unsafe model loaders, network calls or source paths. Full suite blocks socket/DNS. |
| AL | Documentation | Six new scope documents, profile/report and updated master/README/fit/probability/calibration/reproducibility docs; frozen 26 phases AFRE-0–25. |
| AM | New tests | 108 AFRE-8 acceptance tests covering contracts, sharing, cutoffs, layers, truth-free application, PSD, TEST, migration, corruption, bounds, concurrency and replay. |
| AN | Full pytest | 993 passed in 363.99s, including all 885 earlier tests and 108 AFRE-8 tests; socket/DNS blocked. |
| AO | Branch coverage | PASS: 99.05% combined statement/branch coverage; branch mode enabled, threshold 95%; 993 passed in 954.49s. 11196/11253 statements and 2392/2466 branches covered. |
| AP | Ruff | Lint and formatting checks passed across the repository. |
| AQ | Strict mypy | Passed across 249 source files. |
| AR | Diff review | Changes are additive AFRE-8 implementation/tests/docs plus version/documentation gate updates; prior phase implementation/contracts/tests remain unchanged. |
| AS | Secret/unfinished scans | PASS: 320 deliverables scanned for secrets, unfinished work and whitespace; git diff --check clean. |
| AT | Profile | 3,000 residual rows×4 synthetic horizons; separate 2-horizon causal persisted workload with 100 bundles, 8 matched TRAIN rows, 357 audit nodes, 113 artifacts and 9,875,456-byte SQLite. Covariance/aggregate reference errors0.0; no SLA. |
| AU | Dependencies | Python3.11+ and standard library only; project runtime dependencies remain[]. |
| AV | Limits | Backbone point-only, raw features/no learned shared transforms, no group fitting/joint density/correlation/automatic repair. Covariance is retrospective TRAIN dependence. Profile kernels and smaller historical workload are reported separately. |
| AW | Exact AFRE-9 scope | Cross-Sectional Alpha & Ranking: within-origin security ranking, cross-sectional forecasts, rank targets/metrics, IC/rank IC, sector/industry-neutral evaluation, PIT group memberships, cross-sectional normalization and ranking stability; no event-conditioned specialization yet. |

The [architecture](multi-horizon-forecasting.md) documents supported contracts and
limits. The [profile](multi-horizon-benchmark.md) records reproducible local timings.
Predictive metrics do not establish trading profitability. Portfolio construction,
risk optimization and execution remain downstream projects after AFRE.

Working tree: `main...origin/main`, 9 modified tracked files and 40 new files;
no staged changes. HEAD remains `5b9df80 Add forecast calibration`.
No commit or push is performed.

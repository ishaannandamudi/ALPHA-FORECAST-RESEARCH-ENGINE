# AFRE-5 completion report

AFRE-5 implements **Statistical Baseline Models** against frozen AFRE-4 research
folds. The current working tree was resumed and its existing numerical, persistence,
leakage and constant-Pearson work retained. AFRE-0 through AFRE-4 public contracts
and prior tests remain unchanged. The only earlier implementation change preserves
the strict pre-model interfaces' AFRE-4 universe snapshot metadata (0.5.0), while
ModelRepository emits 0.6.0. This fixes the version-bump regression without changing
the UniverseSnapshot contract or an existing assertion. Changes are unstaged and
uncommitted on main.

| Item | Topic | Result |
| --- | --- | --- |
| A | Architecture | Separate model layer composes frozen AFRE-1 features, AFRE-2 targets and AFRE-4 dataset/split/preprocessing. Fit reads one pinned snapshot and publishes immutable results atomically. No selection or tuning. |
| B | Package structure | `afre.statistical_models`: schema, definitions, artifacts, design_matrix, linear_algebra, elastic, fitting, prediction, metrics, evaluation, storage, repository, lineage, validation, engine and static public exports. |
| C | Model schema | New closed model schema 1.0. Foundation, feature-store, target, universe and dataset schemas remain 1.0. All new artifacts use canonical data-only JSON and domain-separated SHA-256 fingerprints. |
| D | Engine/store versions | Engine 0.6.0; shared model store 1.5; SQLite user_version=6, additive to research store 1.4/user_version=5. Prior creation metadata and schemas are retained. |
| E | Model families | All ten typed families work in their declared domain: UNCONDITIONAL_MEAN, UNCONDITIONAL_MEDIAN, REFERENCE_VALUE, PERSISTENCE, LINEAR_REGRESSION, RIDGE_REGRESSION, LASSO_REGRESSION, ELASTIC_NET, CROSS_SECTIONAL_LINEAR and RESIDUAL_LINEAR. Incompatible target/intercept/preprocessing configurations fail explicitly. |
| F | ModelSpec | BaselineModelSpec composes the unchanged foundation ModelSpec. It pins rich registered feature set, exact target/horizon, fold, supplied preprocessing, fixed penalties, intercept, rank/condition/nonconvergence/missing/weighting policies, seed, solver and versions. Foundation ModelArtifact and ExperimentSpec retain their original meanings. |
| G | Fit-run identity | ModelFitInputs pins exact matrix, admitted TRAIN order, dataset/split/fold, preprocessing, cutoff and fit clocks. FittedModelArtifact points to those inputs; ModelFitRun pins inputs, result and diagnostics. The immutable unique artifact→run index avoids a circular fingerprint and requires completed publication before prediction. |
| H | Design matrices | Exact TRAIN rows sort by origin, stable security and sample identity. Columns follow the frozen dataset's feature name order. Matrix pins joins/vintages, transformed finite numeric values, responses, preprocessing, target, cutoff and explicit missing exclusions. Insertion and dictionary order are irrelevant. |
| I | Mean/median/reference baselines | Mean and median use only admitted TRAIN targets. Supplied reference is a fixed finite scalar in the spec; all use explicit GLOBAL intercept and zero feature coefficients. No held-out response estimates a reference. Exact numerical fixtures cover all three. |
| J | Persistence baseline | Explicit PersistenceReference binds a completed trailing simple/log return feature to the same elapsed target horizon. Dimensionless registered market feature and adequate lookback are required; coefficient is one and intercept NONE. No future label read or changed return units. Unsupported target/window semantics reject. |
| K | OLS | Ordinary, cross-sectional and residual linear families solve the exact supplied design and optional GLOBAL intercept. No feature selection, pseudoinverse, silent regularization or unstable coefficient publication. |
| L | Numerical solver | Deterministic column-pivoted Householder QR with original-column tie breaking, stable norms, finite checks, compensated summation, back substitution and inverse permutation. No explicit matrix inversion or normal equations. |
| M | Rank deficiency/conditioning | Rank threshold is tolerance × maximum original column norm. Short, zero/rank-deficient and excessive-condition-proxy systems fail. FAIL and RIDGE_REQUIRED refuse unstable OLS; callers must explicitly submit a ridge spec. The R-diagonal ratio is documented as a proxy rather than an exact condition number. |
| N | Ridge | Deterministic augmented QR minimizes sum SSE + supplied L2 × squared coefficients. Intercept regularization is explicit. Lambda is finite, nonnegative and identity-bearing. Lambda zero follows OLS rank/condition behavior. Known solutions and stationarity checks pass. |
| O | Lasso | Cyclic coordinate descent from zero minimizes sum SSE + supplied L1 × absolute coefficients. Canonical coordinate order, L1/2 soft threshold, exact objective, fixed max passes/tolerance and explicit KKT convergence. Tests cover sparse/negative/zero-column coefficients and nonconvergence. |
| P | Elastic net | Same deterministic solver with independently supplied L1 and L2. No hidden loss scaling or normalization. Both coefficient-change and TRAIN-scaled KKT tests must pass; RETURN_NONCONVERGED records failure and cannot issue forecasts. |
| Q | Cross-sectional baseline | Multiple stable securities/origins, equal row weights, exact shared design and global/absent intercept. No future-origin demeaning or implicit weights. WITHIN_ORIGIN intercept fitting is explicitly rejected. Evaluation's per-origin IC is diagnostic only. |
| R | Residual baseline | Fits exact AFRE-2 RESIDUAL_RETURN responses with supplied benchmark lineage. Real residual-target integration passes. No benchmark estimator is learned from future or held-out truth; optional causal factor features remain declared ordinary inputs. |
| S | TRAIN-only fitting | AFRE-4 admission and semantic replay determine exact TRAIN. VALIDATION, TEST, PURGED, EMBARGOED and INELIGIBLE responses are guarded out. Every target must be completed/verified and available by cutoff; equality passes. Fixed supplied preprocessing is replayed, never globally refitted. Held-out price and feature outliers do not change learned parameters. |
| T | Model availability | Explicit UTC start ≥ cutoff, completion ≥ start, availability ≥ completion and admitted input/preprocessing availability. Historical OOS prediction requires model and features/states available by origin cutoff. Later reconstructed computation stays later; retrospective IN_SAMPLE is explicitly marked. |
| U | Model artifacts | Immutable family/spec lineage, ordered feature IDs, intercept/coefficients/reference, penalties/intercept policy, solver/version, diagnostics and availability. Fit inputs carry exact training samples, target via spec, dataset/split/fold and preprocessing. Structured decoding cannot execute a model payload. |
| V | Prediction contracts | PredictionInput accepts origin, exact feature join, optional sample and typed scope, with no response field. PointForecast pins model, target, stable security/origin, input, scalar, availability/computation clocks, historical-admissibility state and identity. Guarded prediction and publication never load TargetVintage. |
| W | Batch prediction | Bounded unique requests sort by origin, stable security and request identity; one read snapshot and atomic publication. Supports IN_SAMPLE, VALIDATION, TEST and OUT_OF_SAMPLE_OTHER. Exact immutable memberships prevent TRAIN/TEST relabeling; incomplete or nonconverged fits reject. |
| X | Evaluation metrics | Later explicit cutoff joins only exact frozen truth. COUNT, prediction−truth mean error, MAE, MSE, RMSE, R² against evaluation target mean, Pearson, average-tie Spearman and descriptive sign accuracy. Empty/constant states are explicit; unavailable labels are recorded exclusions. No horizon/model/partition pooling. |
| Y | IC/rank diagnostics | Separate per-origin Pearson and rank IC preserve insufficient/constant states. Summary reports valid counts, means, medians and population standard deviations. Literal constant decimal vectors are detected before centering, preventing false correlation from rounding; regression retained. |
| Z | Baseline comparisons | Candidate-minus-reference deltas require identical dataset/fold, target/horizon, scope, cutoff, paired sample/target/truth evidence and exclusions. Mismatched samples and horizons reject; metrics cannot choose a model or mutate a spec. |
| AA | Test boundary | TEST evaluation requires explicit identity/purpose and persists the unchanged AFRE-4 TestEvaluation ready-grid/reuse record. Each model evaluation uses its own exact horizon subset. Conflicting identity reuse and scope bypass reject. Semantic seal is not authentication or AFRE-19 governance. |
| AB | Fit diagnostics | TRAIN count, feature count, target mean/population deviation, residual SSE, coefficient norm, column scales, QR rank/condition proxy when calculated, iterations, convergence and final KKT residual. Nonidentity elapsed timings separate matrix, numerical solve and publication/validation. |
| AC | Coefficient/model audits | Semantic replay recomputes exact matrix, fit-input clocks, fixed solver coefficients and diagnostics. Audit resolves exact completed run, foundation bridge, spec, matrix, fold and admitted TRAIN evidence; self-consistent forged coefficients or matrices still reject. |
| AD | Prediction lineage | Forecast→model→run/inputs→matrix→fold→TRAIN samples→feature vintages/preprocessing and admitted labels. Held-out forecast input expands feature evidence without held-out truth; evaluation adds later truth explicitly. One shared node/depth/byte budget covers model and upstream provenance; cycles/unresolved references fail. |
| AE | Persistence/migration | Five immutable model artifact/index tables persist specs, matrices, inputs/runs, diagnostics, coefficients, requests/forecasts, evaluations, comparisons and audits. Transactional 5→6 migration preserves prior SQL/rows/metadata; rollback, future-version rejection, immutable writes, idempotence, payload/hash/family/schema/index/orphan corruption are tested. |
| AF | Indexes/performance | Indexed spec family/fold/target, fit dataset/split/fold/spec/availability, forecast model/target/origin/security/scope and evaluation model/fold/target/scope/cutoff. Dense sample/feature/coefficient/iteration bounds apply before solving. Validation caching is scoped to a snapshot/transaction. |
| AG | Deterministic replay | Seeds 0, 1, 42 and random, reversed upstream/request/prediction insertion and restart preserve byte-identical semantic artifacts within supported Python/platform arithmetic. Explicit spec/penalty/solver/clock changes produce new identities. Timings do not enter identity. |
| AH | Concurrency | A real second connection inserts a backdated upstream correction during a pinned fit; old frozen fit remains identical. Rebuilt corrected dataset/split/preprocessing/spec creates a new model identity, with old model and forecast bytes unchanged. |
| AI | Numerical correctness | Known intercept/multifeature QR coefficients, pivoting, rank/condition failures, fixed ridge coefficients/intercept penalties/lambda zero, exact orthogonal lasso/elastic shrinkage and sparsity, KKT/nonconvergence and finite-overflow checks. Separate 4,000-row/16-feature workload verifies coefficient error and ridge stationarity. |
| AJ | Security | Static closed structured artifact decoding, immutable fixed DDL and explicit budgets. Zero runtime network/shell/eval/exec/pickle/joblib/dynamic executable import/provider-selected code or paths. Full tests and hash-seed children block socket creation/connection/socketpair and DNS calls. |
| AK | Documentation | Six required new documents, README/master/reproducibility/dataset/preprocessing/feature/target integration, offline demo/profile and this 48-item report. Advanced roadmap remains 26 distinct phases, AFRE-0 through AFRE-25. AFRE-6 is deferred Probabilistic Forecasting; calibration remains AFRE-7. |
| AL | Tests added | Final focused AFRE-5 run: 94 passed in 31.16 s. Numerical, causal cutoff, target-free prediction, all ten families, persistence/residual integration, TEST reuse, exact comparison, metrics/constant-Pearson, frozen snapshot, determinism/restart, additive migration/rollback, corruption and bounds. All 37 prior test files remain byte-unchanged; their 510 tests remain in the full suite. The focused older-interface compatibility/repository and new guard regressions also passed: 41 tests in 4.92 s. |
| AM | Full pytest | 604 passed in 313.38 s, including all 510 prior tests and 94 new AFRE-5 tests. This full run used branch coverage and the unchanged autouse socket/DNS block; hash-seed child processes also explicitly block the seven network entry points. No test assertions were weakened. |
| AN | Coverage | Branch-enabled combined statement/branch coverage 98.96%, exceeding the >=95% gate: 7,512 statements, 43 missed; 1,754 branches, 49 partial. Branch-only coverage is also above 95% at 96.98%. |
| AO | Ruff | Lint passed; format check passed for all 203 Python files discovered by Ruff. |
| AP | mypy | Strict full-repository check passed: 159 source files, no issues. |
| AQ | Diff review | All tracked changes and 36 new files reviewed, including complete source/tests/docs/demo/profile. git diff --check passed. 12 modified files, 36 new files, no staged changes. main HEAD remains 150a8776f90f7eaffe2b734bfbe8934fa28aa1c3; no commit/push. Baseline SHA-256 comparison confirms all prior tests and public contract files unchanged; earlier source changes are the version constants and the two snapshot-metadata compatibility files described above. |
| AR | Secret/TODO scan | Existing check_repository.py passed: 206 deliverables checked for secrets, TODO/FIXME/unfinished work and whitespace. Updated documentation check passed: 44 documents, exact 26-phase roadmap, versions, local links, historical reports and exactly 48 A–AV items. New model source also contains no network/shell/executable-loading or unfinished implementation boundary. |
| AS | Benchmark/profile | Passed: bounded 256-sample/two-fold pipeline with six fits, 90 predictions, six evaluations, audits and restart; separate 4,000-row/16-feature numerical workload. cProfile 36.470 s; SQLite 25,473,024 bytes. OLS maximum coefficient error 5.551115123125783e−17, ridge stationarity residual 1.270095140171179e−13; elastic converged in seven passes, KKT residual 1.2080838107230568e−08. Measurements below are local synthetic observations, with no production SLA or profitability claim. |
| AT | Dependencies | Zero runtime dependencies. Python 3.11+ and existing pinned development tools are unchanged. No NumPy/pandas/Polars/SciPy/sklearn/statsmodels/Arrow/ML framework introduced. |
| AU | Remaining limitations | Bounded stdlib dense arithmetic; default 64 features, explicit ceiling 128; no SVD/pseudoinverse/within-origin intercepts/imputation/feature selection/tuning. Provider scalars and caller clocks need external evidence. Semantic TEST seal only. Existing embedded universe provenance limits registry scaling; numerical throughput is measured separately. No universal cross-platform bit identity or profitability inference. |
| AV | Exact AFRE-6 scope | Deferred Probabilistic Forecasting: conditional forecast distributions, quantiles, probability return exceeds threshold, tail probabilities, conditional variance/scale, proper scoring rules, distribution artifacts and probabilistic evaluation. Post-hoc calibration remains AFRE-7. Nothing from AFRE-6 is implemented. |

## Verification and local observations

The focused suite passes with all final prediction-publication guards. The full
socket/DNS-blocked suite passes all 604 tests with 98.96% branch-enabled coverage.
Lint, formatting, strict typing, whitespace, secret/unfinished-work and documentation
checks pass. All 37 original test files remain byte-identical to the starting tree;
77 prior implementation/contract files remain byte-identical, with only version
constants and the documented two-file snapshot metadata compatibility fix changed.

Model fitting uses exact historical information boundaries. A manifest assembled
later does not authenticate earlier literal AFRE ingestion or a caller's asserted
fit time. A reconstructed forecast retains its declared later computation/final
availability; historical_admissible describes its model/feature information boundary.
All demo and profile observations use synthetic fixtures.

The offline demo covers mean, OLS, fixed ridge, lasso and elastic fits; coefficients;
guarded feature-only VALIDATION prediction; later truth evaluation; identical-sample
comparisons; held-out target/feature perturbations; immutable corrected rebuild;
model/prediction audits; persistence and byte-identical restart.

The profile separates an actual 16-security × 8-origin × 2-horizon registry pipeline
(256 samples, two folds, six fits with 29 admitted TRAIN rows each, 90 predictions,
six evaluations) from a 4,000-row/16-feature dense numerical workload. The latter
does not claim 4,000-row end-to-end registry throughput. The pipeline explicitly
uses a 16 MiB model/dataset serialization budget; original embedded AFRE-1 universe
provenance dominates its validation and serialization cost.

Local Python 3.11 observations, with cProfile enabled:

| Registry pipeline operation | Seconds |
| --- | ---: |
| Synthetic upstream and dataset setup | 21.251347 |
| Design matrix per fit (29 TRAIN rows, one feature) | 0.517786–0.521428 |
| Numerical solve per fit | 0.001221–0.001473 |
| Persistence and semantic validation per fit | 0.558271–0.581975 |
| All 90 predictions and persistence | 1.793556 |
| All six evaluations and persistence | 0.314120 |
| Model/prediction lineage audits and persistence | 2.521230 |
| Restart and indexed artifact reads | 0.065669 |

| Separate numerical workload (4,000 rows, 16 features plus intercept) | Seconds | Check |
| --- | ---: | --- |
| OLS QR | 0.686591 | Rank 17; maximum coefficient error 5.551115123125783e−17; R-diagonal condition proxy 1.4173842171395634 |
| Fixed-L2 ridge QR | 0.682961 | L2=2, unpenalized intercept; stationarity residual 1.270095140171179e−13 |
| Fixed-L1/L2 elastic net | 0.995662 | L1=0.1, L2=2, unpenalized intercept; seven passes; KKT residual 1.2080838107230568e−08 |

Serialization, immutable-object validation and embedded upstream provenance account
for most pipeline cost. These measurements establish neither a production throughput
target nor a claim that thousands of rows passed through the complete registry path.

No AFRE phase claims trading profitability from predictive metrics. AFRE-18
transaction-cost-aware research evaluation, AFRE-19 multiple-testing/overfitting
controls, AFRE-20 model selection, AFRE-21 ensembles, AFRE-22 drift/decay, AFRE-23
champion/challenger evaluation, AFRE-24 forecast service and AFRE-25 final hardening
remain separate. Portfolio construction, risk optimization and execution stay
downstream. **Stop after AFRE-5. No commit or push.**

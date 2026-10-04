# AFRE-6 completion report

AFRE-6 — Probabilistic Forecasting. Changes remain uncommitted in the working tree.
No commit or push is authorized or performed. All requested quality gates passed; verified on 2026-10-04.

| Item | Requested topic | Implementation and evidence |
| --- | --- | --- |
| A | Architecture | A separate probability layer composes completed AFRE-5 models and exact AFRE-4 folds; point/foundation contracts remain intact. |
| B | Package structure | 17 modules separate contracts, families, queries, scale, fitting, forecasting, scoring/evaluation, storage, validation, lineage and engine. |
| C | Probabilistic schema | 1.0; all six prior schemas remain 1.0. |
| D | Engine/store versions | Engine 0.7.0; additive shared store 1.6 / SQLite user_version=7 from 1.5/u6. Strict ModelRepository remains 1.5 and emits historical 0.6.0 snapshots. |
| E | Distribution families | EMPIRICAL_RESIDUAL, GAUSSIAN_LOCATION_SCALE, QUANTILE_SET only; no unsupported family advertisements. |
| F | Probabilistic model spec | Exact point/fold/rich-target/cutoff, observation policy, centering, scale, quantile/event definitions, seed and implementation/approximation versions. |
| G | Fit-run identity | Ordered TRAIN response/residual evidence -> fit inputs -> distribution/artifact -> completed run. Explicit clocks and diagnostics; no hash cycle or implicit wall time. |
| H | Empirical residual distribution | All admitted TRAIN residuals are equal-mass sorted atoms including ties. RAW or recorded CENTER_MEAN. TRAIN_TARGETS gives unconditional empirical baseline with exact TRAIN-mean scaffold. |
| I | Gaussian location-scale | Point location plus TRAIN pool mean; unconditional target mean when declared. Fixed population STD, MAD-factor or positive supplied scale; no learned conditional scale. |
| J | Quantile-set forecasts | Sparse Type-7 empirical values only. No hidden CDF, survival, events, density, mean, variance, CRPS or NLL. Unsupported scores have typed states. |
| K | Scale estimators | Population denominator n; median absolute deviation times explicit positive factor; FIXED_SCALE>0. Continuous zero scale rejects atomically, no floor. Degenerate atoms/sparse quantiles explicit. |
| L | Quantile semantics | Unique sorted interior levels including 0.5. LINEAR_N_MINUS_ONE/type7-v1. Crossing rejects. Gaussian inverse domain [1e-12,1-1e-12]; sparse queries require exact stored levels. |
| M | Threshold probabilities | Explicit GT/GE/LT/LE with exact atom boundary semantics. Later truth indicator uses identical comparison; no implicit clipping. |
| N | Tail probabilities | Gaussian erfc upper/lower tails avoid subtraction cancellation; empirical finite atom tails exact. Complement/monotonicity/domain/extreme-tail regressions pass. |
| O | Conditional variance | Gaussian sigma², empirical population variance; sparse quantiles return unsupported None. Expected and median are distinct and explicit. |
| P | TRAIN-only fitting | Exact point-matrix TRAIN order/responses; blocked VALIDATION/TEST/PURGED/EMBARGOED/INELIGIBLE truth. Later cutoff excludes; equality admits. Held-out perturbation preserves fitted numeric state. |
| Q | Probabilistic availability | Fit follows base point/input availability; completion/state/model clocks ordered. OOS point/state/features/preprocessing <= origin cutoff. Later computation cannot pretend earlier physical observation. |
| R | Forecast contracts | Immutable model/base-point/target/input, full parameters, quantiles/events/moments, clocks and admissibility. Construction/publication deny TargetVintage, TrainingObservations and DesignMatrix reads. |
| S | Batch forecasting | Unique bounded requests sorted by origin/security/identity; reversed requests identical. Explicit pool-times-batch work budget and atomic publication. |
| T | NLL | Gaussian proper continuous log score computed directly in log space; negative finite values valid. No empirical pseudo-density. |
| U | CRPS | Analytic Gaussian erf form and exact equal-mass empirical step-CDF score; O(n) sorted positive terms, not fair-ensemble CRPS. Sparse quantiles unsupported. |
| V | Pinball loss | Exact per-level quantile loss, plus equal-weight mean over fixed declared levels. |
| W | Brier/event scores | Exact per-threshold squared probability error, plus declared-set mean. Binary event log loss/clipping not implemented. |
| X | Coverage/PIT diagnostics | Inclusive interval coverage/width, per-level frequency, sharpness, per-origin scores, right-CDF PIT and fixed-bin histogram. Discrete ties are nonrandomized; no fitted calibration transform. |
| Y | Distribution consistency | Finite values, nonnegative scale/variance, monotone quantiles/CDF, unit probabilities, exact complements/atom boundaries and semantic replay tested. |
| Z | Probabilistic comparisons | Candidate-minus-reference scores only on exact identical sample/target/truth sets, dataset/fold/horizon/scope/cutoff/protocol/exclusions/keys. Descriptive, never selection. |
| AA | TEST boundary | Existing AFRE-4 TestEvaluation identity/purpose/cutoff/reuse record retained. No missing identity, altered reuse cutoff or TEST relabeling. |
| AB | Distribution audits | Exact family/base-model/TRAIN evidence/residuals/centering/scale/levels/events/cutoff/availability/versions replayed. Bounds and unresolved/cyclic evidence fail. |
| AC | Forecast lineage | One depth/node/byte budget spans probability -> completed point fit -> fold/TRAIN features/vintages/targets. Forecast omits held-out truth; evaluation explicitly adds later truth. |
| AD | Persistence/migration | Five immutable probability tables. Upgrade6->7 preserves every previous row/DDL/metadata value. Injected migration and fit-publication failures rollback; future versions/tampering reject. |
| AE | Indexes/performance | Spec/base/family/fold/target, dataset/split/fit, security/origin/scope and evaluation-cutoff indexes; bounded history/reads. Offline reference profile complete; no SLA. |
| AF | Deterministic replay | Seeds 0/1/42/random, reversed upstream/TRAIN/request order and restart give byte-identical semantic artifacts on the supported Python/platform environment. |
| AG | Concurrency | A real second connection inserts a backdated feature correction and rebuilt point fit during the pinned uncertainty snapshot. Current fit unchanged; new rebuilt probability identity differs; old bytes preserved. |
| AH | Numerical correctness | Normal CDF max absolute error 2.78e-17; inverse 8.882e-16; Gaussian CRPS fixture 0 and independent quadrature 2.502e-13; empirical pairwise CRPS 0; Type-7/event atoms 0; Gaussian event 2.78e-17. |
| AI | Security | Closed canonical data-only artifacts; static type/enum registry, finite values, byte/depth/work limits, immutable SQL and hash/index checks. No executable payload/network/shell/runtime dependencies; tests block socket/DNS. |
| AJ | Documentation | Six new probability guides; README/master/model-fit/point-evaluation/model-replay/research-replay updated; exact 26-phase AFRE-0 through AFRE-25 roadmap retained. Historical completion reports untouched. |
| AK | Tests added | 145 new AFRE-6 tests; focused run 145 passed in 43.20s. Every prior test file remains byte-identical. |
| AL | Full pytest | 749 passed in 437.46s: all 604 prior tests plus 145 AFRE-6 tests. Full suite and four-seed children block socket construction and DNS. |
| AM | Coverage | Branch-enabled full-package coverage 99.04% combined (statement 99.48%, branch 97.08%); probability package 99.57% combined. Gate >=95% passed; no coverage configuration weakened. |
| AN | Ruff | Full-repository Ruff lint clean; format check 237 files unchanged. |
| AO | mypy | Strict full-repository mypy clean: 186 source files checked. |
| AP | Diff review | Complete tracked/addition review and git diff --check passed. Prior contract/test/report SHA-256 bytes unchanged. Only prior implementation adjustment pins strict ModelRepository snapshot metadata 0.6.0. |
| AQ | Secret/TODO scan | Repository script passed across 240 deliverables: secret, unfinished TODO/FIXME, whitespace and executable-data-boundary checks. Documentation script passed 51 documents, versions/links/reports and exact 26-phase roadmap. |
| AR | Benchmark/profile | Profile complete: two horizons, 8 securities, 128 dataset cells, 4 probability fits, 28 forecasts, 13 admitted TRAIN rows per fit, 13,053,952 disk bytes. Separate 4,000-residual kernels: fit 0.164s,14,000 quantiles 0.039s,6,000 probabilities 0.062s,200 paired proper scores 0.867s. Profiling overhead/local synthetic measurements; no production SLA. |
| AS | Dependencies | Zero runtime dependencies; no changes to dev dependency pins. Python 3.11+ standard library only. |
| AT | Remaining limitations | In-sample residual uncertainty may be optimistic; constant continuous estimated scale rejects; sparse quantiles imply no full law; no parametric heavy-tail family, dynamic scale, resampling, per-security or rolling calibrator. Embedded empirical pools and upstream canonical provenance limit scaling. Caller clocks are not authenticated; universal platform bit identity not promised. No profitability claim. |
| AU | Exact AFRE-7 scope | Forecast Calibration only: probability/quantile/interval calibration, causally valid isotonic-like/conformal-style mappings, rolling diagnostics, versioned calibration state/drift and strict TRAIN/calibration partition semantics; no regime mixtures. Not implemented. Stop after AFRE-6; no selection, ensembles, portfolios or execution. |

The architecture and conventions are documented in [probabilistic forecasting](probabilistic-forecasting.md),
[distributions](forecast-distributions.md), [quantiles](quantile-forecasts.md),
[events](threshold-probabilities.md), [proper scores](proper-scoring-rules.md) and
[evaluation](probabilistic-evaluation.md). The [demo](../examples/probabilistic_demo.py)
and [profile](../benchmarks/probabilistic.py) are offline and deterministic.

AFRE-6 evaluates calibration diagnostics but does NOT fit calibration transformations.
AFRE-7 owns Forecast Calibration. The frozen roadmap retains **26 distinct phases,
AFRE-0 through AFRE-25**. Portfolio construction, risk optimization and execution remain
downstream projects after AFRE; predictive metrics do not establish trading profitability.

## Final working-tree status

Branch `main`; unchanged HEAD `faa92a7` (Add statistical baseline models).
10 modified tracked files and 34 untracked new files; no staged files.
No commit or push performed. Stop after AFRE-6.

Modified tracked files: README.md; docs/AFRE_MASTER_SPEC.md;
docs/model-fit-semantics.md; docs/model-reproducibility.md;
docs/point-forecast-evaluation.md; docs/research-reproducibility.md; pyproject.toml;
scripts/check_documentation.py; src/afre/statistical_models/repository.py;
src/afre/version.py.

New files: all 17 modules in src/afre/probabilistic/, eight files in
tests/probabilistic/ (six test modules plus fixture/package files),
examples/probabilistic_demo.py, benchmarks/probabilistic.py, six probability guides
and this completion report. No prior tests, public contract files, historical
reports, old demos or old benchmark files changed. Runtime/development dependency
lists remain unchanged.

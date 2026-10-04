# AFRE-7 completion report — Forecast Calibration

AFRE-7 is complete in the working tree. AFRE-0 through AFRE-6 contracts, tests,
payloads and strict repository semantics are preserved. The sole AFRE-6 code
compatibility change pins its snapshot engine metadata at 0.7.0 as the global
engine advances. The frozen roadmap remains **26 distinct phases, AFRE-0 through
AFRE-25**. No commit or push is performed. AFRE-8 remains unimplemented.

| Item | Area | Implementation and evidence |
| --- | --- | --- |
| A | Architecture | Separate causal calibration above completed AFRE-6 raw models; immutable adjusted forecasts and independent later evaluation. Calibration sample is fit data. |
| B | Package structure | 21 modules in `src/afre/calibration`: schema, definitions, artifacts, partitions, samples, isotonic, probability, quantile, conformal, fitting, application, diagnostics, evaluation, drift, bounds, storage, repository, validation, lineage, engine and public exports. |
| C | Calibration schema | Closed data-only calibration schema 1.0. All earlier schemas remain 1.0. |
| D | Versions | Engine/package 0.8.0; shared calibration store 1.7 / SQLite user_version=8. Prior metadata and layouts remain intact. |
| E | Methods | IDENTITY, BINNED_PROBABILITY, ISOTONIC_PROBABILITY, QUANTILE_OFFSET, CONFORMAL_ABSOLUTE_RESIDUAL and ROLLING_CONFORMAL are implemented and tested. Asymmetric conformal is not advertised. |
| F | CalibrationSpec | Raw model/spec, rich target/horizon, method, reservation/range/policy, cutoff/minimum, fixed bins/events/levels/interval/alpha/window, tie/extrapolation/interpolation/statistic versions and seed are identity-bearing. |
| G | Samples | CalibrationObservation pins raw forecast, exact origin/stable instrument, sample and target IDs, truth/availability, cutoff, raw probabilities/quantiles/median/interval. Explicit requests preserve corrected-vintage identity. |
| H | Partition semantics | DEDICATED_CALIBRATION, TRAIN_TAIL and ROLLING_PAST use explicit reservations over unchanged AFRE-4 memberships. TRAIN tail uses a declared parent boundary and a base fold excluding that tail. |
| I | Overlap/disjointness | DISJOINT_FROM_MODEL_TRAIN, OVERLAPS_MODEL_TRAIN and UNKNOWN are typed. Supported fits require strict disjoint evidence; actual underlying TRAIN/TEST scopes and memberships are forbidden. |
| J | Identity | Exact raw probabilities/quantiles/intervals preserved, including applicable complete-distribution scores. |
| K | Binned probability | Fixed left-closed/right-open bins, last including 1, minimum count, empirical rate and RAW/FAIL sparse-bin policies. Exact counts/rates/source IDs persist. |
| L | Isotonic probability | Deterministic tie aggregation and integer-ratio PAV pooling. Exact ranges/counts/successes/rates/source IDs persist. Constant blocks, linear gaps and CLAMP_EDGE; O(n) pooling after sorting and logarithmic queries. |
| M | Quantile calibration | Type-7 empirical q-quantile of truth-minus-raw-q residuals. Exact level identity and persisted residual evidence; crossings fail during fit and application, without repair. |
| N | Conformal calibration | Absolute residual about raw median; one-based k=ceil((n+1)*(1-alpha)), exact decimal-alpha convention and q_hat=score[k-1]. k>n rejects. Symmetric center +/- q_hat interval. |
| O | Rolling calibration | Explicit last-N resolved eligible observations ordered origin/security/sample; future truth excluded before trailing selection, with explicit exclusions and new state per fit/cutoff/window. |
| P | CalibrationState | Immutable fit inputs/observations, raw model, target, mapping/offset/score IDs, diagnostics, sample IDs/overlap and fit clocks. Completed run required for application. |
| Q | Availability | Truth <= fit cutoff, including exact equality; state availability >= fit completion and every used truth/raw availability. Raw forecasts must have existed by origin cutoff. |
| R | CalibratedForecast | Separate artifact referencing exact raw forecast/state, adjusted marginals/interval, actual computation/availability, origin and historical admissibility. |
| S | Probability semantics | Event value plus GT/GE/LT/LE is exact; multiple events calibrate independently. No hidden sharing, complement representation or full calibrated CDF claim. |
| T | Quantile/interval semantics | Exact q identity; selected residual offsets; declared raw interval/nominal levels and separate conformal interval. Unselected raw quantities remain explicit. |
| U | Raw preservation | AFRE-6 rows/bytes unchanged; raw IDs remain recoverable. Guarded demo and six-method regressions verify preservation. |
| V | TEST prevention | Reservation and raw-fold TEST denied before calibration truth reads. Changing later TEST source outcomes leaves frozen calibration unchanged; TEST evaluation uses explicit AFRE-4 reuse evidence. |
| W | Diagnostics | Same-sample raw/calibrated Brier, fixed reliability bins/frequencies, quantile frequency/signed/absolute gaps, coverage/nominal/error/width. Fit diagnostics labeled retrospective; independent evaluation excludes fit samples. |
| X | ECE/MCE | ECE=count-weighted absolute bin gap; MCE=largest nonempty gap. Empty bins have null statistics/zero weight. Binning and sampling limitations documented. No Brier decomposition claimed. |
| Y | Coverage/sharpness | Empirical coverage and nominal gap reported separately from finite average width. Calibration, sharpness, discrimination, point accuracy and proper scores remain distinct. |
| Z | Proper scores | AFRE-6 raw scoring reused exactly. Calibrated Brier/pinball/interval coverage/width supported; identity Gaussian NLL/CRPS tested. Nonidentity full PDF/CDF NLL/CRPS/PIT/scale remain unsupported. |
| AA | Raw/calibrated comparison | Exact forecast/sample/target/value/exclusion/cutoff/protocol match required. Descriptive score deltas, absolute coverage-error delta and width delta; no automatic acceptance. |
| AB | Drift | Bounded historical evaluation windows, fixed thresholds/minimum and STABLE/DEGRADED/INSUFFICIENT_DATA/UNKNOWN. Brier, ECE, max quantile gap and interval gap; repeated window sample IDs reject. |
| AC | No auto-refit | Drift persists diagnostics only, never mutates state, creates fit, tunes methods or promotes a calibrator. No AFRE-22 model-health framework. |
| AD | Audits | Bounded semantic audit checks completed fits, exact causal evidence, mapping/offset/score replay, availability, output/scoring consistency and immutable relational indexes. |
| AE | Lineage | Calibrated forecast -> state -> spec/observations -> raw forecasts/models -> point fit/fold -> upstream feature/target evidence. Used calibration truth is past evidence; later deployment truth enters evaluation only. One node/depth/byte budget. |
| AF | Persistence/migration | Eight immutable tables, additive transactional 7->8 upgrade, success/rollback/future-version tests, atomic publication/retry/idempotence and corruption rejection. Every prior row/metadata/DDL is compared. |
| AG | Indexes/performance | Specs index raw model/spec/target/fold/method/cutoff; completed fit/state availability, raw/calibrated forecast origin/security, evaluation cutoff, exact event/level and drift window indexes. Explicit count/byte/work bounds. |
| AH | Replay | Seeds 0/1/42/random, reversed upstream/request order and restart produce identical state/forecast/evaluation/comparison bytes. Platform-universal float identity is not claimed. |
| AI | Concurrency | Snapshot hook inserts later corrected source/target through a second writer; current fit retains original exact targets and old state bytes. |
| AJ | Numerical correctness | Independent PAV oracle, exact tie/pooling/clamp/monotonicity, Type-7 offsets/crossing, finite rank and leave-one-out coverage, probability bounds, ECE/Brier/coverage fixtures. Profile errors: zero for PAV/rank/q_hat/coverage; residual offsets 2.22e-16 and ECE 5.55e-17. |
| AK | Security | Static closed structured-data contracts; no executable payloads, runtime network/shell/dynamic executable imports, pickle or provider-selected paths. Tests and replay workers block sockets/DNS. Hashes verify consistency rather than authenticate providers/admins. |
| AL | Documentation | Six dedicated calibration documents, README/master, splitting/reproducibility/probability evaluation updates, exact 26-phase roadmap and A–AW checker; demo and profile documented. |
| AM | Tests added | 136 new tests covering causal reservations/cutoffs/overlap/TEST, numerical methods, target-free application, raw bytes, proper scores/comparison/drift, migration/rollback/corruption/bounds, concurrency and deterministic replay. All 749 prior tests remain unchanged. |
| AN | Full pytest | 885 tests pass in the final full run (665.79 seconds), with sockets/DNS blocked throughout. Focused AFRE-7: 136 pass; all 749 prior tests remain green. |
| AO | Coverage | 99.08% combined statement/branch coverage in the final full run; >=95% gate passes. Branch instrumentation enabled; focused calibration previously 99%. |
| AP | Ruff | Complete repository lint and formatting checks pass; no suppressions added. |
| AQ | mypy | Strict complete-repository mypy passes, 218 source files. |
| AR | Diff review | Tracked and new files reviewed; prior code change limited to frozen AFRE-6 snapshot version plus additive global calibration version constants. Whitespace check passes; status is 10 modified tracked files and 40 new deliverables, all unstaged; HEAD remains 73e884e on main. |
| AS | Secret/unfinished-work scan | Existing secret/TODO/FIXME/unsafe-call/whitespace scan passes on 280 deliverables. Documentation checker passes 59 documents, local links, versions, historical reports and exact 26-phase roadmap. |
| AT | Benchmark/profile | 5,000 synthetic computational observations, four events/three levels, isotonic/conformal/offset kernels; separate fully causal persisted seven-observation calibration/seven deployment forecasts per method. Fit/application/evaluation/drift/audit/restart/storage measured; no production SLA. |
| AU | Dependencies | Zero runtime dependencies; stdlib only, Python 3.11+. Development dependency pins unchanged. |
| AV | Limitations | Strict disjoint policy only; no asymmetric conformal, adaptive bins, crossing repair, coherent nonidentity calibrated PDF/CDF, model selection or universal financial coverage guarantee. Profile persistence fixture is small; generated 5,000-row kernel workload is not causal store evidence. |
| AW | Exact AFRE-8 scope | Multi-Horizon Forecast Architecture: consistent declared horizons, shared versus horizon-specific parameters, horizon dependencies/joint identity, appropriate cross-horizon covariance and horizon-specific loss/evaluation. Deferred; no regimes/mixtures/selection/ensembles/portfolios/execution added. |

## Validation record

Final full run: **885 passed; 99.08% combined statement/branch coverage**, sockets
and DNS blocked. Full Ruff lint/format and strict mypy pass; whitespace, repository
secret/unfinished-work and documentation consistency scans pass. All prior test and
contract files are byte-identical to the baseline. The demo completes its causal,
TEST-isolation, truth-free application, corrected-truth and restart checks. The
5,000-observation offline profile completes with numeric errors <=2.23e-16.
Additional forged conformal-score/quantile-offset publication checks fail closed
and roll back even when given valid new content hashes.

Git status: main at **73e884e**, 10 modified tracked files and 40 new deliverables;
no staged changes, no commit and no push. See
[calibration](forecast-calibration.md) and [offline profile](calibration-profile.md).

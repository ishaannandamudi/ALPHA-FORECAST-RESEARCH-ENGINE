# AFRE-15 completion report

**AFRE-15 complete. All 44 quality gates pass.** No commit or push performed.
Baseline/current HEAD `f326d88`; AFRE-0 through AFRE-14 implementations and tests are preserved.
Current target: engine0.16.0, uncertainty1.0, store1.15/user_version16, zero runtime dependencies.
Frozen roadmap:26 distinct phases, AFRE-0 through AFRE-25. Stop after AFRE-15.

## Required A–BM items

| Item | Topic | Result and evidence |
| --- | --- | --- |
| A | Architecture | Immutable descriptive uncertainty layer over exact native sources; separate TRAIN estimator, target-free construction, later assessment and audit. |
| B | Package structure | 20 focused modules in src/afre/uncertainty; numerical/source/persistence/evaluation concerns are separated. |
| C | Schema | Uncertainty1.0; every earlier public schema remains1.0. |
| D | Versions | Engine0.16.0; additive shared store1.15; SQLite user_version16, transactional15→16. |
| E | Component types | TOTAL_PREDICTIVE, ALEATORIC, PARAMETER, MODEL_SPECIFICATION, EXPERT_DISAGREEMENT, WITHIN_EXPERT_PREDICTIVE, REGIME_AMBIGUITY, EVENT_AMBIGUITY, DATA_QUALITY, HORIZON, RESIDUAL_UNATTRIBUTED. |
| F | Identifiability | Seven typed statuses; unavailable/incompatible/unidentifiable/insufficient states have no numerical payload. |
| G | Measures | Variance, standard deviation, interval width, entropy, disagreement, score variance, quality penalty. Incompatible measures reject or carry explicit status; no mixing units. |
| H | Total predictive uncertainty | Exact finite-law moment where available; point/sparse/calibrated marginals alone do not identify variance. |
| I | Gaussian | Exact sigma²; native declared Gaussian quantile approximation for intervals. |
| J | Empirical | Finite empirical population variance denominatorN, including declared degenerate atoms; Type7 intervals. |
| K | Mixture identity | Exact native finite-law within+between=total; no expert independence assumption or quantile averaging. |
| L | Aleatoric semantics | OLS SSE/(N−rank) noise is partially identified only under declared fixed-design iid homoskedastic correct-model assumptions. Predictive or within-expert variance is not automatically aleatoric. |
| M | Parameter uncertainty | Frozen analytic OLS covariance; xᵀCov(beta)x. No bootstrap, jackknife, posterior or Hessian surrogate. |
| N | Model specification | Distinct explicitly supplied matched models; equal-weight prediction spread is PROXY_ONLY. No selector. |
| O | Expert disagreement | Exact finite-mixture between term; point expert weighted variance/pairwise absolute disagreement are proxies. Disagreement is not automatically epistemic. |
| P | Regime ambiguity | Supplied membership entropy in nats; weighted TRAIN fitted-state mean spread is an attribution proxy. Missing active fits explicit. |
| Q | Event ambiguity | Conditioned-vs-base absolute shift proxy; no event-state probability model or invented variance. |
| R | Data quality | Retain source/conditioning/expert/sequence/calibration states/cohorts; no configured numerical penalty mapping or variance conversion. |
| S | Horizon uncertainty | Exact independent target/horizon identity, no proportional time scaling or joint-law inference. |
| T | UncertaintySpec | Exact source/target, requests/measures, closure, covariance/alternatives, interval levels, counts, tolerance, seed, implementation/identifiability/calibration policy. |
| U | Components | Immutable type/measure/value/units/status/method/reason/source and sample evidence/additivity/availability. |
| V | Decomposition | Exact security/origin/target/horizon/sample/fold/partition/source/components/interval/total/closure/shares/quality/computation. |
| W | Closure | Only compatible finite-mixture identity permits EXACT_ADDITIVE; approximate additive methods unsupported; diagnostics non-additive. |
| X | Residual | Explicit compatible total−terms remainder only; no arbitrary percentages or silent negative clamp. Tiny negative residual also rejects. |
| Y | Availability | Every native source/covariance/alternative and actual computation must be available by origin cutoff. No new historical-delivery permission/backdating. |
| Z | Target-free | Construction denies TargetVintage and response-bearing matrices/datasets even through resolve caches. Full audit and later evaluation may read truth. |
| AA | TRAIN estimators | Pinned model/design/normalization and admitted exact TRAIN samples; held-out response reads excluded. |
| AB | TEST boundary | Explicit native TEST access identity, exact reuse semantics; no TEST fitting/calibration/tuning/selection API. Caller-supplied policies remain declarations, not proof of human pre-registration. |
| AC | Intervals | Gaussian approximation, empirical Type7, explicit sparse levels or compatible stored calibrated levels; mixture quantiles unsupported; exact width/endpoints. |
| AD | Calibration | Reuse AFRE-7 stored semantics. Marginals do not invent a full law; reliability does not identify causal sources. |
| AE | Coverage | Nominal/empirical/signed error/count separately, inclusive interval endpoints, minimum counts and horizon/event/regime/quality/expert cohorts. |
| AF | Sharpness | Mean width and mean predictive variance separately from coverage/proper scores; no opaque combined score. |
| AG | Linear covariance | Pivoted Householder QR and triangular inverse, full-rank/condition gate, fixed intercept policy, SSE/(N−p). Ridge/lasso/constants/within-origin intercept unsupported. |
| AH | Prediction variance | Frozen covariance and exact causal design vector including global intercept, or excluding no-intercept; independent quadratic-form oracle. |
| AI | Nonlinear limits | Unpenalized fixed transformed-column linear readout only; no tree/ridge epistemic claim or transform-selection uncertainty. |
| AJ | Sequence | Unpenalized fixed temporal readout covariance, conditional on fixed dynamics/normalization; hidden-dynamics/model-search uncertainty unestimated. |
| AK | Event source | Exact native event source/law where compatible, absolute shift proxy and event class/subtype cohorts. |
| AL | Regime source | Hard/soft/fallback source states, supplied membership semantics and source law preserved without invented joint law. |
| AM | Mixture source | Native full law/exact identity or point disagreement diagnostics; quality and unavailable experts retained. |
| AN | Cross-sectional | Existing rank semantics preserved; no uncertainty adjustment, allocation or orthogonalization. |
| AO | Multi-horizon | Actual independent1h/1d fixtures; per-horizon source metadata, no artificial time scaling/cross-horizon joint distribution. |
| AP | Error diagnostics | Native Pearson/Spearman vs realized absolute/squared error, explicit zero-dispersion/minimum states; descriptive monotonic bucket errors. |
| AQ | Buckets | Deterministic ordinal equal-count variance/sample-ID rank buckets; ties may split with stable assignment. |
| AR | Drift | Ordered disjoint known windows; variance shifts, coverage errors, error correlation and exact additive share means. |
| AS | No auto-refit | Drift/comparison/evaluation never retrain calibrators/models, tune mappings or select methods. |
| AT | Audit | Unified bounded semantic audit answers exact source/evidence/assumptions/closure/status/quality/horizon/availability and later truth/TEST provenance. |
| AU | Lineage | Components/specs/law/models/design/TRAIN/calibration/completed fits/sample/target/horizon and later assessment. TargetDefinition embeds exact horizon; horizon indexed without inventing a standalone registry record. |
| AV | Persistence/migration | Canonical immutable data-only records, additive15→16, preserved prior DDL/metadata/rows, rollback/future rejection, semantic and projection corruption tests. |
| AW | Indexes/performance | Forecast/source, component/measure/status, target/horizon, security/origin, availability/cutoff/TEST and reverse references; explicit resource bounds. |
| AX | Replay | Hash seeds0/1/42/random, source/component/request reversal, fresh process and restart; canonical byte comparison. |
| AY | Concurrency | Real second SQLite writer inserts forecast/model/target corrections during pinned read hooks. Frozen construction/fit/evaluation remains identical. |
| AZ | Numerical correctness | Independent variance/mixture/state/expert/OLS/quadratic/closure/coverage/correlation/bucket fixtures. Profile maximum absolute covariance/prediction oracle error3.308722450212111e−24. |
| BA | Security | Zero runtime dependencies; closed structured deserialization; static/runtime guards exclude executable payloads, network, shell, dynamic imports and provider paths. |
| BB | Documentation | Eight required guides plus profile/report/validation evidence; README/master and14 existing integration/reproducibility/roadmap guides updated. Frozen26-phase roadmap AFRE-0 through AFRE-25. Complete65-entry A–BM report. |
| BC | Tests added | 159 new tests. Migration/corruption/bounds, numerical identities, source integration, causality/held-out isolation, real second-writer concurrency, four hash seeds/order/restart, evaluation and security. Every earlier test file is byte-identical to baseline. |
| BD | Full pytest | 2,063 passed, zero failures in 1,659.48s (27:39). Completed saved run verified and reused; no expensive gate repeated. |
| BE | Coverage | 2,063 passed in 2,977.50s (49:37), branch coverage enabled. Combined 98.892234%; statements 99.401422%; branches 96.485411%. 21,256/21,384 statements and 4,365/4,524 branches covered. New uncertainty package 98.619547% combined; required combined≥95% passes. |
| BF | Ruff | Full Ruff lint and format PASS; 633 files already formatted. Rerun after reporting-only checker correction. |
| BG | Mypy | Strict full repository mypy PASS, 501 source files; no typing configuration loosened. Rerun after reporting-only checker correction. |
| BH | Diff review | All runtime/test/config fingerprints match full-gate inputs. 501/502 total frozen files unchanged; one documentation-check status string corrected from61 to65 report entries after tests. Exact checker assertions unchanged; no tests invoke that script. Earlier contracts/tests preserved; only earlier runtime change is version metadata. |
| BI | Scans | Scripted repository secret/TODO/FIXME/whitespace and documentation/roadmap/version/link checks PASS, rerun on final report/evidence. |
| BJ | Profile | Recorded bounded offline profile: 48 decompositions,11 source families,3 covariance estimates,12 TRAIN rows each,44 evaluation pairs,309 audit nodes,748 uncertainty artifacts,1,476,071 canonical bytes,25,010,176 closed SQLite bytes. Fixture26.035s, evaluation1.362s, audit0.818s, restart0.198s. Arithmetic repetitions separate; no production SLA. |
| BK | Dependencies | Python3.11+ stdlib runtime; pyproject dependencies=[]; existing pinned dev tools unchanged. |
| BL | Limits | No complete causal aleatoric/epistemic split; no ridge/tree/dynamics posterior, bootstrap, penalty mapping, mixture quantiles, approximate additive method, significance/model selection, horizon joint law or production SLA. Provider timestamps/derivation remain supplied trust boundaries. |
| BM | Exact next scope | AFRE-16 Signal Orthogonalization & Redundancy Analysis: signal residualization/projection, pairwise/multivariate redundancy, partial correlation, incremental explanatory value, collinearity, orthogonal signals, cross-sectional/temporal redundancy. No invariance framework yet. No AFRE-16 code implemented. |

## Quality gates

| Gate | Check | Result |
| --- | --- | --- |
| 1 | Focused AFRE-15 tests | PASS: 159 focused tests,361.61s |
| 2 | Full pytest | PASS: 2,063 tests,1,659.48s |
| 3 | Branch-enabled combined coverage≥95% | PASS: 98.892234% combined |
| 4 | Socket/DNS-blocked full suite | PASS: Both full suites use seven autouse socket/DNS denials |
| 5 | Ruff lint | PASS: Full ruff check . |
| 6 | Ruff format | PASS: 633 files formatted |
| 7 | Strict mypy | PASS: Strict mypy,501 files |
| 8 | git diff --check | PASS: git diff --check |
| 9 | Git status/diff/hash review | PASS: Review and frozen runtime/tests/config; one reporting-only checker message correction |
| 10 | Secret scan | PASS: scripts/check_repository.py |
| 11 | TODO/FIXME scan | PASS: scripts/check_repository.py |
| 12 | Migration success/rollback/future | PASS: Migration success/prior preservation/rollback/future rejection |
| 13 | Corruption | PASS: Semantic and SQL family/schema/hash/index/link/orphan/metadata/DDL tests |
| 14 | Bounds | PASS: Hard/caller bounds, numerical dimensions and source/lineage limits |
| 15 | Hash-seed determinism | PASS: Hash seeds0/1/42/random fresh processes |
| 16 | Insertion-order determinism | PASS: Reversed source/component/request order |
| 17 | Restart replay | PASS: Fresh-process canonical bytes and demo restart |
| 18 | Concurrency | PASS: Actual second SQLite forecast/model/target writer hooks |
| 19 | Gaussian variance fixture | PASS: Known exact Gaussian sigma² |
| 20 | Empirical variance fixture | PASS: Known population empirical variance including degeneracy |
| 21 | Mixture closure | PASS: Independent finite-mixture within/between oracle and exact closure |
| 22 | Disagreement labels | PASS: Mixture disagreement identified mathematically; point spread proxy; no automatic epistemic label |
| 23 | Soft-regime ambiguity | PASS: Supplied membership entropy and state-mean spread oracle |
| 24 | Parameter covariance | PASS: Independent QR/OLS covariance and prediction quadratic-form oracles |
| 25 | Rank deficiency | PASS: Actual deficient/unstable/invalid design fixtures |
| 26 | Ridge semantics | PASS: Ridge covariance explicitly incompatible |
| 27 | Tree limitation | PASS: Tree parameter uncertainty unavailable/unidentifiable |
| 28 | Data-quality separation | PASS: Retained quality states without numerical mapping |
| 29 | Closure/negative residual | PASS: Partial identity, forged closure and negative residual rejection |
| 30 | Target-free construction | PASS: All11 source families deny truth/response reads; cached guard |
| 31 | Held-out isolation | PASS: Held-out target reads forbidden during covariance fit |
| 32 | TEST boundary | PASS: Native TEST seals/reuse, TRAIN-only estimators, target-free TEST application |
| 33 | Coverage/sharpness | PASS: Separate coverage/sharpness/minimum counts |
| 34 | Uncertainty-error correlation | PASS: Independent Pearson/Spearman and undefined states |
| 35 | Buckets | PASS: Stable equal-count rank/tie/order buckets |
| 36 | Horizon identity | PASS: Actual independent1h/1d target/horizon fixtures |
| 37 | Source-family integration | PASS: 11 native sources including calibrated compatibility |
| 38 | No-direct external engines | PASS: Static/stdlib boundary tests; no direct sibling imports |
| 39 | Drift | PASS: Ordered disjoint known-window drift |
| 40 | No auto-refit | PASS: Diagnostics preserve frozen estimators; no refit/selector API |
| 41 | Documentation consistency | PASS: 26-phase AFRE-0 through AFRE-25; versions/links/all65 A–BM entries/stale deferrals |
| 42 | 35-step offline demo | PASS: 35 steps offline;310 TEST-lineage nodes |
| 43 | Bounded profile | PASS: Bounded profile; independent maximum error3.308722450212111e−24 |
| 44 | Dependency check | PASS: dependencies=[]; original dev tools unchanged |

## Reviewable deliverables

Runtime:src/afre/uncertainty(20modules), version metadata and pyproject version only.
Examples:uncertainty fixture, independent oracles, actual horizon fixture and35-step demo.
Tests:tests/uncertainty. Profile:benchmarks/uncertainty_profile.py and docs/uncertainty-profile.json.
Documentation: eight required guides plus profile/report/validation evidence; README/master,
14 existing integration/reproducibility/roadmap guides and scripts/check_documentation.py. Existing tests and source contracts have not been rewritten.

Predictive uncertainty does not imply profitability. Quality diagnostics are not variance;
disagreement is not automatically epistemic; calibration is separate from sharpness and causal
uncertainty identification. Portfolio construction, risk optimization and execution remain
downstream projects after AFRE. There is no direct external-engine dependency.

## Final validation evidence

[Machine-readable validation](uncertainty-validation.json) retains exact counts, durations,
network-denial entry points, baseline/current HEAD and all502 original gate-input fingerprints.
The ordinary and branch-enabled full suites completed while disconnected. Their saved results
were verified and reused; no implementation or expensive test gate was restarted.

Runtime, examples, tests, benchmark code and configuration still match the full-gate inputs.
Only the documentation check's status message changed from61 to65 A–BM entries after those
runs; its exact label assertions stayed unchanged. Static gates were repeated for that correction.

Overall combined coverage is98.892234%(required≥95%), with99.401422% statements and96.485411%
branches. The uncertainty package is98.619547% combined. No coverage exclusions or relaxed
assertions/configuration were introduced. Every AFRE-0–14 test and prior runtime contract
matches baseline; only src/afre/version.py changes earlier runtime metadata.

Git status: main...origin/main;19 tracked files modified and49 new files untracked, including
validation evidence. All changes are unstaged. HEAD remainsf326d88. No commit or push.

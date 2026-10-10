# AFRE-21 completion report

Completed 2026-10-10 (America/New_York). All applicable quality gates passed. Changes remain uncommitted and unstaged; no push. AFRE-22 and later phases are not implemented.

Baseline: 4e84f82; 2,813 prior tests. Frozen roadmap: 26 distinct phases, AFRE-0 through AFRE-25. AFRE-0 through AFRE-21 complete; AFRE-22 next.

| Item | Scope | Result |
| --- | --- | --- |
| A | architecture | Dedicated typed fusion layer; immutable sources, specs, fitted state, outputs and separate diagnostics. |
| B | package structure | 25 focused modules under src/afre/fusion; separate fixtures, demo, profile and tests/fusion. |
| C | schema | Fusion schema 1.0; all earlier public schemas retain 1.0. |
| D | engine/store versions | Engine 0.22.0; store 1.21; SQLite user_version=22; Python 3.11+. |
| E | source references | Exact source family, logical producer, artifact/version/provider, model/spec, target/horizon/kind/unit/calibration and anchor output. |
| F | supported source families | Native AFRE-5/6/7/10/11/12/13/14/16 and neutral external scalar/forecast boundaries. |
| G | output kinds | POINT, PROBABILISTIC, SCALAR_SIGNAL; exact semantics; explicit native probability-to-point adapter. |
| H | FusionSpec | Identity-bearing source grid, fold, target, clocks, policies, bounds, seed, implementation and optional upstream selection context. |
| I | fusion families | Fixed point, unconstrained learned linear point, fixed probability mixture, fixed scalar signal blend. |
| J | fixed-weight semantics | Finite explicit SIMPLEX or SIGNED_LINEAR weights; fixed declaration precedes held-out assessment. |
| K | weight normalization | NONE or explicit simplex normalization; TRAIN_STANDARDIZE is fixed signal preprocessing with frozen TRAIN centers/scales. |
| L | learned point weights | Native deterministic pivoted Householder QR; unconstrained coefficients with optional intercept. |
| M | TRAIN evidence | Complete admitted TRAIN sample/observation/target witnesses; causal out-of-sample source predictions; globally sealed TEST excluded. |
| N | stacking support/limitations | StackedPoint unsupported. Future stacking must use out-of-fold or properly nested historical predictions; in-sample base predictions rejected. |
| O | intercept semantics | WITH_INTERCEPT or NO_INTERCEPT; fixed value explicit; learned intercept estimated only on TRAIN. |
| P | weight constraints | No simplex-constrained learning or hidden ridge. Unconstrained QR is labeled honestly. |
| Q | source compatibility | Exact target/horizon/kind/unit/sample/origin/fold grids; incompatible or late inputs fail closed. |
| R | calibration compatibility | Exact calibrated state retained in provenance; no implicit recalibration or claim of mixture calibration. |
| S | point fusion | Explicit intercept plus weighted scalar contributions; independent fixed fixture. |
| T | probabilistic fusion | Finite exact Gaussian/empirical mixture preserving native law parameters and component lineage. |
| U | probabilistic weights | Nonnegative simplex only; signed probability weights rejected. |
| V | Gaussian mixture semantics | Gaussian components remain an explicit Gaussian mixture; never collapsed. |
| W | empirical mixture semantics | Weighted finite empirical components/atoms remain explicit; density/NLL unavailable. |
| X | quantile-only handling | Quantile-only full-law fusion is INCOMPATIBLE; no fabricated CDF. |
| Y | threshold probabilities | Exact weighted strict exceedance with native empirical tie convention. |
| Z | expectation | Exact finite weighted expectations; probability observation scalar is law expectation. |
| AA | variance | Exact within plus between variance; independent Gaussian/empirical oracle. |
| AB | mixture quantiles | Mixture quantiles explicitly unavailable; no source-quantile averaging. |
| AC | signal fusion | Fixed scalar blend with exact units; no automatic neutralization or target interpretation. |
| AD | signal standardization | Population center/scale fitted on complete TRAIN only; dimensionless output; constant columns fail. |
| AE | source-set identity | Canonical ordered source IDs, weights, rows and requests; identity independent of insertion order. |
| AF | duplicate handling | Duplicate logical producers require explicit distinct versions; identical producer/version duplication still rejected. |
| AG | missing-source policies | FAIL, fixed-simplex DROP_AND_RENORMALIZE or exact USE_DECLARED_FALLBACK. |
| AH | drop-and-renormalize | Surviving nonnegative weights explicitly divide by their positive sum; no intercept; recorded per sample. |
| AI | learned missingness | No learned column deletion or zero filling; unavailable or declared fallback only. |
| AJ | fallback sources | Exact source/sample/origin fallback; weight one, actual intercept zero. Standardized fallback bridge unsupported. |
| AK | FusionArtifact | Frozen coefficients/intercept/transforms, exact TRAIN rows, numerical diagnostics, fit/computation/availability and assumptions. |
| AL | FusedForecast | Exact security/sample/origin/target/horizon/unit/fold, inputs, effective contributions/status/law and availability. |
| AM | target-free application | Mandatory feature-only application; TargetVintage guards precede get/resolve/get_any native caches. |
| AN | availability | Final fused availability includes artifact, computation and actually used inputs and cannot exceed origin cutoff. External publication is not AFRE receipt. |
| AO | learned-artifact availability | Fitted artifact must be available by use origin; source artifact availability separately enforced. |
| AP | AFRE-20 integration | Optional fusion-candidate AFRE-20 adapter unsupported. Explicit upstream SelectionResult context may name an actual contributor; no hidden reselection. |
| AQ | AFRE-19 integration | Native AFRE-19 hypothesis/trial/family pool; all supplied rules and failed attempts remain represented. |
| AR | contribution diagnostics | Per-source original/effective weights, transformed value and additive weighted value; intercept_used stored. |
| AS | contribution reconstruction | Point contributions plus actual intercept reconstruct exact output; independent error reported. |
| AT | probabilistic contribution semantics | Mixture component weights/laws are probability contributions, not additive realized returns. |
| AU | diversity diagnostics | Descriptive prediction Pearson/Spearman, absolute disagreement and sign agreement; diversity is not quality. |
| AV | diversity matrix | Exact common source/sample intersection, explicit missing exclusions and native constant/insufficient states. |
| AW | error diversity | Later pinned truth cutoff permits exact error correlation; unsealed TEST error diversity unsupported. |
| AX | ensemble-vs-component evaluation | Fused and every contributor share exact truth/sample intersection; explicit exclusions and native point/probability/IC conventions. |
| AY | metric deltas | Fused-minus-component; negative error delta better, positive R-squared delta better; no significance or profit inference. |
| AZ | source dominance | Normalized absolute-weight dominance is descriptive. |
| BA | effective source count | Simplex effective count 1/sum(w*w); signed rules unavailable. |
| BB | weight entropy | Simplex entropy -sum(w log w), omitting zeros; signed rules unavailable. |
| BC | weight stability | Ranges, sign stability and concentration for explicitly supplied compatible frozen fits; no rolling automation. |
| BD | event source integration | Actual AFRE-10 native event forecast accepted unchanged. |
| BE | regime source integration | Actual AFRE-11 hard-regime output accepted unchanged. |
| BF | mixture source integration | Actual AFRE-12 gate/experts remain frozen; nested mixture flattened exactly. |
| BG | nonlinear source integration | Actual AFRE-13 nonlinear forecast accepted unchanged. |
| BH | sequence source integration | Actual AFRE-14 sequence forecast accepted unchanged. |
| BI | uncertainty metadata | Separate exact AFRE-15 decomposition attachment cannot change weights. |
| BJ | orthogonal signal integration | Actual explicitly supplied AFRE-16 residual/projection accepted; no implicit residualization. |
| BK | stability metadata | Separate exact AFRE-17 EnvironmentMetric target/horizon/sample/output attachment; no weight changes. |
| BL | cost-aware evaluation | Native AFRE-18 hypothetical evaluation accepts target-unit fused returns; explicit costs/exposure, no portfolio or execution. |
| BM | multiple-testing accounting | Every inspected rule is a trial; atomic pool publication prevents partial native plan rows; failed protocol anchors explicit. |
| BN | model-selection boundary | AFRE-20 owns candidate selection. No alternative fusion selector or post-VALIDATION winner authority exists. |
| BO | source-subset search limitations | Source-subset optimization, adaptive weighting and continuous/random/Bayesian fusion search unsupported. |
| BP | multi-horizon treatment | Actual 1h/1d native fusion has separate source/spec/artifact/target/horizon identities; no joint law. |
| BQ | cross-sectional signal fusion | Explicit scalar sources can be blended cross-sectionally; no implicit portfolio allocation. |
| BR | rank-signal handling | Ordinal ranks require an explicit scalar unit; never silently treated as returns/probabilities. |
| BS | calibration boundary | Calibration state preserved; automatic calibration transformation/selection of fusion unsupported. |
| BT | fitted-weight artifact | All fitted weight state persisted as canonical data and numerically replayed. |
| BU | rank deficiency | Explicit native QR rank-deficiency failure; no hidden regularization. |
| BV | condition threshold | Pinned QR condition-proxy limit rejects near-collinearity; not an exact matrix condition number. |
| BW | negative weights | Signed point/signal linear rules and unconstrained learned weights only; never probability mixtures. |
| BX | TEST boundary | No TEST fitting/tuning. Single predeclared final artifact chosen by TRAIN cutoff; native TestEvaluation seal required for TEST truth. |
| BY | audit | Bounded replayable root graph with exact sources, fitting, contributions, trial/selection/TEST evidence and limitations. |
| BZ | lineage | Fusion and native edges retain exact fitted/source/truth context; unrelated TEST truth not expanded into application lineage. |
| CA | persistence/migration | Transactional additive 21→22 migration; prior DDL/metadata/rows preserved; rollback/future version and immutability verified. |
| CB | indexes/performance | Static artifact/spec/source/security-origin/target-horizon/family/cutoff/availability/trial/selection and link indexes; measured bounded profile. |
| CC | deterministic replay | Fresh interpreters seeds 0/1/42/random, reversed source/sample/spec/request order and restart compare semantic bytes. |
| CD | concurrency | Actual separate-thread SQLite writer changes source, target and spec while evaluation snapshot remains fixed. |
| CE | numerical correctness | Independent fixed, known QR coefficients, contributions, Gaussian/empirical laws, vector diversity and metric/delta oracles. |
| CF | security | Canonical data only; no executable definitions, runtime networking, shell, pickle/joblib or provider-selected paths. |
| CG | documentation | Eight new fusion guides; README/master and selection, testing, uncertainty, residual, stability, costs and reproducibility guides updated. |
| CH | tests added | 88 added AFRE-21 tests cover numerical semantics, causal availability/reconstruction, guards, native/context, bounds, corruption, migration, concurrency and replay; all passed in the full run. |
| CI | full pytest | PASS: 2,901 tests, including 2,813 prior tests and 88 AFRE-21 tests; zero failures/errors/skips; 8,844.64 seconds (2h 27m 24s). |
| CJ | coverage | PASS: 98.5016% combined with branches enabled; statements 29,802/30,073 (99.0989%); branches 6,026/6,300 (95.6508%). |
| CK | Ruff | Full repository Ruff lint and format clean. |
| CL | mypy | Strict mypy all src/examples/benchmarks/tests/scripts clean. |
| CM | diff review | Complete tracked and new-file diff reviewed; prior phase tests unchanged; only internal fusion adapters extend earlier implementations. |
| CN | secret/TODO scan | Scripted scan passed for 946 deliverables: secrets, TODO/FIXME, executable-data and whitespace; no direct external-engine dependency. |
| CO | benchmark/profile | Bounded offline profile measures actual resolution/fixed/learned/application/probability/diversity/evaluation/audit/SQLite backup/restart/storage; no SLA. |
| CP | dependencies | Zero runtime dependencies; pinned development dependencies unchanged. |
| CQ | remaining limitations | No stacking, constrained learning, ridge, mixture quantiles, empirical density, automatic calibration, fusion-candidate selection adapter, subset search or health/promotion. |
| CR | exact AFRE-22 scope | AFRE-22 Drift, Decay & Model Health: input/prediction/calibration/residual drift, signal/coefficient/weight decay, windows and warning/degraded states; no automatic production replacement. Not implemented. |

## Quality gates

| Gate | Check | Result |
| --- | --- | --- |
| 1 | focused AFRE-21 tests | PASS — all 88 focused tests; affected regressions and fresh replay rechecked |
| 2 | full pytest | PASS — 2,901 tests; zero failures/errors/skips |
| 3 | branch-enabled combined coverage >=95% | PASS — 98.5016% combined; statements 99.0989%; branches 95.6508% |
| 4 | socket/DNS blocked full suite | PASS — network guards installed before AFRE imports and inherited by fresh Python children; child DNS-denial probe passed |
| 5 | Ruff lint | PASS — full repository Ruff lint |
| 6 | Ruff format | PASS — 928 files formatted |
| 7 | strict mypy | PASS — strict mypy, 742 source files |
| 8 | git diff --check | PASS — final working-tree whitespace check |
| 9 | full status/diff review | PASS — complete diff; prior tests unchanged; 17 modified tracked files and 54 new files |
| 10 | secret scan | PASS — scripted repository scan |
| 11 | TODO/FIXME scan | PASS — scripted repository scan |
| 12 | migration success/rollback/future-schema | PASS — focused tests and final static review |
| 13 | corruption | PASS — focused tests and final static review |
| 14 | bounds | PASS — focused tests and final static review |
| 15 | hash-seed determinism | PASS — focused tests and final static review |
| 16 | insertion-order determinism | PASS — focused tests and final static review |
| 17 | restart replay | PASS — focused tests and final static review |
| 18 | concurrency | PASS — focused tests and final static review |
| 19 | fixed point fusion | PASS — focused tests and final static review |
| 20 | weight-sum semantics | PASS — focused tests and final static review |
| 21 | learned linear fusion | PASS — focused tests and final static review |
| 22 | target-free application | PASS — focused tests and final static review |
| 23 | held-out isolation | PASS — focused tests and final static review |
| 24 | rank-deficiency handling | PASS — focused tests and final static review |
| 25 | condition threshold | PASS — focused tests and final static review |
| 26 | Gaussian mixture | PASS — focused tests and final static review |
| 27 | no Gaussian collapse | PASS — focused tests and final static review |
| 28 | quantile-only incompatibility | PASS — focused tests and final static review |
| 29 | threshold probability | PASS — focused tests and final static review |
| 30 | missing FAIL | PASS — focused tests and final static review |
| 31 | drop-and-renormalize | PASS — focused tests and final static review |
| 32 | learned missingness handling | PASS — focused tests and final static review |
| 33 | contribution reconstruction | PASS — focused tests and final static review |
| 34 | diversity matrix | PASS — focused tests and final static review |
| 35 | common sample intersection | PASS — focused tests and final static review |
| 36 | fused-vs-component evaluation | PASS — focused tests and final static review |
| 37 | event/regime/mixture/nonlinear/sequence source integration | PASS — focused tests and final static review |
| 38 | AFRE-16 residual integration | PASS — focused tests and final static review |
| 39 | AFRE-15 metadata separation | PASS — focused tests and final static review |
| 40 | AFRE-19 trial accounting | PASS — focused tests and final static review |
| 41 | AFRE-20 selection integration if implemented | NOT APPLICABLE — optional fusion-candidate AFRE-20 adapter unsupported; selection boundary/no-selector tests PASS |
| 42 | TEST boundary | PASS — focused tests and final static review |
| 43 | actual1h/1d identity | PASS — focused tests and final static review |
| 44 | corrected source identity | PASS — focused tests and final static review |
| 45 | no-direct external-engine regressions | PASS — focused tests and final static review |
| 46 | docs consistency | PASS — 186 documents, exact 26-phase roadmap, versions/links and historical reports |
| 47 | demo | PASS — 41 offline steps; maximum numerical error 1.5987211554602254e-13 |
| 48 | benchmark/profile | PASS — measured offline profile; 18 unique application rows, 9 security/origins, no SLA |
| 49 | dependency check | PASS — zero runtime dependencies; pinned development dependencies unchanged |

## Evidence and limits

The [41-step demo](ensemble-signal-fusion.md), [measured profile](fusion-profile.json), [source semantics](fusion-sources.md), [evaluation boundary](fusion-evaluation.md) and focused tests provide concrete evidence. Native demo graphs use separate temporary stores to avoid conflicts among earlier fixtures that reuse security/universe identities.

The 41-step demo reports maximum numerical error 1.5987211554602254e-13. Diversity Spearman error is 2.220446049250313e-16; fixed/contribution/mixture expectation/variance/threshold and metric/delta fixture errors are zero. The frozen full suite passed all 2,901 tests with 98.5016% combined coverage (99.0989% statements; 95.6508% branches). The final freeze pins 744 code/test/config files; the full gate verified all their SHA-256 hashes before and after execution with zero changes. Diversity, metric deltas and hypothetical cost evaluation establish no trading profitability. Portfolio construction, risk optimization and execution remain downstream projects. No automatic production replacement or promotion exists.

Non-target-unit scalar blends (including dimensionless standardized and ordinal rank signals) cannot enter target-error statistical trials or return-cost evaluation without an explicit unit bridge. Native target-metric adapters reject them. They remain valid frozen signal outputs; no automatic return interpretation is made.

Git status: branch `main`; baseline HEAD `4e84f82c638f78808bba10f6238254ea770367a4` unchanged. There are 17 modified tracked files and 54 untracked AFRE-21 deliverables, with zero staged changes. No commit or push was performed.

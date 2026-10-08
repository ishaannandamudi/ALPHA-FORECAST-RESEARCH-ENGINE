# AFRE-17 completion report

Engine 0.18.0; invariance/stability schema 1.0; shared store 1.17/SQLite user_version=18. All earlier public schemas remain 1.0. Frozen roadmap: 26 distinct phases, AFRE-0 through AFRE-25.

AFRE-17 provides declared, descriptive environment stability research. Stability != causal invariance proof; input distribution shift != error degradation. No significance or profitability claim, auto-refit/pruning/promotion, direct external-engine integration or AFRE-18 implementation.

Validation finalized on 2026-10-07 from the saved successful full-suite runs. All 577 frozen source/test inputs match their validated hashes and file set; no expensive gate was repeated during continuation. All 54 quality gates pass. No commit or push.

| Item | Scope | Evidence |
|---|---|---|
| A | architecture | Dedicated immutable declared-environment layer over frozen AFRE-0 through 16 evidence; input shift and later error assessment stay separate. |
| B | package structure | 20 focused modules in src/afre/invariance; native orchestration, definitions, scoring, distributions, parameters, ranks, uncertainty, storage, replay and unified lineage. |
| C | schema | New invariance/stability schema 1.0. Every earlier public schema remains 1.0. |
| D | engine/store versions | Engine 0.18.0, shared store 1.17, SQLite user_version=18; transactional additive17→18 migration. |
| E | environment types | All nine declared categories implemented; MARKET_STATE is a neutral received label, without inferred market semantics. |
| F | environment definitions | Exact ID/kind/provider/version/matching rule/target/horizon/declaration/minimum/temporal policies, with canonical fingerprints. |
| G | membership semantics | Full sample/security/origin; hard or explicit soft weight; supplied and selected evidence; historical evidence and actual construction clocks remain distinct. |
| H | environment sets | Canonical exact definitions, unique logical IDs, one target, explicit bounded compounds; no partition discovery. |
| I | time windows | Overlapping/non-overlapping UTC windows with exact endpoints, elapsed calendar and minimum N. |
| J | rolling/expanding windows | Deterministic bounded length/stride rolling windows; expanding windows and adaptive boundaries deferred. |
| K | regime environments | Native filtered hard/soft regime taxonomies and PIT subjects; retrospective states fail closed; no argmax. |
| L | event environments | Native class/subject/window and exact materiality/novelty/surprise ranges; both expectation and actual evidence checked. |
| M | PIT sector environments | Native PIT sector/industry classifications, exact taxonomy/version, valid time and availability; late revisions cannot replace history. |
| N | universe environments | Exact admitted native universe definition/snapshot and eligible security; different pools remain explicit. |
| O | quality environments | Explicit native source-quality tokens; no conversion of quality into variance. |
| P | custom environments | Immutable neutral source labels and six native availability clocks; no executable predicate. |
| Q | analysis spec | Target/fold/source IDs, environments, selectors, metrics, intersections, minimums, baseline, weighting, score/bin policy, tolerance/seed/version pinned. |
| R | sample intersection policies | Native cohorts, entire-set common and pairwise intersections remain distinct; exact sample/truth IDs retained. |
| S | performance stability | Native MAE/MSE/RMSE/R²/Pearson/Spearman/sign accuracy with explicit count/variance states; weighted point scores preserve declared weights. |
| T | probabilistic stability | Native Gaussian/empirical/mixture proper scores; calibrated marginal semantics retained; unsupported density/quantiles remain unavailable. |
| U | cross-sectional stability | Equal-origin mean Pearson IC/rank IC in explicit full-context cross-sections; incompatible same-time contexts cannot be pooled. |
| V | coefficient stability | Supplied compatible fits expose coefficients, intercepts, range/mean/median, sign fractions and meaningful vector correlations; no refits. |
| W | raw-scale coefficient handling | Affine native preprocessing converts beta/scale and intercept−ΣbetaRaw×center. Non-affine/unsupported sequence centering is incomparable. |
| X | tree stability | Measured split-feature/path recurrence, thresholds and leaf support from immutable native shallow trees; descriptive only. |
| Y | sequence stability | Fixed readout/decay/state parameters and readout L1 sensitivity; no hidden-dynamics invariance assertion. |
| Z | orthogonal-signal stability | Supplied AFRE-16 projection coefficients, TRAIN residual variance, held-out ratio/raw-reference/incremental metrics. |
| AA | uncertainty stability | Native predictive variance/disagreement/exact component shares with unchanged method/units/identifiability; missing or non-additive evidence is unavailable. |
| AB | feature distribution shift | Exact predeclared feature observations, sample lists, observed mean/std/Type7 quantiles and explicit missingness. |
| AC | KS/quantile/missingness shift | Empirical KS sup, quantile distance, standardized mean difference and missing-fraction delta; no p-values. |
| AD | forecast degradation | Separate immutable degradation artifact, explicit predeclared baseline and score orientation; absolute environment−baseline delta. |
| AE | relative degradation | Relative delta only above pinned nonzero-denominator tolerance; absolute delta stays primary. |
| AF | sign stability | Exact negative/zero/positive fractions and modal sign consistency; distinct artifact identities determine parameter summaries. |
| AG | prediction stability | Exact matched prediction Pearson/Spearman, mean absolute difference and sign agreement; temporal rank limitations explicit. |
| AH | rank stability | AFRE-9 average-tie ranks for displacement and fixed declared top K with stable identity tie break. Bucket monotonicity deferred. |
| AI | calibration stability | Coverage/error/width and fixed-bin ECE/MCE/reliability; exact native calibrated marginals; no calibrator refit. |
| AJ | event stability | Same frozen producer evaluated against native declared event cohorts; no event causal-effect claim. |
| AK | regime stability | Same frozen producer across hard/soft regime cohorts; explicit weighted effective support. Weighted correlations/IC unavailable. |
| AL | sector stability | Exact PIT sector/industry cohorts with minimum count; native population changes visible. |
| AM | universe stability | Exact universe identity and eligibility preserve historical pools; no hidden survivorship substitution. |
| AN | temporal stability | Explicit chronological windows and later in-sample TRAIN description; no adaptive refit schedule. |
| AO | environment counts/minimums | Eligible, selected, included, excluded, missing, truth-available and effective counts always retained; explicit minimum N. |
| AP | comparability states | Typed comparable/partially comparable/incomparable/insufficient/unavailable states and pinned reasons. |
| AQ | environment metrics | Immutable replayable metric source/spec/environment/intersection/target/horizon/producer/cutoff/availability/TEST evidence. |
| AR | stability comparisons | Immutable pair/spec/score/intersection/delta/comparability and optional relative delta; no universal score. |
| AS | feature-shift artifacts | Separate immutable feature distributions/distances/missingness artifact with exact selector and source observations. |
| AT | target-free boundary | Feature-only metadata/shift paths and guarded later-result reads, including after validation cache use. |
| AU | TEST boundary | Explicit native sealed TEST assessment; declared settings before fold training cutoff; no TEST fitting/tuning/calibration/baseline selection. |
| AV | baseline/environment declaration | Settings/declarations chronologically constrained, never chosen by an outcome-reading API; caller-attested historical declaration trust boundary documented. |
| AW | multi-horizon treatment | Actual independent one-hour and one-day native targets assessed separately; mixed-horizon comparison is incomparable. |
| AX | compound environments | Only explicitly declared event×regime and sector×regime; no nested compounds or generated grids; count bounds on reads/writes. |
| AY | shift-vs-degradation separation | Separate feature-shift and error-degradation families; no causal attribution. |
| AZ | trends | Descriptive chronological center slope and monotonicity, with overlap/cohort limitations; no significance or health automation. |
| BA | no-auto-refit | Analysis has no fit/refit/recalibrate API; existing model/calibrator bytes and native table rows remain unchanged. |
| BB | no-auto-prune | No feature/signal pruning or mutation; existing source sets preserved. |
| BC | no-promotion | No promotion/champion/challenger or production replacement API. |
| BD | audit | Audit records exact frozen declarations/sources/metrics/cutoffs/TEST and explicit absence of causal/significance/profitability/mutation claims. |
| BE | lineage | Bounded unified native TRAIN/PIT/model/forecast/truth lineage with sorted IDs, cycle/depth/node/byte checks. |
| BF | persistence/migration | Immutable canonical data; exact republish idempotent; additive migration, rollback/future rejection and prior DDL/metadata/rows preserved. |
| BG | indexes/performance | Environment/kind, source/model/metric, target/horizon, security/origin, window, cohort, cutoff/TEST and inverse-reference indexes. |
| BH | deterministic replay | Fresh AFRE-17 construction across hash seeds0/1/42/random, reversed environments/memberships/samples/requests and reopen yields identical semantic bytes. |
| BI | concurrency | Real second SQLite writer publishes environment/regime/event/group/forecast/target revisions; open exact-reference analysis remains frozen. |
| BJ | numerical correctness | Independent weighted/error, affine conversion, empirical CDF/Type7/missingness, Gaussian/calibration, rank and trend fixtures. Profile KS/delta maximum error 0. |
| BK | security | Strict data-only contracts, stdlib runtime, closed serializers, no runtime network/shell/eval/exec/pickle/dynamic imports or provider-selected paths. |
| BL | documentation | Eight dedicated documents, master/README and all active roadmap references updated; historical completion reports retained. |
| BM | tests added | 135 new focused tests. Prior contracts and assertions are preserved; one AFRE-14 corruption-test fixture now constructs explicit late evidence, and its existing demo selects the declared irregular-history scenario instead of relying on fingerprint ordering. |
| BN | full pytest | PASS: 2,362 tests in 2,137.72s (35m37s); all prior tests plus 135 AFRE-17 tests, with the repository's autouse socket/DNS block. |
| BO | coverage | PASS: branch-enabled, socket/DNS-blocked full suite before collection; 2,362 tests in 4,035.26s (1h07m15s), exit 0. Combined 98.698129% (29,112/29,496), statement 99.297799% (24,181/24,352), branch 95.859253% (4,931/5,144); combined gate≥95%. |
| BP | Ruff | Whole-repository Ruff check and format verification pass (726 Python files formatted). |
| BQ | mypy | Strict whole-repository mypy passes over 576 files. |
| BR | diff review | Complete changed-file diff/status reviewed. Hashes of prior source/contracts/benchmarks and historical reports match the 693-file baseline, except version metadata. All prior tests are unchanged except explicit late-evidence setup in one AFRE-14 snapshot-corruption test; its original assertions are intact. The prior sequence demo now selects its intended irregular-history fixture explicitly; demonstration assertions are unchanged and all 37 legacy steps pass. No commit or push. |
| BS | secret/TODO scan | Final scripted secret/unfinished-work scan passes over 740 deliverables; documentation consistency verifies 150 documents, all 75 A–BW entries, all 54 gates and the exact 26-phase roadmap. |
| BT | benchmark/profile | Measured bounded native profile: 2 environments, 12 samples, 24 memberships, 44 metrics; separate 32×2,000 empirical-KS kernel. See invariance-profile.json; no SLA. |
| BU | dependencies | Zero runtime dependencies; Python 3.11+ and existing native stdlib numerical/scoring contracts. |
| BV | remaining limitations | Descriptive observations only; no causal proof/significance/profitability. Weighted rank/IC/distribution distances, expanding windows, bucket monotonicity, target distributions, broader prediction-distribution diagnostics and change-point search deferred. Different calibrated states are incomparable. Declaration chronology cannot authenticate human outcome blindness. |
| BW | exact AFRE-18 scope | AFRE-18 only: cost-aware alpha evaluation, spread/slippage/impact assumptions, neutral cost inputs, turnover diagnostics, gross versus net expected edge, break-even cost and market-impact research comparison; no execution optimization. Not implemented. |

## Quality gates

| Gate | Check | Result |
|---|---|---|
| 1 | focused AFRE-17 tests | PASS — 135 tests |
| 2 | full pytest | PASS — 2,362 tests, 2,137.72s |
| 3 | branch-enabled combined coverage≥95% | PASS — combined 98.698129%; statement 99.297799%; branch 95.859253% |
| 4 | socket/DNS-blocked full suite | PASS — blocking before collection; 2,362 tests, 4,035.26s, exit 0 |
| 5 | Ruff check | PASS — Ruff check . |
| 6 | Ruff format check | PASS — 726 files |
| 7 | strict mypy | PASS — strict mypy, 576 files |
| 8 | git diff --check | PASS |
| 9 | complete status/diff review | PASS — 22 tracked modified, 47 new; unstaged on main |
| 10 | secret scan | PASS — 740 deliverables |
| 11 | unfinished-work scan | PASS — 740 deliverables |
| 12 | migration success/rollback/future rejection | PASS |
| 13 | corruption rejection | PASS |
| 14 | resource bounds | PASS |
| 15 | hash-seed determinism | PASS |
| 16 | insertion-order determinism | PASS |
| 17 | restart replay | PASS |
| 18 | real concurrent writer | PASS |
| 19 | time-window semantics | PASS |
| 20 | regime memberships | PASS |
| 21 | event cohorts | PASS |
| 22 | PIT sectors | PASS |
| 23 | PIT universes | PASS |
| 24 | quality cohorts | PASS |
| 25 | point/probability numerical fixtures | PASS |
| 26 | intersection policies | PASS |
| 27 | insufficient count states | PASS |
| 28 | coefficient sign/range | PASS |
| 29 | raw-scale coefficients | PASS |
| 30 | tree recurrence | PASS |
| 31 | sequence stability | PASS |
| 32 | AFRE-16 stability | PASS |
| 33 | AFRE-15 uncertainty | PASS |
| 34 | feature shift | PASS |
| 35 | empirical KS | PASS |
| 36 | Type7 quantiles | PASS |
| 37 | missingness | PASS |
| 38 | degradation | PASS |
| 39 | compound environment | PASS |
| 40 | compound bounds | PASS |
| 41 | actual1h/1d | PASS |
| 42 | same-origin IC | PASS |
| 43 | rank overlap/displacement | PASS |
| 44 | calibration | PASS |
| 45 | TEST boundary | PASS |
| 46 | target-free metadata | PASS |
| 47 | no auto-refit | PASS |
| 48 | no auto-prune | PASS |
| 49 | no promotion | PASS |
| 50 | no direct external-engine dependency | PASS |
| 51 | documentation/roadmap | PASS — 150 documents; exact 26-phase roadmap |
| 52 | 37-step offline demo | PASS — all 37 steps |
| 53 | bounded measured profile | PASS — refreshed native workflow and separate arithmetic workload |
| 54 | zero runtime dependencies | PASS — runtime dependencies=[] |

The [research guide](invariance-stability-research.md), [evaluation contract](stability-evaluation.md) and [profile](invariance-profile.json) describe exact semantics and practical limits. The 37-step offline demo passes.

**Next scope: AFRE-18 — Transaction-Cost-Aware Research Evaluation.** **Stop after AFRE-17.** Leave changes in the working tree for review. Do not commit or push.

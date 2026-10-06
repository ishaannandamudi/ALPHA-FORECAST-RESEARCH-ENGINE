# AFRE-16 completion report

Working-tree implementation for review; no commit or push. Frozen roadmap: 26 distinct phases,
AFRE-0 through AFRE-25. Engine 0.17.0, orthogonalization schema 1.0, store 1.16/user_version17.

All 49 quality gates passed on the final frozen implementation. Both full socket/DNS-blocked
runs passed all 2,227 tests. The roadmap remains 26 distinct phases, AFRE-0 through AFRE-25.

| Item | Scope | Evidence / behavior |
| --- | --- | --- |
| A | Architecture | Supplied causal TRAIN-fitted transforms, exact matched descriptive/predictive evaluation, immutable replay; orthogonal != independent. |
| B | Package structure | 23 focused modules in `afre.orthogonalization`; contracts, sources, alignment, QR, residuals, partial/incremental/evaluation, diagnostics, feature/rank bridges, SQLite validation and lineage. |
| C | Schema | Orthogonalization1.0; every earlier public schema remains 1.0. |
| D | Engine/store versions | Engine 0.17.0; shared store 1.16/user_version17; additive 16→17 migration. |
| E | Signal references | Exact family, provider/version, semantic/model key, selector, unit and optional predictive target. Observations pin actual source artifact, sample, full origin, numerical presence, clocks and approved reconstruction attestors. |
| F | Supported sources | Ordinary feature, neutral external/generic scalar, AFRE-10 event, AFRE-11 regime/probability, AFRE-12 expert point/law expectation and mixture, AFRE-13 scalar/nonlinear, AFRE-14 sequence, numerical AFRE-15 diagnostic. |
| G | Spec | Fixed candidate/canonical references, fold/cutoff/target/horizon, explicit intercept/preprocessing/equal-row weights/support/rank/condition/seed/numerical version. |
| H | Modes | TEMPORAL_PANEL and CROSS_SECTIONAL_HISTORICAL. Historical projection fits complete eligible TRAIN origin grids, then applies within later origins. Per-origin fits are unsupported. |
| I | Pairwise correlation | Pearson/Spearman average ties, absolute Pearson, native N/degenerate states, one pinned common complete-case intersection; TRAIN and held-out matrices remain separate. |
| J | Partial correlation | Separately TRAIN-fitted residuals under exact common controls/fold/target/mode/policy/cutoff. Pearson and Spearman-of-linear-residuals, not rank-first classical partial Spearman or independence. |
| K | Multivariate projection | Candidate is response. Deterministic AFRE-5 column-pivoted Householder QR plus triangular-factor Frobenius condition gate; no hidden regularization/pseudo-inverse. |
| L | Intercept | WITH_INTERCEPT or NO_INTERCEPT. R² retains the native centered denominator even with no intercept. |
| M | Preprocessing | NONE stores 0/1; TRAIN_STANDARDIZE stores TRAIN population means/scales. Standardization explicitly centers references even with NO_INTERCEPT; constants fail. |
| N | Projection artifact | Exact TRAIN row/sample IDs and candidate values, canonical reference IDs, coefficients/intercept/centers/scales, rank/condition/VIF, TRAIN metrics/residual variance, matrix, cutoff/computation/availability. |
| O | Orthogonal signal | Exact projection/row/source lineage, stable sample/origin, raw candidate/projected/residual, preserved candidate unit, missing state, actual computation/availability and fingerprint. |
| P | Target-free residualization | Engine and internal helper require feature-only reads. Cached target vintages, TRAIN-response matrices and paired target-model truths remain forbidden during application. |
| Q | Availability | Input/model/computation ≤ final residual availability ≤ origin cutoff. Provider publication is not AFRE receipt. Qualified channel reconstruction needs exact evidence and caller-approved attestors; later actual AFRE clocks remain intact. |
| R | Pairwise redundancy | Correlations are descriptive association, not percent redundant, novelty or independence. No universal redundancy score or automatic acceptance/rejection. |
| S | Projection R² | In-sample TRAIN projection R² is explicitly separate from frozen held-out R². |
| T | Held-out redundancy | Exact VALIDATION/TEST complete intersection, frozen candidate predictions, R²/MSE and candidate/residual population variances; no refitting. |
| U | Residual variance ratio | Population N denominator; Var(residual)/Var(candidate), unavailable for empty/zero denominator. Named 1−ratio fraction can be negative and is not R². |
| V | Incremental explanatory value | Separate fixed TRAIN QR target readouts on references vs references plus raw candidate or residual. Matched held-out diagnostics only; no significance or profitability inference. |
| W | Base/augmented comparison | One immutable paired fingerprint pins both named coefficient/intercept fields, same exact TRAIN rows/target vintages/truths, projection, representation and clocks. Δ metrics are augmented minus base. |
| X | Partial target correlation | Target minus frozen TRAIN reference-only target prediction is compared with frozen candidate residual; exact later truth intersection, no held-out nuisance fit. |
| Y | Cross-sectional orthogonalization | Frozen historical TRAIN fit applies within a later exact origin. Complete eligible grids and one full universe/origin context per timestamp are enforced in historical cross-sectional fitting and evaluation. |
| Z | PIT universe/group handling | Exact AFRE-3 snapshot/eligibility and manifest/full origin. Explicit AFRE-9 historical sector groups cannot be replaced by later classifications. Dedicated within-group projection estimators are deferred. |
| AA | Temporal orthogonalization | Historical security/panel rows ordered by time, stable instrument and sample identity; exact supplied fold/cutoff, equal-row weights and explicit held-out evaluation. |
| AB | Lagged redundancy | Optional lag diagnostics/search are deferred. No implicit lag choice or hidden shifting. |
| AC | Event signals | Exact native event forecast value/declared shift or causal scalar adapters; source model/sample/target/horizon/clocks preserved. |
| AD | Regime signals | Exact native forecasts and supplied membership probabilities with probability units; no future smoothing/reclassification. |
| AE | Expert signals | Exact expert point or distribution expectation plus mixture output, expert/gate/source identity and predictive context; no expert/gate mutation. |
| AF | Nonlinear signals | Exact native scalar inputs and nonlinear outputs; linear residualization makes no nonlinear-independence claim. |
| AG | Sequence signals | Exact causal forecast scalars; hidden-state vector comparisons are unsupported. |
| AH | Uncertainty signals | Identified/explicit numerical proxy only, exact component/measure/method/units/model/covariance/closure policy plus generative producers, alternative model set, interval settings and full uncertainty-policy digest. No quality-to-variance invention or automatic alpha attribution. |
| AI | External microstructure/context/options | Neutral existing ExternalSignal/GenericSignalSource contracts with physical receipt clocks. No direct AME/MCE/EIE/options-engine dependency. |
| AJ | Multi-horizon treatment | Actual independent 1h/1d targets/folds/projections/truths/evaluations; mixed horizon/model assessments fail. |
| AK | Collinearity | Rank, Frobenius condition estimate, common correlation matrix and conventional centered VIF. Primary deficiency/condition failure is explicit. |
| AL | VIF | N·population reference variance/auxiliary SSE =1/(1−R²), with intercept in auxiliary regressions. Constants, invalid auxiliary rank/condition and near-perfect fits are unavailable; single varying reference VIF 1. |
| AM | Redundancy matrix | Immutable candidate-first/canonical-reference matrix with exact rows/common intersection/exclusions/partition, Pearson/Spearman metrics and availability. |
| AN | Orthogonal basis | Ordered sequential basis and symmetric factors are optional and deferred; supplied candidates are independent requests. |
| AO | Residual scaling/quality | Raw candidate units preserved. Numerical availability is separate from original detailed source quality in lineage; missing candidate/reference means absent numerical residual, never zero. |
| AP | Residual integration | Caller-named AFRE-1 source-vintage export pins projection as version/transformation/unit and actual clocks; explicit registration/persistence. Existing feature sets/models stay immutable. |
| AQ | Ranking/IC | Explicit AFRE-9 residual score bridge with exact projection/residual provenance, target/horizon, eligible PIT universe and supplied historical groups. Same-time raw/residual rank IC is descriptive; cross-sectional mode enforces one full universe/origin context per timestamp. |
| AR | Raw-vs-residual comparison | Identical complete sample/target-vintage intersection for raw/residual Pearson/Spearman and base/augmented metrics. |
| AS | Multi-candidate handling | Up to16 supplied distinct candidates fit independently in canonical request order; no survivor, automatic ordering basis or combinatorial search. |
| AT | Stability | Compatible caller-supplied ordered disjoint known windows: raw-unit coefficient ranges, residual variance ratios, raw-reference correlations. This is not AFRE-17 invariance across environments. |
| AU | No auto-prune | Diagnostics cannot delete signals, change feature sets, refit downstream models, promote survivors or select candidates. |
| AV | TEST boundary | Explicit inherited fold/sample/cutoff seal required; TEST may assess frozen transforms/models but cannot fit/tune/select. |
| AW | Audit | Bounded semantic replay answers source/version/availability, TRAIN evidence, coefficients/preprocessing/rank/condition/matrices, held-out metrics, truth context and TEST seal. Full audits have separate truth access. |
| AX | Lineage | Residual→row/projection→spec/references/matrix/TRAIN samples→exact source evidence; optional evaluations/target models/partial/stability/TEST roots. Native completed fit runs are included in unified audits. |
| AY | Persistence/migration | Immutable canonical structured JSON, transactional additive 16→17, prior DDL/rows/metadata preserved, rollback and future-schema rejection; strict hashes/family/schema/index/link/replay checks. |
| AZ | Indexes/performance | Fixed candidate/source/model, security/origin/sample, target/horizon, fold/cutoff/TEST and inverse-reference indexes; bounded work/payload/family counts/lineage. See measured profile. |
| BA | Deterministic replay | Seeds 0/1/42/random, fresh reversed reference/sample/request construction and restart require identical semantic artifact bytes. |
| BB | Concurrency | Actual second SQLite writer appends candidate/reference/projection/target corrections during frozen fit/application/evaluation; exact pinned computations/old bytes remain unchanged. |
| BC | Numerical correctness | Independent centered correlation/rank arithmetic, Gaussian-elimination OLS, residual/R²/variance/VIF/partial/incremental/stability fixtures. Maximum absolute error in the measured fixtures is 4.35207425653061e-14; individual quantities are recorded below and in the profile. |
| BD | Security | Data-only closed contracts; no eval/exec/pickle/joblib/shell/network/provider code/dynamic executable imports/provider-selected paths. Timestamp/provider/attestor honesty remains a declared trust boundary. |
| BE | Documentation | Eight dedicated guides, README/master and feature/split/rank/event/regime/mixture/nonlinear/sequence/uncertainty/reproducibility integration; current references corrected, historical reports retained. |
| BF | Tests added | 164 focused tests pass in 102.90 seconds, including the same-time context regression, covering independent oracles, sources/joins, availability/guards/holdouts, migrations/corruption/bounds, hashes/order/restart/concurrency, horizons/ranks/groups/stability and the demo. |
| BG | Full pytest | PASS: 2,227 tests in 1,802.85 seconds (30:02), including all 2,063 prior tests and 164 AFRE-16 tests. |
| BH | Coverage | PASS: 98.920693% combined, 99.422424% statements, 96.521922% branches. Branch coverage enabled; 2,227 tests pass in 3,346.13 seconds (55:46). |
| BI | Ruff | PASS: whole-repository lint; format check reports 680 files already formatted. |
| BJ | Mypy | PASS: configured strict mypy checks src/examples/benchmarks/tests/scripts; 539 source files, no issues. |
| BK | Diff review | Prior AFRE-0–15 source/tests are preserved; intended version/doc/checker changes and new AFRE-16 files reviewed. Working tree left for review; no commit/push. |
| BL | Secret/TODO scan | PASS: scripted scan of 693 deliverables for secrets, unfinished markers, whitespace and executable-data boundaries. |
| BM | Benchmark/profile | Bounded admitted 12-TRAIN/12-VALIDATION/4-TEST workflow; separate 2000-row/12-reference/8-candidate arithmetic kernels are not causal repository admissions. No production SLA. |
| BN | Dependencies | Python 3.11+, standard library only; zero runtime dependencies, unchanged development dependency pins. |
| BO | Limitations | Linear fixed equal-row transforms; complete TRAIN inputs; bounded full-rank/conditioned QR. No per-origin refit, lag search, ordered/symmetric basis, hidden-state vectors, new subgroup estimator, nonlinear independence, significance, automatic pruning/model search, portfolio/risk/execution or profitability claims. |
| BP | Exact AFRE-17 scope | Invariance & Stability Research across time/regimes/events/sectors/universes/market environments/feature-distribution shifts, coefficient/sign stability, forecast degradation, environment-conditioned diagnostics and an explicit no-causal-proof boundary. Deferred; STOP after AFRE-16. |

## Quality gates

| Gate | Check | Result |
| --- | --- | --- |
| 1 | focused AFRE-16 tests | PASS — 164 tests, 102.90 s |
| 2 | full pytest | PASS — 2,227 tests, 1,802.85 s (30:02) |
| 3 | branch-enabled combined coverage≥95% | PASS — 98.920693% combined, 99.422424% statements, 96.521922% branches; 2,227 tests, 3,346.13 s (55:46) |
| 4 | socket/DNS-blocked full suite | PASS — both full 2,227-test runs; inherited autouse socket/connection/DNS guard |
| 5 | Ruff lint | PASS — full repository lint |
| 6 | Ruff format | PASS — 680 files already formatted |
| 7 | strict mypy | PASS — 539 files under configured strict checks |
| 8 | git diff --check | PASS — clean |
| 9 | full status/diff review | PASS — tracked diff and new files reviewed; prior source/tests preserved except version constants |
| 10 | secret scan | PASS — 693 deliverables |
| 11 | TODO/FIXME scan | PASS — 693 deliverables |
| 12 | migration success/rollback/future-schema | PASS — additive 16→17, prior DDL/rows/metadata, rollback and version 18 rejection |
| 13 | corruption | PASS — hashes/families/schemas/indexes/links and semantic artifact forgeries fail closed |
| 14 | bounds | PASS — references/rows/work/matrix/payload/family/window/lineage limits |
| 15 | hash-seed determinism | PASS — seeds 0, 1, 42 and random |
| 16 | insertion-order determinism | PASS — fresh reversed candidate/reference/sample/request insertion |
| 17 | restart replay | PASS — reopened projections/residuals/evaluations match canonical bytes |
| 18 | concurrency | PASS — real second SQLite writer; five correction scenarios during fit/application/evaluation |
| 19 | pairwise correlation fixture | PASS — independent centered Pearson and average-tie Spearman |
| 20 | perfect redundancy fixture | PASS — perfect linear candidate and absent incremental rank |
| 21 | no-intercept fixture | PASS — explicit raw and standardized no-intercept policies |
| 22 | multivariate projection fixture | PASS — one/two-reference QR versus independent Gaussian-elimination OLS |
| 23 | standardization isolation | PASS — held-out changes leave TRAIN centers/scales/coefficients unchanged |
| 24 | target-free residualization | PASS — engine/internal/cache guards block target vintages and target-model truths |
| 25 | late-signal exclusion | PASS — late references, late projections and actual receipt/computation clocks |
| 26 | corrected-signal identity | PASS — new admissible revision identity, unchanged old bytes |
| 27 | rank deficiency | PASS — deficient design fails explicitly |
| 28 | condition threshold | PASS — near-collinear numerical condition policy |
| 29 | VIF | PASS — independent centered VIF and unavailable auxiliary states |
| 30 | partial correlation | PASS — frozen common-control residual association and independent arithmetic |
| 31 | held-out redundancy | PASS — frozen held-out R²/MSE and population variance diagnostics |
| 32 | incremental value | PASS — matched frozen base/augmented metrics and deltas versus independent oracle |
| 33 | no held-out selection | PASS — held-out perturbations do not alter projection/reference policy |
| 34 | PIT cross-sectional analysis | PASS — exact historical universe/full-origin complete eligible grids; same-time contexts cannot be pooled |
| 35 | PIT sector ranking integration | PASS — PIT sector ranking bridge; later reclassification excluded; new within-sector estimators deferred |
| 36 | temporal panel | PASS — stable sample/security/time ordering and exact supplied folds |
| 37 | event/regime/expert/nonlinear/sequence/uncertainty inputs | PASS — native point/law/scalar adapters; diagnostic policy/producer identity |
| 38 | neutral external microstructure/context/options | PASS — neutral sources with physical receipt evidence |
| 39 | no-direct external-engine regressions | PASS — static AME/MCE/EIE/options dependency regression |
| 40 | actual multi-horizon identity | PASS — actual distinct 1h/1d target/fold/model/evaluation identities |
| 41 | raw-vs-residual IC | PASS — identical target-vintage/sample intersection |
| 42 | cross-sectional ranking | PASS — explicit residual bridge into unchanged AFRE-9 ranks |
| 43 | descriptive stability | PASS — disjoint supplied windows and independent raw-unit coefficient-range oracle |
| 44 | no-auto-prune | PASS — diagnostics leave sources/feature sets/models unchanged |
| 45 | TEST boundary | PASS — TEST seal required; TEST cannot fit or select |
| 46 | documentation consistency | PASS — 141 documents; exact 26-phase roadmap, versions, links and 68-entry report |
| 47 | 37-step offline demo | PASS — all 37 steps |
| 48 | bounded benchmark/profile | PASS — measured bounded causal workflow and separate arithmetic workload |
| 49 | zero runtime dependency check | PASS — empty runtime dependencies; development pins unchanged |

## Numerical profile

Maximum absolute errors in the measured independent synthetic fixtures:

| Quantity | Maximum absolute error |
| --- | ---: |
| Projection coefficient | 5.77315972805081e-15 |
| Incremental target-model metric | 4.35207425653061e-14 |
| Partial target correlation | 0 |
| Pearson correlation | 0 |
| R² | 0 |
| Residual | 0 |
| Spearman correlation | 1.38777878078145e-17 |
| Raw-unit stability coefficient range | 0 |
| Residual variance ratio | 0 |
| VIF | 3.10862446895044e-15 |

The admitted causal workflow has 12 TRAIN, 12 VALIDATION and 4 TEST rows, two references,
222 AFRE-16 artifacts and 548 audited lineage nodes. The separate arithmetic workload uses
2,000 rows, 12 references and eight supplied candidates; it does not claim causal TRAIN admission.
AFRE-16 payloads occupy 344,653 bytes in the measured shared registry of 25,513,984 bytes.
Timings in [the profile](orthogonalization-profile.json) are hardware-specific; no production SLA
or trading-profitability inference is made.

## Evidence

[Architecture](signal-orthogonalization.md), [numerical tests](../tests/orthogonalization/test_numerics.py),
[causality](../tests/orthogonalization/test_causality.py), [workflow](../tests/orthogonalization/test_workflow.py),
[persistence](../tests/orthogonalization/test_repository.py), [bounds](../tests/orthogonalization/test_bounds.py),
[concurrency](../tests/orthogonalization/test_concurrency.py), [determinism](../tests/orthogonalization/test_determinism.py),
[security](../tests/orthogonalization/test_security.py), [demo](../examples/orthogonalization_demo.py),
[profile source](../benchmarks/orthogonalization_profile.py) and [profile results](orthogonalization-profile.json).

No AFRE-17 framework, downstream portfolio/risk/execution, automatic signal pruning or direct
external-engine integration is implemented. Orthogonality does not establish independence, unique
economic information, significance or trading profitability.

## Final working-tree status

`main...origin/main`; HEAD remains `943f7582d67175f274fe6414f60b14fbaa708677`.
18 tracked files modified and 48 new files untracked; no staged changes. No commit or push.
AFRE-0–15 source/tests remain unchanged except the intended version constants. AFRE-17 is deferred.

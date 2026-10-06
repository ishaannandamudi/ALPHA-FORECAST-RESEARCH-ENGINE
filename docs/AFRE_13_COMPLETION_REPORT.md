# AFRE-13 completion report

AFRE-13 — Nonlinear Feature Interactions. Engine0.14.0; nonlinear schema1.0; store1.13/user14.
Frozen roadmap:26 distinct phases, AFRE-0 through AFRE-25. Earlier phases remain stable.
Stop after AFRE-13. No commit or push. Portfolio/risk/execution remain downstream;
predictive metrics do not establish profitability.

| Item | Topic | Implementation/evidence |
| --- | --- | --- |
| A | architecture | Immutable contracts → pure transforms → exact TRAIN fits → truth-free application → later evaluation/audit. |
| B | package structure | 22 modules in afre.nonlinear, two offline examples, profile and focused tests; earlier packages unchanged. |
| C | schema | NONLINEAR_SCHEMA_VERSION1.0; every prior public schema remains1.0. |
| D | engine/store versions | Engine0.14.0, store1.13, SQLite user_version14; additive transactional13→14. |
| E | interaction definition | Exact semantic inputs, closed transform/parameters, output name/unit, missing/fallback, availability rule and implementation hash. |
| F | transform types | IDENTITY, PRODUCT, RATIO, DIFFERENCE, ABS_DIFFERENCE, SQUARE, CUBE, LOG1P_SIGNED, CLIPPED_LINEAR, PIECEWISE_LINEAR. |
| G | product interactions | Exact x*y; canonical operand/unit order; independent2×3=6 fixture. |
| H | ratio interactions | Mandatory FAIL_ON_ZERO, MISSING_ON_ZERO or positive signed EPSILON_FLOOR; no silent epsilon. |
| I | nonlinear scalar transforms | Finite differences, absolute differences, clipped linear and dimensionless sign(x)log1p(abs(x)); zero/nonfinite fixtures. |
| J | piecewise transforms | Fixed or exact TRAIN Type-7 quantile knots, supplied ordinates, linear interpolation and clamp extrapolation; duplicate knots reject. |
| K | polynomial interactions | Explicit square/cube only, degree≤3; no automatic full expansion. |
| L | cross-domain interactions | Generic event×regime, microstructure×context, options×context and causal expert×state; neutral AFRE contracts only. |
| M | availability semantics | Max source/fitted-state/model/actual-computation availability; receipt floor and model-approved qualified reconstruction preserve actual later clocks. |
| N | missingness | Interaction FAIL/PROPAGATE_MISSING/DECLARED_FALLBACK; model/tree missingness FAIL; None remains distinct from zero. |
| O | interaction sets | Canonical distinct supplied definitions, exact rich target/horizon, maximum128 and versioned fingerprint. |
| P | fitted transform artifacts | Spec/definition/fold, exact TRAIN input/sample IDs, knots, cutoff/start/completion/final clocks and canonical identity. |
| Q | training causality | Complete admitted AFRE-4 TRAIN set, known exact labels and per-origin causal scalar sources; held-out values cannot fit parameters. |
| R | nonlinear model families | LINEAR_ON_INTERACTIONS, LINEAR_PLUS_INTERACTIONS, SHALLOW_REGRESSION_TREE; squared error only. |
| S | linear-on-interactions | AFRE-5 pivoted Householder QR, fixed optional augmented ridge and explicit conditioning policies. |
| T | linear-plus-interactions | Declared originals precede exact interactions; fitted standardization is TRAIN-only; contributions use actual preprocessed values. |
| U | shallow tree model | Deterministic raw-column target-mean SSE tree, depth≤4 and exact TRAIN node support. |
| V | tree split semantics | TRAIN unique strictly interior midpoints, equally spaced candidate-index cap≤64; ties by SSE, feature identity, threshold; left≤/right>. |
| W | tree missingness | FAIL; no silent default branch or surrogate/imputed split. |
| X | monotonic/shape constraints | Monotonic constraints, shape constraints, splines and post-hoc repair unsupported. |
| Y | event×regime interactions | AFRE-10 security surprise/materiality/novelty semantic scales × AFRE-11 exact FILTERED security membership; no bespoke engine. |
| Z | microstructure×context | Declared AFRE-9 ExternalSignal provider/name/version/semantics/unit; no AME/MCE dependency. |
| AA | options×context | Neutral ExternalSignal options scalar crosses context; no options-engine algorithm/import. |
| AB | expert×state | Exact causal AFRE-12 binding/mixture point input, matching rich target/horizon; feature semantics, not learned gating. |
| AC | multi-horizon treatment | Actual1h/1d AFRE-8 architecture fixture yields separate models/forecasts with independent target/fold/cutoff identities. |
| AD | cross-sectional integration | Explicit derived neutral nonlinear score → unchanged AFRE-9 universe-aware ranking/IC; full origin/security grid pinned. |
| AE | probabilistic conditioning | Compatible AFRE-6 expectation/location translation preserves law shape/scale/atoms and recomputes supported quantiles/events. |
| AF | calibration semantics | Upstream states incompatible; independent VALIDATION assessment reports insufficient/unavailable/incompatible; dedicated nonlinear fitting unavailable. |
| AG | nonlinear forecast | Exact model/spec/input/sample/origin/security/target, interaction values, point, contributions/path, optional probability view and clocks. |
| AH | forecast availability | All required source/state/model/base-law availability precedes actual computation and origin cutoff; late forecast reconstruction unsupported. |
| AI | target-free application | Mandatory get guard denies TargetVintage, InteractionMatrix and InteractionTrainingRow; models/features/base laws retain original bytes. |
| AJ | matched evaluation | AFRE-5 point and AFRE-6 applicable proper scores, exact baseline sample/truth IDs, event/regime cohorts; no selection. |
| AK | interaction contributions | Exact coefficient×preprocessed column value with separate intercept; arithmetic attribution, not causal importance. |
| AL | tree path diagnostics | Every feature/threshold/left≤ or right>/leaf retained; prediction path reproduces leaf value. |
| AM | stability diagnostics | Compatible-model raw-slope sign consistency and magnitude range; tree feature split recurrence; independent statistic fixtures. |
| AN | no-auto-prune boundary | Diagnostics publish immutable descriptive artifacts only; no deletion/pruning/refit/selection. |
| AO | TEST boundary | TEST cannot fit/select transforms, interactions, splits or coefficients; explicit AFRE-4 seals and reuse evidence on later evaluation. |
| AP | audit | Semantic replay verifies exact sources, TRAIN parameters, matrices, models, paths/laws, metrics and clocks. |
| AQ | lineage | Unified bounded traversal spans nonlinear → sets/definitions/state → sources → folds/TRAIN/truth → completed upstream fit runs. |
| AR | persistence/migration | Immutable canonical JSON, verified family/schema/hash/index/links, atomic republish and transactional13→14 preserving prior DDL/metadata/rows. |
| AS | indexes/performance | Interaction/source/feature/family/target/horizon/security/origin/model/spec/availability/cutoff/TEST and reverse-reference indexes; bounded work/payloads. |
| AT | deterministic replay | Seeds0/1/42/random, reversed source/interaction/request insertion and reopened databases compare representative semantic bytes. |
| AU | concurrency | Second-writer source/transform/target corrections during frozen fit/prediction/evaluation/matrix builds preserve exact old results. |
| AV | numerical correctness | Independent products/ratios/logs/interpolation/knots/QR/split/path/shift/metric/stability oracles; profile QR maximum coefficient error4.44e-16. |
| AW | security | Closed data-only serialization, finite values/bounds, no eval/exec/pickle/joblib/shell/network/executable imports/provider-selected paths. |
| AX | documentation | Eight dedicated guides/profile docs, A–BI report and README/master/integration updates; exact26-phase roadmap retained. |
| AY | tests added | 185 new focused tests plus unchanged1579 earlier tests; all1764 pass in the full socket/DNS-blocked suite. |
| AZ | full pytest | 1764 passed in1252.01s (20m52s), including every prior test; final code/config remained frozen. |
| BA | coverage | PASS:98.89% combined,99.41% statements,96.42% branches; nonlinear package99.20% combined. All1764 tests pass under coverage. |
| BB | Ruff | Full Ruff lint and format gate; final evidence is recorded below. |
| BC | mypy | Strict mypy over source/examples/benchmarks/tests/scripts; final evidence is recorded below. |
| BD | diff review | Full tracked/untracked diff and baseline hash review; no completed source/test changes except current version constants. |
| BE | secret/TODO scan | Repository secret, TODO/FIXME and whitespace scan; final evidence is recorded below. |
| BF | benchmark/profile | Offline causal workflow and separately labelled2000-row arithmetic/40000-transform profile; replay/storage/audit/stage timings; no production SLA. |
| BG | dependencies | Python3.11+, standard library only, zero runtime dependencies; heavy ML frameworks absent. |
| BH | remaining limitations | Security-scoped event/regime projections; exact complete TRAIN set; FAIL model missingness; no nonlinear calibration fit, sparse-quantile expectation, shape constraints, splines, search or deployment-scale SLA. |
| BI | exact AFRE-14 scope | Deferred AFRE-14 Temporal / Sequence Models: causal ordered histories/masks/windows/alignment, missingness/length/time encoding, TRAIN transforms, appropriate recurrent/state-space/attention research and horizon/event/regime/external sequences. AFRE-15 uncertainty decomposition remains separate. |

## Final gate evidence

Focused:185 passed in249.99s (socket/DNS-blocked). Full suite:1764 passed in1252.01s
(20m52s), also socket/DNS-blocked. Branch-enabled full suite:1764 passed in2376.75s
(39m36s), zero failures. The completed saved coverage run was inspected and reused;
neither expensive full-suite gate was rerun during continuation. All426 frozen
code/config fingerprints still match exactly.

Combined coverage:98.89042995839112% (22103/22351 statement/branch units).
Statement coverage:99.40969401570538% (18356/18465 statements).
Branch coverage:96.42305712815234% (3747/3886 branches). Required combined gate≥95% passes.
Nonlinear package:99.19879819729594% combined,99.578567128236% statements,
97.32142857142857% branches across22 modules.
Exact saved coverage evidence:/private/tmp/afre13-full-coverage.json and
/private/tmp/afre13-full-coverage.log.

Ruff lint/format pass (537 files); strict mypy passes (425 source files).
Documentation consistency passes (112 documents, exact26-phase roadmap, all61 A–BI items).
Repository scan passes (546 deliverables, secrets/TODO/FIXME/whitespace).
Offline demo verifies all36 steps and585 immutable artifacts after restart.
Offline profile:12 causal TRAIN rows,2000 separately labelled arithmetic rows,
40000 transform applications, maximum independent QR coefficient error4.44e-16.

Baseline hash review confirms every prior source/test/example/benchmark file is unchanged
except src/afre/version.py. Git HEAD remains0ed50ca on main; no staged files/commit/push.
Changes:13 modified files plus50 new files (22 source,15 test,2 example,1 benchmark,10 docs).

## Final continuation checklist

| Gate | Result/evidence |
| --- | --- |
| 1 focused AFRE-13 tests | PASS:185 tests. |
| 2 full pytest | PASS:1764 tests. |
| 3 branch-enabled combined coverage≥95% | PASS:98.89% combined;99.41% statements;96.42% branches. |
| 4 socket/DNS-blocked full suite | PASS:unchanged autouse network denial plus explicit replay-worker network denial. |
| 5 Ruff lint | PASS:full repository. |
| 6 Ruff format | PASS:537 files already formatted. |
| 7 strict mypy | PASS:425 files across source/examples/benchmarks/tests/scripts. |
| 8 git diff --check | PASS. |
| 9 full git status/diff review | PASS:63-file inventory and baseline hashes; prior source/tests/examples/benchmarks unchanged except version constants. |
| 10 secret scan | PASS:repository scanner. |
| 11 TODO/FIXME scan | PASS:repository scanner. |
| 12 migration success | PASS:transactional13→14 preserves every prior metadata/DDL/row. |
| 13 migration rollback | PASS:failed additive migration restores user13 and earlier state. |
| 14 future-schema rejection | PASS:test_repository future-version corruption fixture. |
| 15 corruption | PASS:payload/family/schema/index/link corruption and semantic forgery fixtures. |
| 16 bounds | PASS:test_bounds, tree work bounds and payload/lineage limits. |
| 17 hash-seed determinism | PASS:0/1/42/random fresh workers. |
| 18 insertion-order determinism | PASS:source/interaction/request reversal fixtures. |
| 19 restart replay | PASS:fresh workers, repository tests and585 demo artifacts. |
| 20 concurrency | PASS:second-writer source/transform/target corrections during frozen reads. |
| 21 transform availability | PASS:receipt floor, qualified reconstruction, future state/model and computation clocks. |
| 22 held-out transform leakage | PASS:VALIDATION/TEST cannot fit; held-out value/truth perturbations preserve TRAIN fits. |
| 23 target-free prediction | PASS:guard denies TargetVintage, InteractionTrainingRow and InteractionMatrix reads. |
| 24 tree held-out leakage | PASS:held-out truth/value perturbations preserve fitted trees. |
| 25 tree deterministic tie-break | PASS:independent feature-identity and threshold tie fixtures. |
| 26 event×regime | PASS:exact product fixture and demo. |
| 27 microstructure×context | PASS:neutral exact product fixture and demo. |
| 28 options×context | PASS:neutral exact product fixture and demo. |
| 29 expert×state | PASS:causal exact product fixture and demo. |
| 30 no-direct AME dependency | PASS:closed implementation AST checks and unchanged earlier tests. |
| 31 no-direct MCE dependency | PASS:closed implementation AST checks and unchanged earlier tests. |
| 32 no-direct EIE dependency | PASS:closed implementation AST checks and unchanged earlier tests. |
| 33 no-direct options-engine dependency | PASS:closed implementation AST checks and unchanged earlier tests. |
| 34 probability shift | PASS:independent translated-law/quantile fixture and forgery rejection. |
| 35 calibration compatibility | PASS:upstream incompatibility and independent non-TRAIN/non-TEST assessment. |
| 36 cross-sectional rank | PASS:exact-origin AFRE-9 ranking/IC tests and demo. |
| 37 multi-horizon identity | PASS:actual1h/1d AFRE-8 targets with separate model/fold identities. |
| 38 matched evaluation | PASS:exact sample/truth baseline comparisons, metric deltas and mismatch rejection. |
| 39 contribution diagnostics | PASS:coefficient×preprocessed-value arithmetic and intercept reconstruction. |
| 40 stability diagnostics | PASS:independent sign/magnitude and tree split-recurrence fixtures. |
| 41 no-auto-prune | PASS:diagnostics leave model/spec/source bytes unchanged. |
| 42 TEST boundary | PASS:fit/calibration rejection, seal and reuse evidence. |
| 43 docs consistency | PASS:112 documents, exact26-phase roadmap, links/versions/historical reports and61 A–BI items. |
| 44 demo | PASS:all36 requested steps,585 immutable artifacts after restart. |
| 45 benchmark/profile | PASS:offline bounded causal workflow plus separately labelled arithmetic kernels; no SLA. |
| 46 dependency check | PASS:zero runtime dependencies, stdlib implementation and no heavy ML framework. |

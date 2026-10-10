# AFRE-20 completion report

Completed 2026-10-09 (America/New_York). All applicable final gates passed; unsupported optional criteria remain explicitly deferred.

Engine 0.21.0; selection schema 1.0; store 1.20/SQLite 21; Python 3.11+; zero runtime dependencies.

| Item | Topic | Result |
| --- | --- | --- |
| A | architecture | Bounded frozen-snapshot orchestration around native fitting APIs; TRAIN fits, VALIDATION selects, TEST stays outside selection. |
| B | package structure | 24 selection modules separate contracts, admission, fitting, scoring, decisions, accounting, guards, storage, comparisons and lineage. |
| C | schema | Closed data-only selection schema 1.0; canonical immutable contracts and explicit typed states; earlier public schemas unchanged. |
| D | engine/store versions | Engine 0.21.0; store 1.20; SQLite user_version 21; additive 20→21 migration. |
| E | search spaces | Predeclared complete Cartesian grid, exact native recipe per combination, target/horizon/dataset/fold and VALIDATION grid. |
| F | search dimensions | Categorical sorted finite dimensions/values; duplicates rejected; 16-dimension ceiling. |
| G | candidate specifications | Embedded native specs, seeds, exact TRAIN inputs, VALIDATION feature bindings, preprocessing/features and guarded metadata. |
| H | candidate identity | CandidateSpec commits to parent space, full recipe and exact target/horizon/dataset/fold context. |
| I | canonical enumeration | All combinations checked before fitting; candidates sorted by fingerprint; order reversals normalize identically. |
| J | candidate bounds | 128 absolute candidates and caller budget checked before any fit; no truncation. |
| K | resource budgets | Whole-grid fit/TRAIN/VALIDATION/native iteration/payload reservations; snapshot/publication/artifact/comparison/lineage bounds. |
| L | TRAIN fitting | Native family fitting and preprocessing use the fold TRAIN cutoff and exact native witnesses. |
| M | VALIDATION evaluation | Frozen predictions, verified available exact truth, complete requested pair/exclusion grid; common support checked. |
| N | TEST exclusion | Mandatory get/resolve/get_any guards before caches; stored held-out evaluations and declared TEST reclassification rejected. |
| O | selection criteria | MIN_MSE, MIN_MAE, MAX_R2, Gaussian/empirical MIN_CRPS and Gaussian MIN_NLL; IC/rank-IC/cost/composites deferred. |
| P | criterion direction | MSE/MAE/CRPS/NLL minimize; R² maximizes; no silent direction inversion. |
| Q | metric compatibility | Native distribution law required; no point-to-density fabrication; empirical NLL and undefined R² unavailable. |
| R | validation results | Exact candidate/fit/trial, criterion/secondary, sample/truth/forecast witnesses, exclusions, cutoff/availability and status. |
| S | selection result | Complete roster, ordering, selected TRAIN model, request/family, native event compatibility, usage and exhaustive flag. |
| T | failed candidate handling | Actual bounded LASSO nonconvergence retained; failed trial has no invented observations; protocol anchor explicit. |
| U | tie handling | Declared lexicographic primary/secondary direction then canonical candidate fingerprint; no post-hoc simplicity bias. |
| V | secondary criteria | Optional explicit identity-bearing secondary criterion; exact compatible support required. |
| W | model-family support | Real native AFRE-5/6/10/11/13/14 adapters fit/forecast/restart; AFRE-12 orchestration unsupported. |
| X | calibration candidate handling | Automatic calibrated-candidate orchestration is deferred; native calibration contracts remain intact. |
| Y | feature-set variants | Exact native feature definitions/input bindings and TRAIN preprocessing identities, with no automatic inclusion/pruning. |
| Z | orthogonal feature integration | Actual AFRE-16 residual-to-native nonlinear scalar binding; causal later fold; original TEST samples remain excluded. |
| AA | uncertainty metadata | Optional guarded diagnostic IDs remain metadata; no automatic uncertainty penalty or false variance decomposition. |
| AB | stability metadata | Guarded declared references only; no post-hoc stability optimizer, model-health automation or refit. |
| AC | cost-aware criteria | AFRE-18 net-edge selection deferred; transaction-cost research remains separate from portfolio construction. |
| AD | AFRE-19 integration | Every candidate has a native opportunity/trial and exact full family; unsupported inference assumptions remain false. |
| AE | candidate trial accounting | Full roster including failed/incompatible/insufficient candidates; request cutoff pins distinct native attempts. |
| AF | selection events | Native median-effect/trial-order event only on exact values, orientation and full ordering match; otherwise explicit unavailable event. |
| AG | TEST reuse treatment | Later evaluation requires native seals and AFRE-19 adaptivity/history; SelectionEngine does not evaluate TEST. |
| AH | nested selection | Unsupported; no nested tuning claim or hidden inner folds. |
| AI | walk-forward selection | Independent exact fold calls; no shared future-fold criterion/parameter adaptation or aggregate-fold optimizer. |
| AJ | multi-horizon treatment | Actual 1h and 1d native searches have separate spaces/candidates; coupled horizon optimization unsupported. |
| AK | preprocessing selection | Every variant pins native TRAIN-fitted preprocessing; frozen transforms applied on VALIDATION. |
| AL | no-validation-fitting rule | FIT role rejects VALIDATION truth and selection/evaluation response records; no learned VALIDATION preprocessing. |
| AM | early-stopping treatment | Native deterministic max-iteration/convergence policy only; no VALIDATION or wall-clock stopping. |
| AN | candidate registry | Complete CandidateRegistrySnapshot preserves all fits, validation statuses, native trials and model witnesses. |
| AO | append-only semantics | Idempotent identical insertion; immutable SQL update/delete protections; later revisions create new artifacts. |
| AP | matched candidate comparison | Exact target/horizon/dataset/fold/criterion/cutoff and common sample/truth intersection; declared minimum support. |
| AQ | metric deltas | Descriptive B-minus-A, recomputed on intersection; no significance or profitability inference. |
| AR | failed validation | Explicit incompatibility/support/numerical statuses and exclusions; no fabricated criterion value. |
| AS | minimum support | Predeclared N applies to exact paired observations; too few rows gives INSUFFICIENT_DATA. |
| AT | no-valid-candidate state | NO_VALID_CANDIDATE records complete pool and has no selected candidate/model. |
| AU | single-valid-candidate state | Only explicitly permitted sole valid candidate selects; status NONCOMPETITIVE. |
| AV | baseline handling | Optional explicit baseline recipe ID; no automatic baseline inclusion or winner override. |
| AW | complexity metadata | Native family/spec settings remain inspectable; no undeclared complexity/simplicity preference. |
| AX | search summary | Full candidate outcomes, exhaustive ordering, immutable winner, event availability and resource usage. |
| AY | resource usage | Reservations and actual attempted fits/fitted candidates/VALIDATION pairs/payload recomputed on semantic replay. |
| AZ | exhaustiveness | Only complete exhaustive declared Cartesian grids; budget failure rejects entire run before publication. |
| BA | partial search | Unsupported; no BOUNDED_PARTIAL or best-over-full-space claim. |
| BB | random/Bayesian search limitations | Random, Bayesian, adaptive and continuous search unsupported; model seeds are explicit native inputs. |
| BC | TEST boundary | No TEST tuning, selected-model promotion, production service or hidden TEST response load. |
| BD | declaration semantics | Caller-recorded space clock precedes TRAIN boundary; not authentication of unrecorded human research. |
| BE | target-free planning | Metadata-only native split geometry and inherited feature-only guard; actual native fit separately validates TRAIN labels. |
| BF | selected model immutability | Selection references exact native TRAIN model; old model/selection bytes remain unchanged. |
| BG | final-refit treatment | Unsupported; no automatic TRAIN+VALIDATION refit. |
| BH | correction semantics | Valid source/VALIDATION revision rebuilds explicit context/new candidates/result; cutoff new attempt; old truth IDs replay; TEST correction independent. |
| BI | audit | Bounded immutable SelectionAudit for result or registry root; cycle/node/depth/byte limits fail closed. |
| BJ | lineage | Native TRAIN/source/feature witnesses and exact scored VALIDATION truth/trials; embedded specs traversable; unrelated TEST responses excluded. |
| BK | persistence/migration | Transactional 20→21 success, rollback, future-schema rejection; prior DDL/metadata/rows preserved; corruption fails closed. |
| BL | indexes/performance | Three selection tables, five relational indexes; bounded stage publication and native replay; measured small offline profile only. |
| BM | deterministic replay | Seeds 0/1/42/random, reversed dimensions/values/recipes/sample/source/request order and restart; same-platform semantic bytes. |
| BN | concurrency | Real second writer appends TRAIN/VALIDATION/TEST source revisions and later candidate space; frozen run unchanged. |
| BO | numerical correctness | Independent point/probability oracles; maximum absolute error 7.192163531399842e-15; exact count/tie and matched delta fixtures. |
| BP | security | Closed JSON/static types/table whitelist; no runtime network, executable search, eval/exec/pickle/joblib/shell/dynamic imports/provider paths. |
| BQ | documentation | Eight guides, active integration docs, master/readme exact 26-phase roadmap and AFRE-21 scope; earlier reports retained. |
| BR | tests added | Selection-focused native pipeline, metrics, grid/budget, guards, storage/migration/corruption, horizons/residual, replay/concurrency regressions. |
| BS | full pytest | PASS: 2, 813 tests; zero failures/errors/skips; 4, 785.68 s (1:19:45), with socket/DNS blocked in the process and fresh Python children. |
| BT | coverage | PASS: 98.5327% combined with branches enabled; statements 28356/28606; branches 5758/6016. Full covered run plus isolated corrected test; runtime source unchanged. |
| BU | Ruff | PASS: repository-wide Ruff lint and format; 875 files formatted. |
| BV | mypy | PASS: strict mypy; 698 source files. |
| BW | diff review | PASS: tracked diff and 48 new deliverables reviewed; git diff --check clean; 844 baseline hashes preserve earlier contracts/algorithms and completion reports; the version file and one regression-test selector are explicit exceptions; 14 tracked changes: 13 version/config/docs updates plus one earlier test correcting hash-order eligibility. |
| BX | secret/TODO scan | PASS: scripted secret/TODO/unfinished-work/whitespace scan; 892 deliverables including untracked files. |
| BY | benchmark/profile | Eight candidates, 16 fit operations, 48 reserved TRAIN rows, 24 VALIDATION pairs; 259 audit nodes/674150 bytes; 7880704 SQLite page bytes. Timings separate; no SLA. |
| BZ | dependencies | Python 3.11+; project dependencies=[]; standard library runtime only. |
| CA | remaining limitations | No AFRE-12/calibration adapter, IC/cost/composite/nested/coupled/partial/random/Bayesian/continuous selection, final refit or universal hardware bit identity. VALIDATION selection proves neither generalization nor profitability. |
| CB | exact AFRE-21 scope | Deferred Ensemble & Signal Fusion: fixed ensembles, TRAIN/VALIDATION-safe learned weights, justified stacking, point/probability/signal fusion, diversity diagnostics; model-health automation remains AFRE-22. |

## Final gates

| Gate | Check | Result |
| --- | --- | --- |
| 1 | focused AFRE-20 tests | PASS: 113 focused tests, 141.95 s. |
| 2 | full pytest | PASS: 2, 813 tests; zero failures/errors/skips; 4, 785.68 s. |
| 3 | branch-enabled combined coverage >=95% | PASS: 98.5327% combined; statements 99.1261%; branches 95.7114%; runtime source unchanged. |
| 4 | socket/DNS blocked full suite | PASS: entire successful 2, 813-test run; seven socket/DNS APIs blocked before imports; fresh-child guard proved even with replaced PYTHONPATH. |
| 5 | Ruff lint | PASS: Ruff lint. |
| 6 | Ruff format | PASS: Ruff format; 875 files. |
| 7 | strict mypy | PASS: strict mypy; 698 source files. |
| 8 | git diff --check | PASS: clean whitespace diff. |
| 9 | complete git status/diff review | PASS: 14 tracked modifications and 48 new files; no staged files; HEAD 400f980 unchanged; earlier contracts/algorithms and reports unchanged; version constants updated; one earlier test selects usable regime membership instead of the first hash. |
| 10 | secret scan | PASS: scripted scan of 892 deliverables. |
| 11 | TODO/FIXME scan | PASS: scripted unfinished-work scan of 892 deliverables. |
| 12 | migration success/rollback/future-schema | PASS: success/rollback/future 22 rejection; all prior DDL/metadata and representative rows preserved. |
| 13 | corruption | PASS: seven artifact payload classes, relational indexes/links, metadata and valid-hash usage forgery fail closed; triggers restored after tampering. |
| 14 | bounds | PASS: configured/absolute grid, payload, snapshot/publication and audit node/depth/byte bounds. |
| 15 | hash-seed determinism | PASS: fresh processes seeds 0/1/42/random reproduce semantic bytes. |
| 16 | insertion-order determinism | PASS: dimensions/values/recipes/samples and native upstream/request insertion reversals. |
| 17 | restart replay | PASS: native result/registry/model and all six family adapters replay after restart. |
| 18 | concurrency | PASS: real second writer appends TRAIN 20/VALIDATION 45/TEST 80 source revisions and later candidate space; old selection unchanged. |
| 19 | canonical candidate enumeration | PASS: independently checked four-combination Cartesian product and canonical sorting. |
| 20 | candidate bound | PASS: oversized grid rejected before fit and atomic budget rejection. |
| 21 | TRAIN-only fitting | PASS: native TRAIN cutoffs/matrices and mandatory FIT truth guards. |
| 22 | VALIDATION-only selection | PASS: exact VALIDATION source/truth support and fixed criterion/winner replay. |
| 23 | TEST leak protection | PASS: cached direct truth and stored held-out evaluation accesses through all roles/get/resolve/get_any; TEST payload unread; prior TEST reclassification rejected. |
| 24 | preprocessing isolation | PASS: native TRAIN-only preprocessing refit is idempotent; states/frozen transforms remain pinned. |
| 25 | MSE selection | PASS: independent/native MIN_MSE value and winner oracles. |
| 26 | MAE selection | PASS: independent/native MIN_MAE value and winner oracles. |
| 27 | R² selection | PASS: independent/native MAX_R2 value and winner; constant truth unavailable. |
| 28 | probabilistic criterion | PASS: native Gaussian CRPS/NLL selection and independent Gaussian/empirical score oracles. |
| 29 | IC/rank-IC if implemented | DEFERRED: unsupported criterion, documented and closed enum. |
| 30 | tie handling | PASS: fingerprint ties, direction-aware secondary lexicographic ordering. |
| 31 | failed candidate handling | PASS: actual native nonconvergence retained in full family, with no invented failed observations. |
| 32 | incompatible candidate handling | PASS: point candidates incompatible with probability criterion remain registered. |
| 33 | NO_VALID_CANDIDATE | PASS: all incompatible, insufficient-support and early-cutoff outcomes have no winner. |
| 34 | single-valid-candidate semantics | PASS: explicit permission required; sole valid candidate NONCOMPETITIVE. |
| 35 | resource-budget enforcement | PASS: complete reservations checked before fits; actual usage replay and forgery rejection. |
| 36 | AFRE-19 trial registration | PASS: exact full native trial/family pool including failures/incompatibility; cutoff changes distinct attempts. |
| 37 | AFRE-19 selection-event compatibility | PASS: exact native-event single-sample fixture plus honest median/mean mismatch case. |
| 38 | actual 1h/1d identity | PASS: actual one-hour/day native searches with disjoint candidate identities. |
| 39 | event/regime/nonlinear/sequence adapters | PASS: six native adapters including actual event/regime/nonlinear/sequence fits and VALIDATION forecasts. |
| 40 | AFRE-16 residual feature integration | PASS: actual declared causal residual scalar consumed by nonlinear candidate; earlier TEST samples excluded. |
| 41 | AFRE-18 cost criterion if implemented | DEFERRED: unsupported criterion, documented and closed enum. |
| 42 | no-direct external-engine regressions | PASS: repository-wide regression suite and source/dependency review; no direct AME/MCE/EIE dependency or runtime network. |
| 43 | docs consistency | PASS: 177 documents; exact 26-phase AFRE-0 through AFRE-25 roadmap, versions, local links, 80 report items and 46 gates. |
| 44 | demo | PASS: 35 verified offline demo steps; 166-node baseline lineage audit. |
| 45 | benchmark/profile | PASS: measured eight-candidate bounded workflow; timings/registry/audit/persistence/restart/storage and independent errors recorded. |
| 46 | dependency check | PASS: project dependencies=[]; Python 3.11+; stdlib runtime only. |

## Validation evidence

The initial frozen full run completed with 2, 812 passes and one failure in an earlier orthogonalization test. That test chose the first forecast by fingerprint and could select the fixture's intentionally late snapshot, whose membership is correctly unavailable. The test now explicitly selects a forecast with usable membership; its binding assertions remain intact. No native adapter, contract or algorithm changed. The isolated corrected test passed under branch coverage in 119.03 s, followed by a successful full pytest rerun.

Coverage combines the original full-run data with the corrected isolated test, against identical runtime source: 28, 356/28, 606 statements (99.1261%) and 5, 758/6, 016 branches (95.7114%), for 98.5327% combined coverage. The source/test/configuration freeze contained 699 hashes; every hash remained unchanged throughout the successful full run. Coverage was not rerun across the whole repository because this correction changed only the test selector.

The 35-step offline demo passed. Its baseline audit visited 166 nodes. The separate measured eight-candidate profile used 16 reserved fit operations, 48 reserved TRAIN rows and 24 VALIDATION pairs; the registry retained all eight candidates. Its audit visited 259 nodes/674, 150 serialized bytes, and SQLite used 7, 880, 704 page bytes. Independent metric-oracle maximum absolute error was 7.192163531399842e-15.

| Profile stage | Measured seconds |
| --- | --- |
| Enumeration | 0.004170 |
| Fitting orchestration | 2.102364 |
| AFRE-19 registration | 0.354950 |
| AFRE-19 completion | 2.284570 |
| VALIDATION scoring | 1.280417 |
| Selection decision | 2.509738 |
| Registry snapshot | 1.160245 |
| Atomic persistence | 1.146198 |
| Audit | 2.510104 |
| Restart | 1.126630 |

These timings describe the measured synthetic fixture and include native semantic validation. They are not a production SLA or a claim about larger searches.

## Final Git status

Branch `main`; HEAD `400f980d0023d3c23e3cf5ba0df770cd12631f3f` unchanged. Fourteen tracked files modified and 48 new files; nothing staged. No commit or push.

```text
 M README.md
 M docs/AFRE_MASTER_SPEC.md
 M docs/forecast-uncertainty-decomposition.md
 M docs/invariance-stability-research.md
 M docs/multiple-testing-controls.md
 M docs/nonlinear-feature-interactions.md
 M docs/research-reproducibility.md
 M docs/research-trial-registry.md
 M docs/stability-evaluation.md
 M docs/transaction-cost-aware-research.md
 M pyproject.toml
 M scripts/check_documentation.py
 M src/afre/version.py
 M tests/orthogonalization/test_workflow.py
?? benchmarks/selection_profile.py
?? docs/AFRE_20_COMPLETION_REPORT.md
?? docs/candidate-registry.md
?? docs/model-family-comparison.md
?? docs/model-selection-framework.md
?? docs/resource-budgets.md
?? docs/search-spaces.md
?? docs/selection-profile.json
?? docs/selection-reproducibility.md
?? docs/test-isolation-selection.md
?? docs/validation-selection.md
?? examples/selection_corrections.py
?? examples/selection_demo.py
?? examples/selection_fixture.py
?? examples/selection_horizons.py
?? examples/selection_oracles.py
?? examples/selection_orthogonal_fixture.py
?? src/afre/selection/__init__.py
?? src/afre/selection/accounting.py
?? src/afre/selection/admission.py
?? src/afre/selection/budgets.py
?? src/afre/selection/comparisons.py
?? src/afre/selection/criteria.py
?? src/afre/selection/decisions.py
?? src/afre/selection/definitions.py
?? src/afre/selection/engine.py
?? src/afre/selection/enumeration.py
?? src/afre/selection/fitting.py
?? src/afre/selection/geometry.py
?? src/afre/selection/guards.py
?? src/afre/selection/lineage.py
?? src/afre/selection/metadata.py
?? src/afre/selection/orthogonal_features.py
?? src/afre/selection/registry.py
?? src/afre/selection/repository.py
?? src/afre/selection/results.py
?? src/afre/selection/schema.py
?? src/afre/selection/scoring.py
?? src/afre/selection/snapshots.py
?? src/afre/selection/storage.py
?? src/afre/selection/validation.py
?? tests/selection/conftest.py
?? tests/selection/test_families_horizons.py
?? tests/selection/test_grid_bounds.py
?? tests/selection/test_metrics_decisions.py
?? tests/selection/test_pipeline.py
?? tests/selection/test_replay_audit.py
?? tests/selection/test_storage.py
```

See [framework](model-selection-framework.md), [measured profile](selection-profile.json) and [reproducibility](selection-reproducibility.md).

**Stop after AFRE-20.** AFRE-21 Ensemble & Signal Fusion remains deferred. Portfolio construction, risk optimization and execution remain downstream.

No staging, commit or push. Changes remain in the working tree for review.

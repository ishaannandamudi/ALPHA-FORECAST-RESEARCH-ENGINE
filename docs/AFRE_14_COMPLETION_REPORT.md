# AFRE-14 completion report

AFRE-14 — Temporal / Sequence Models. Engine 0.15.0, sequence schema 1.0,
shared store 1.14/user_version 15. Earlier public schemas remain 1.0.
Frozen roadmap:26 distinct phases, AFRE-0 through AFRE-25. Stop after AFRE-14.
No commit or push. Predictive metrics do not establish profitability.
Portfolio construction, risk optimization and execution remain downstream projects after AFRE.

| Item | Scope | Result |
| --- | --- | --- |
| A | architecture | Layered immutable causal window → TRAIN transform/dataset → fixed dynamics/QR readout → feature-only forecast → later evaluation; earlier public semantics preserved. |
| B | package structure | 21 focused modules in `src/afre/sequence`; immutable contracts, windows, source projection, transforms, fitting, prediction, evaluation, diagnostics, storage, validation, lineage and engine. |
| C | schema | Sequence schema 1.0; every earlier public schema remains 1.0. |
| D | engine/store versions | Engine 0.15.0; shared store 1.14; SQLite user_version 15. Additive 14→15 migration. |
| E | sequence feature definitions | Exact neutral scalar/interaction definition, semantic/version/unit, missing/alignment/availability/transform policy and implementation fingerprint. |
| F | window specifications | Origin cutoff, mode, count/duration/boundaries, minimum, padding, exact alignment, revision roster and time encoding pinned. |
| G | fixed-count windows | Latest N distinct admissible timestamps, with per-feature effective counts and no insertion-order dependency. |
| H | elapsed windows | Exact UTC nanosecond duration and open/closed lower/upper boundaries, followed by declared maximum count. |
| I | session windows | Unsupported; no informal session arithmetic or advertised calendar mode. |
| J | sequence observations | Exact source/vintage, instrument, observation time, final availability, finite value/missing quality and revision/source fingerprint. Referenced source retains six clocks; afre_ready_ns pins actual source processing separately from final historical availability. |
| K | canonical ordering | Increasing observation timestamps; canonical feature fingerprints. Revisions tie by availability, revision artifact ID and observation fingerprint. |
| L | revision semantics | Cutoff-first latest-available, exact-vintage or fail-on-multiple policies. Future revisions are excluded before resolution. |
| M | sequence snapshots | Exact origin, feature/window/candidate/selected IDs, times, values, masks, encodings, diagnostics and actual construction availability. Candidate evidence must be historically available and actually processed by construction; later audits retain their later clocks. |
| N | completeness | COMPLETE/PARTIAL/INSUFFICIENT/UNAVAILABLE; minimum effective timestamp rows and per-feature history requirements are explicit. |
| O | masking | Per-feature booleans; missing/padded None differs from real 0.0; missing/stale/invalid/withheld source reasons retained. |
| P | padding | FAIL_IF_SHORT, LEFT_PAD_MASKED and RIGHT_PAD_MASKED. Padding has no model influence. |
| Q | irregular-time handling | Actual UTC gaps retained; no assumed equal spacing. State updates are explicitly per unmasked observation. |
| R | time encoding | NONE, DELTA_SECONDS, AGE_FROM_ORIGIN and ordinal NORMALIZED_POSITION; padding None; no learned time scaling. |
| S | multi-feature alignment | Exact timestamp union and canonical feature order with independent masks. No interpolation, declared grid or latest-per-step mode. |
| T | event sequences | Existing event scalar attributes, exact occurrence and availability evidence; no event extraction or later unavailable attributes. |
| U | regime sequences | Existing FILTERED regime histories; SMOOTHED/EX_POST remain inadmissible. |
| V | microstructure sequences | Neutral external microstructure history through existing AFRE contracts; no AME dependency. |
| W | context sequences | Neutral context history with six-clock availability; no MCE dependency. |
| X | options sequences | Neutral options-derived scalar history; no options-engine implementation import. |
| Y | expert-output sequences | Exact causal expert/mixture scalar outputs, target/horizon compatibility and preserved lineage. |
| Z | nonlinear-feature sequences | Causal InteractionValue histories with exact source definitions, units, origin/availability and nested source checks. |
| AA | sequence datasets | Complete exact TRAIN sample/snapshot/target bindings, fold, canonical feature order, transform, target/horizon and computation fingerprint. |
| AB | training causality | Each token is available by its sample origin; targets are completed/known by fit cutoff. No held-out fitting. |
| AC | TRAIN-fitted transforms | Population means/scales over unmasked TRAIN tokens, with declared repeated-token sample weighting; zero scales reject. NONE records zero/unit state. |
| AD | model families | Only EXPONENTIAL_DECAY_LINEAR and LINEAR_STATE_SPACE; no broad search or dynamic provider execution. |
| AE | exponential-decay model | Unnormalized supplied nonnegative exponential age weights; TRAIN QR/fixed-ridge readout. |
| AF | state-space model | Stable supplied diagonal transition, positive gain, zero initial state, masked feature update skipped; exact recurrence/weights and trajectory retained. |
| AG | recurrent model | Unsupported. No learned tanh recurrence/RNN/LSTM is claimed. |
| AH | causal attention model | Unsupported. No attention heads/learned pooling or bidirectional future context is claimed. |
| AI | model spec | Exact target/features/window/fold/cutoff/seed/preprocessing/decay/state/gain/ridge/rank-condition policy/attestors/implementation; dimensions bounded by pinned feature count. |
| AJ | model artifact | Exact spec/dataset/transform/TRAIN IDs, family, intercept/readout, training loss, rank/condition, direct-solve convergence and actual fit clocks. |
| AK | bounded optimization | One deterministic AFRE-5 pivoted QR solve; fixed optional ridge unpenalized intercept; finite/rank/condition failures explicit. |
| AL | sequence forecast | Exact model/spec/snapshot/sample/security/origin/target/partition, value, aggregates, contributions, state trajectory, optional law and clocks. |
| AM | forecast availability | Model, transform, snapshot, optional base and actual computation must be available by cutoff. Later constructed snapshots cannot silently backdate forecasts. |
| AN | target-free application | Mandatory repository guard blocks TargetVintage, sequence training artifacts and earlier interaction training labels during prediction/replay/publication. |
| AO | model immutability | Inputs/models are immutable; corrections append new identities. Descriptive diagnostics never rewrite fitted artifacts. |
| AP | probabilistic conditioning | Compatible AFRE-6 location translation preserves law shape/scale and recomputes quantiles/events; no uncertainty decomposition. |
| AQ | calibration semantics | Upstream AFRE-7 states incompatible; dedicated sequence fitting unavailable. Explicit insufficient/unavailable/incompatible states; independent VALIDATION truth only. |
| AR | cross-sectional integration | Explicit derived neutral score into unchanged same-origin AFRE-9 ranking and IC; never portfolio weights. |
| AS | multi-horizon treatment | Independent actual 1h/1d target/spec/transform/dataset/model/forecast identities; no inferred joint covariance. |
| AT | contribution/internal diagnostics | Per-token standardized value, temporal weight, readout and contribution reconstruct output; linear state trajectory retained. Not causal importance. |
| AU | sequence stability | Compatible supplied fits report raw-scale coefficient ranges; independent oracle checks drift. Different fixed ridge penalties may form descriptive sensitivity comparisons. |
| AV | no-auto-refit | No diagnostic path mutates/retrains/prunes a model. No model search or winner promotion. |
| AW | coverage/exclusions | Eligible unique origins, completeness counts, effective history/gaps/ages, masks and explicit exclusion counts. |
| AX | truth/evaluation | Later exact pinned completed truth and point/proper scores with event/regime/family/horizon cohorts. |
| AY | matched comparison | Exact full sample/origin/security/target grid with point/nonlinear/mixture/sequence baseline values, same truth IDs and metric deltas. |
| AZ | TEST boundary | TEST cannot fit/choose transforms/windows/models or calibrate; evaluation uses existing explicit seals and repeat-use evidence. |
| BA | audit | Semantic replay verifies source, clocks, windows, masks/order, fitted readout, law, matched truths and earlier completed fits. |
| BB | lineage | Bounded unified lineage includes source/definition/vintage/candidate exclusions, TRAIN state/dataset/model, base law, ranking/evaluation and completed upstream fit records. |
| BC | persistence/migration | Additive transactional 14→15, rollback and future-schema rejection; immutable triggers; safe canonical JSON and verified family/schema/hash/index/links/orphans. |
| BD | indexes/performance | Feature/source, window/security/origin, target/horizon/family, model/spec/availability, evaluation cutoff/TEST and reverse reference indexes. Bounded LIMIT+1 queries. |
| BE | deterministic replay | Canonical semantic bytes across seeds 0/1/42/random, reversed observations/features/requests, and verified reopening. |
| BF | concurrency | Second writers append source observations, target bar corrections and later fit identities during frozen snapshot/predict/fit/evaluation; pinned computation unchanged. |
| BG | numerical correctness | Independent exact windows/boundaries/deltas/population normalization/half-life weights/masked recurrence/ridge solver/probability shift/metric deltas/coefficient ranges. Numerical evidence below. |
| BH | security | No eval/exec/pickle/joblib/shell/network/dynamic executable imports/provider paths; static closed-boundary checks and socket/DNS-blocked tests. |
| BI | documentation | Eight required guides, profile and A–BT report; README/master and all requested integrations plus stale roadmap references updated. Exact 26 phases AFRE-0 through AFRE-25 preserved. |
| BJ | tests added | Focused window, availability, numerical, workflow, training isolation, TEST/calibration, horizons, migration/corruption/immutability, bounds, concurrent writer, security and subprocess replay tests. |
| BK | full pytest | PASS:1904 tests in 1333.92s (22m 13s), with socket/DNS blocking; every earlier test retained without weakening. |
| BL | coverage | PASS: 98.89608234% combined, 99.39722725% statement and 96.51384909% branch; required combined threshold 95%. |
| BM | Ruff | PASS: full repository lint; all 586 Python files already formatted. |
| BN | mypy | PASS: strict source/examples/benchmarks/tests/scripts check, 464 source files. |
| BO | diff review | Complete tracked/new file review, whitespace check and baseline hash comparison; no earlier source/test changes except version constants. |
| BP | secret/TODO scan | PASS: scripted secret, unfinished-marker and whitespace scan across 596 deliverables. |
| BQ | benchmark/profile | Bounded socket/DNS-blocked causal profile with separate 3200 inference-kernel repetitions; no claim of 3200 additional causal TRAIN rows or production SLA. |
| BR | dependencies | Python 3.11+ and zero runtime dependencies; no ML framework added. |
| BS | remaining limitations | Two fixed dynamics families; no learned state dynamics/session windows/grid fill/recurrent/attention/sequence calibrator/joint horizon law. Source honesty remains an upstream audit trust boundary. No profitability claim. |
| BT | exact AFRE-15 scope | Forecast Uncertainty Decomposition only: identifiable aleatoric/epistemic, model/parameter/expert-disagreement/regime/event/data-quality/horizon uncertainty and calibrated diagnostics with explicit identifiability limits. No AFRE-15 implementation; no orthogonalization yet. |

## Validation evidence

Focused frozen-input run: **140 passed in 305.94s**, socket/DNS blocked.
Sequence combined coverage: **98.96788991%**;
statement coverage: **99.23717060%**;
branch coverage: **97.68211921%**.
Full ordinary suite: **1904 passed in 1333.92s (22m 13s)**, socket/DNS blocked.
Full branch-enabled suite: **1904 passed in 2517.46s (41m 57s)**.
Combined coverage: **98.89608234%**;
statement coverage: **99.39722725%** (19788/19908);
branch coverage: **96.51384909%** (4042/4188).
The required combined coverage threshold is 95%.
The full suite automatically blocks sockets and DNS, including subprocess replay workers.
The numerical profile records maximum readout oracle error **2.615746161338528e-15**;
known decay/recurrence/boundary fixtures use independent expected arithmetic.
The offline demo completes all 37 requested steps, including source correction, actual 1h/1d
models, matched truths, no-auto-refit, persist/reopen and bounded 786-node lineage.

[Architecture](temporal-sequence-models.md), [profile](sequence-benchmark.md),
[recorded measurements](sequence-profile.json), [master roadmap](AFRE_MASTER_SPEC.md).

## Quality gates

| # | Required gate | Result |
| --- | --- | --- |
| 1 | focused AFRE-14 tests | PASS — 140 focused tests; 98.96788991% combined sequence coverage. |
| 2 | full pytest | PASS — 1904 tests in 1333.92s; all prior 1764 tests retained. |
| 3 | branch-enabled coverage >=95% | PASS — full combined 98.89608234%, statement 99.39722725%, branch 96.51384909%. |
| 4 | socket/DNS blocked full suite | PASS — full ordinary and coverage runs deny sockets and DNS; replay workers also deny both. |
| 5 | Ruff lint | PASS — full repository lint. |
| 6 | Ruff format check | PASS — 586 files already formatted. |
| 7 | strict mypy | PASS — strict check of 464 source files. |
| 8 | git diff --check | PASS — no whitespace errors. |
| 9 | full git status/diff review | PASS — all 66 changed files reviewed; 16 tracked modifications and 50 untracked files; nothing staged. |
| 10 | secret scan | PASS — scripted scan of 596 deliverables. |
| 11 | TODO/FIXME scan | PASS — scripted unfinished-marker scan of 596 deliverables. |
| 12 | migration success/rollback/future-schema | PASS — test_migration_preserves_prior_layout and test_rollback_and_future. |
| 13 | corruption | PASS — semantic forgery and SQL family/schema/hash/index/link/orphan corruption fail closed. |
| 14 | bounds | PASS — positive/lower/work/query/serialized/audit node and depth bounds. |
| 15 | hash-seed determinism | PASS — fresh subprocesses with seeds 0, 1, 42 and random. |
| 16 | insertion-order determinism | PASS — reversed observations, sequence features and requests across all four seeds. |
| 17 | restart replay | PASS — persisted/reopened semantic bytes agree across all eight replay cases. |
| 18 | concurrency | PASS — second-writer source, target, model and combined corrections preserve frozen computations. |
| 19 | future-observation leakage | PASS — upstream publication cannot bypass AFRE receipt or source processing clocks; future candidates excluded. |
| 20 | revision leakage | PASS — later revisions excluded before explicit revision-policy resolution. |
| 21 | exact window semantics | PASS — fixed-count and all four elapsed-window inclusivity combinations. |
| 22 | masking/padding | PASS — every padding policy and source quality; genuine zero remains unmasked. |
| 23 | irregular-time encoding | PASS — all four time encodings with actual gaps and masked padding. |
| 24 | TRAIN transform isolation | PASS — held-out values leave TRAIN snapshot, normalization and fit identities unchanged. |
| 25 | event sequence | PASS — neutral event histories with causal occurrence/attribute availability. |
| 26 | regime sequence | PASS — FILTERED histories accepted; SMOOTHED/EX_POST rejected. |
| 27 | microstructure sequence | PASS — neutral external microstructure history. |
| 28 | context sequence | PASS — neutral external context history. |
| 29 | options sequence | PASS — neutral external options-derived history. |
| 30 | expert sequence | PASS — causal expert/mixture histories and exact target/horizon checks. |
| 31 | nonlinear sequence | PASS — nonlinear interaction histories with raw source lineage. |
| 32 | no-direct external-engine regressions | PASS — static closed-implementation regression; no specialist-engine imports or sibling paths. |
| 33 | held-out label leakage | PASS — held-out labels leave model identity and parameters unchanged. |
| 34 | target-free prediction | PASS — guarded prediction rejects target/training records; only feature-side artifacts are read. |
| 35 | model immutability | PASS — immutable SQLite records, input/model byte comparison, idempotence and replay. |
| 36 | causal attention if implemented | NOT APPLICABLE — causal attention is unsupported; neither implemented family uses future tokens. |
| 37 | probability shift | PASS — translated location preserves distribution shape and scale; quantiles/events recomputed. |
| 38 | calibration compatibility | PASS — upstream incompatible calibrators rejected; explicit insufficient/unavailable/incompatible assessment states. |
| 39 | cross-sectional rank | PASS — derived neutral score feeds existing ranking and exact truth/cutoff IC linkage. |
| 40 | multi-horizon identity | PASS — actual 1h and 1d models/datasets/forecasts have distinct identities. |
| 41 | matched evaluation | PASS — point/nonlinear/mixture/sequence comparisons pin identical samples/origins/targets/truths. |
| 42 | contribution/model-internal diagnostics | PASS — exact decay/state contributions reconstruct forecasts and preserve masks. |
| 43 | stability | PASS — independent raw-scale coefficient range oracle for compatible fits. |
| 44 | no-auto-refit | PASS — descriptive diagnostics leave repository models and bytes unchanged. |
| 45 | TEST boundary | PASS — TRAIN-only fitting; later evaluation preserves existing TEST seal/reuse rules. |
| 46 | docs consistency | PASS — 122 documents, exact 26-phase AFRE-0–AFRE-25 roadmap and all 72 A–BT items. |
| 47 | demo | PASS — all 37 offline steps; bounded 786-node unified lineage. |
| 48 | benchmark/profile | PASS — offline profile; independent readout maximum error 2.615746161338528e-15; timing/storage results recorded. |
| 49 | dependency check | PASS — Python 3.11+; zero runtime dependencies; no ML framework. |

## Review and working-tree state

Baseline commit remains `da088f3` on `main`, tracking `origin/main`.
All 465 frozen Python/configuration files match the hashes used for the final gate runs.
All earlier source, tests, examples and benchmarks retain their baseline bytes except
`src/afre/version.py`; the documentation checker and package version were updated for AFRE-14.
There are 66 changed files: 16 tracked modifications and 50 untracked additions.
No files are staged, deleted or committed. No commit or push was performed.

Added deliverables are the 21-module sequence package, 14 test-package files,
three sequence example/oracle files, the sequence profile benchmark and 11 documentation/profile files.
Existing edits are README, master specification, requested integration guides,
two stale current roadmap references, version constants, package version and the documentation checker.

AFRE-15 remains deferred: **Forecast Uncertainty Decomposition**, with explicit identifiability
limits. Signal orthogonalization remains AFRE-16. No later phase has been implemented.

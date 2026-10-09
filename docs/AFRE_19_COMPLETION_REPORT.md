# AFRE-19 completion report

Verified complete, 2026-10-09. Current working tree resumed from committed AFRE-18
HEAD `fd4f92fbad7a17ba43a16521a2b6f5b8b19e2392`; earlier implementation/tests/reports preserved.
Engine 0.20.0; multiple-testing schema 1.0; store 1.19/SQLite 20; zero runtime dependencies.
Frozen roadmap: 26 distinct phases, AFRE-0 through AFRE-25. No commit or push.

| Item | Topic | Result |
| --- | --- | --- |
| A | architecture | Additive declared-opportunity evidence layer over native AFRE-5–18; separate planning, completion, inference and descriptive diagnostics. |
| B | package structure | 26 modules in src/afre/multiple_testing; five native fixture/workflow/demo/replay/oracle examples, focused tests and bounded profile. |
| C | schema | Closed immutable dataclass contracts, canonical structured JSON and domain-separated fingerprints; multiple-testing schema 1.0. |
| D | engine/store versions | Engine 0.20.0; store 1.19/SQLite user_version 20; all prior public schemas 1.0 unchanged. |
| E | research trials | TrialSpecification plans an opportunity; ResearchTrial records one completion with exact native observations/exclusions and result/seal references. |
| F | trial identity | Attempt, hypothesis, target/horizon, dataset/fold, source streams, inspected choices, preprocessing/model refs, environment and cost scenario all affect identity. |
| G | hypotheses | Explicit conditional fair nonzero-sign null, alternative, metric, effect definition, target/horizon, method, assumptions, support and declaration. |
| H | hypothesis direction | TWO_SIDED, GREATER and LESS are explicit identity-bearing directions; no post-hoc flip API. |
| I | hypothesis families | Exact planned attempt IDs; primary/additional methods, explicit level, dependence and caller-attested declaration are frozen. |
| J | family membership | No inferred family, outcome-dependent pruning or chosen denominator; all exact declared attempts consume slots. |
| K | family completeness | COMPLETE requires every declared attempt completed, including unsuccessful ones; OPEN/PARTIAL are interim and INVALID incompatible. |
| L | p-value artifacts | Raw p-value/status/statistic and total/informative/zero counts retained independently of effects. |
| M | effect-size artifacts | Descriptive sample median minus declared null in native metric units; no fabricated CI or standard error. |
| N | supported raw tests | Exact conditional one-sample and paired sign tests; normal-mean and correlation inference explicitly unsupported. |
| O | test assumptions | Caller attests independent fair nonzero signs, exact pairing and nonoverlap; native per-security label intervals checked. Financial independence is not established by timestamps. |
| P | Bonferroni | min(1,m*p), using complete declared m including unavailable/failed slots. |
| Q | Holm | Stable (p, immutable plan ID) step-down; running maximum enforces monotone adjusted p. |
| R | Benjamini-Hochberg | Stable reverse running minimum of m*p/rank; independent or PRDS hypothesis dependence required for inference. |
| S | Benjamini-Yekutieli | Fully implemented harmonic-factor BY, with independent arithmetic fixtures; arbitrary dependence allowed only for valid marginal p-values. |
| T | FWER semantics | Bonferroni/Holm nominal family-wise error semantics; cross-hypothesis independence not required, raw sign observation assumptions remain required. |
| U | FDR semantics | BH/BY nominal expected false-discovery proportion semantics, not posterior probability that an individual finding is false. |
| V | adjusted results | Rows pin family/spec/plan/hypothesis/trial/raw/effect, m, raw/adjusted values, level, rank, rejection/status and availability. |
| W | effect preservation | All methods point to the original immutable effect artifact; no correction shrinkage. |
| X | selection events | Caller-recorded complete candidate pool and chosen identities, metric, orientation, rule, ordering, cutoff and TEST flag. |
| Y | selection rules | MAX_METRIC, MIN_ERROR, TOP_K and DECLARED_THRESHOLD validate caller outcomes; no model promotion. |
| Z | selection-bias diagnostics | Full candidate count, winner/median/runner-up spreads, exact adjusted evidence and TEST-use count; missing metrics prevent full-pool spread claims. |
| AA | repeated TEST counts | Exact native seal IDs/counts and dataset/fold/target/horizon/metric scope; each registered sealed attempt counts. |
| AB | TEST reuse | Explicit predeclared heavy threshold; tracked FIRST_USE/REUSED/HEAVILY_REUSED; global UNTRACKED native history remains visible; validation-only INCOMPATIBLE. |
| AC | research chronology | Immutable completion chronology and known parent result availability retained in exact registry snapshots. |
| AD | adaptivity | PREDECLARED is caller attestation, ADAPTIVE requires available parent trial IDs, UNKNOWN stays explicit; adaptive/unknown final families remain interim. |
| AE | data-snooping diagnostics | Counts distinct hypotheses, targets/horizons, metrics, sources, environments, costs and choice sets plus repeated assessments. Correction does not remove data snooping. |
| AF | deflated-statistic support/limitations | Deflated performance always UNSUPPORTED: no portfolio-return series or justified generic deflation; AFRE-18 arithmetic contributions never converted into Sharpe. |
| AG | trial registry | Whole visible plans/families/trials/selection events/native seals by cutoff; new snapshots cannot choose a subset. |
| AH | append-only semantics | Immutable tables and unique one-completion-per-plan index; exact republish idempotent; reevaluation needs a new attempt. |
| AI | trial source integrations | Native point, probabilistic, calibrated, horizon-set, ranking context, event, regime, mixture, nonlinear, sequence, uncertainty context, residual, environment and cost scenario sources. Ranking-context registration does not invent IC inference. |
| AJ | target/horizon identity | Actual native 1h and 1d targets, folds, source/sample grids and trial IDs remain separate opportunities. |
| AK | environment trial accounting | Two native PIT time-window environments count independently; exact membership weights/availability retained; unsupported soft weighted sign inference not manufactured. |
| AL | cost-scenario trial accounting | Two explicitly declared AFRE-18 scenarios count independently; NET_CONTRIBUTION reads exact native evaluation rows/units/truth and hypothetical arithmetic semantics. |
| AM | paired-sample semantics | One producer per side; exact ResearchSample/TargetVintage intersection and origin/units required. Missing right-side rows create explicit exclusions. |
| AN | missing/failed trials | FAILED/UNAVAILABLE attempts contain no fabricated observations; INSUFFICIENT/UNSUPPORTED raw slots remain visible. |
| AO | family-size semantics | Every exact planned attempt is included in m; absent raw evidence is p=1 internally and nullable externally. |
| AP | open/interim families | OPEN/PARTIAL reports have no final rejection; invalid/adaptive/retrospective/unknown interpretation limits explicit. |
| AQ | alpha/q semantics | No hidden alpha/q; mandatory 0<level<1 pinned before the held-out boundary with every reported correction. |
| AR | tie handling | Immutable identity resolves p-value and selection ties; declaration/request order does not affect semantic bytes. |
| AS | multi-metric treatment | Metric changes create new hypothesis/attempt identities; mixed units or sample/truth protocols cannot be silently combined for selection. |
| AT | TEST boundary | Native TEST seals retained; family/method/null/direction/metric/level immutable. TEST truth corrections cannot alter frozen definitions/results. |
| AU | declaration/predeclaration semantics | Declaration checked against native TRAIN cutoff; timestamps/attestors do not prove genuine human preregistration or unregistered research completeness. |
| AV | target-free registration | Hypothesis/plan/family registration runs under target-free guards. Cached get_any target exposure is blocked at the AFRE-19 boundary without changing prior contracts. |
| AW | correction semantics | Bonferroni/Holm/BH/BY arithmetic deterministic and bounded; effect estimates and raw statistical evidence remain separate. |
| AX | no-auto-research-loop | No automatic hypothesis generation, follow-up loops or threshold optimization. |
| AY | no-auto-promotion | No automatic selection/promotion API; native model artifacts remain unchanged during analysis. |
| AZ | no-auto-prune | No significance-dependent deletion/pruning; failed and nonsignificant attempts stay registered. |
| BA | audit | Bounded composition audit with 2008 nodes in the demo, explicit interpretation limitations and native completed-fit witnesses. |
| BB | lineage | Exact source, TRAIN fit, target/truth, environment, cost and TEST lineage; cycle/node/depth/byte admission fails closed. |
| BC | persistence/migration | Transactional19→20 migration, rollback and future-version rejection; prior DDL/metadata/rows preserved. Semantic forgery and relational/hash corruption reject. |
| BD | indexes/performance | Four additive tables, nine indexes, ten immutable triggers; compound family/hypothesis/plan, source, target/horizon/dataset/fold, metric, clocks, selection, reverse links and seal indexes. |
| BE | deterministic replay | Eight fresh offline builds across seeds 0/1/42/random and normal/reversed hypotheses/family/trials/requests; canonical restart digest compared. |
| BF | concurrency | Real second SQLite writers append target corrections/trials during frozen reads; pinned old registry/adjusted bytes remain unchanged. |
| BG | numerical correctness | Independent sign enumeration, known exact fractions and correction fixtures; effects, TEST counts and winner spreads verified. Profile maximum fixture error 0.0; broader Fraction oracles tolerate at most2e-16. |
| BH | security | Closed JSON, fingerprints, explicit limits and semantic replay; no executable hypothesis data, eval/exec/pickle/joblib/network/shell/dynamic imports/external-engine dependency. |
| BI | documentation | Eight requested guides, active integrations/README/master, measured JSON profile and exact 26-phase roadmap consistency checks; prior completion reports unchanged. |
| BJ | tests added | Focused AFRE-19 numerical, semantic, native, guard, registry, selection, storage/migration, corruption, bounds, concurrency, security and replay regressions. 208 new tests; committed AFRE-18 baseline 2492 tests, total 2700. |
| BK | full pytest | PASS: 2700 tests in 8869.60s (2h27m49s); all 2492 earlier tests plus 208 AFRE-19 cases. Zero failures, errors or skips; all seven socket/DNS surfaces blocked. |
| BL | coverage | PASS: 98.67% combined statement/branch coverage (required >=95%); 99.26% statements and 95.85% branches. 26991/27191 statements and 5456/5692 branch destinations covered; branch coverage enabled. |
| BM | Ruff | Ruff lint and format pass across the full repository. |
| BN | mypy | Strict mypy passes over 660 Python files in src/examples/benchmarks/tests/scripts. |
| BO | diff review | PASS: full tracked diff and new deliverables reviewed; all 661 frozen code/configuration files unchanged during verification. Baseline 790 files checked; earlier implementation/tests/examples/benchmarks/reports preserved. 18 modified and 54 new files, all unstaged; HEAD unchanged and index empty. |
| BP | secret/TODO scan | PASS: repository script checks 844 deliverables for secrets, unfinished-work markers, whitespace and executable boundary regressions; git diff --check passes. |
| BQ | benchmark/profile | Measured bounded native profile: 25 trials, 4 reports, 239 AFRE-19 artifacts, 505387 payload bytes, 2008 audit nodes; separate 2000-slot arithmetic workload. No capacity extrapolation. |
| BR | dependencies | Python 3.11+; runtime dependencies=[]; exact stdlib arithmetic and native AFRE contracts only. |
| BS | remaining limitations | Conditional sign independence/fairness caller-attested; floating tails rounded with conservative positive saturation. Unregistered human research unknown. Parametric inference/CI/SE/deflation unsupported; no causal/profitability proof. |
| BT | exact AFRE-20 scope | AFRE-20 remains deferred: Hyperparameter & Model Selection Framework. Explicit candidates/search spaces; TRAIN/VALIDATION selection; deterministic search; no TEST tuning; candidate registry; budgets; stable ties; criteria; model-family comparisons; nested selection when needed. No ensemble fusion until AFRE-21. |

## Final quality gates

| Gate | Requirement | Result |
| --- | --- | --- |
| 1 | focused AFRE-19 tests | PASS: 207 focused cases in 1636.16s plus separate fresh replay in 1047.15s; all 208 AFRE-19 cases also passed in the full coverage run. |
| 2 | full pytest | PASS: 2700 tests in 8869.60s; zero failures/errors/skips, including all 2492 earlier tests and 208 AFRE-19 cases. |
| 3 | branch-enabled coverage >=95% | PASS: 98.67% combined, 99.26% statements, 95.85% branches; branch coverage enabled; >=95% required. |
| 4 | socket/DNS blocked full suite | PASS: full 2700-case run blocks socket, create_connection, getaddrinfo, gethostbyname, gethostbyname_ex, gethostbyaddr and socketpair before pytest imports; replay children block the same seven surfaces. |
| 5 | Ruff lint | PASS: ruff check . across the full repository. |
| 6 | Ruff format | PASS: ruff format --check .; 828 files formatted. |
| 7 | strict mypy | PASS: strict mypy; 660 source/example/benchmark/test/script files. |
| 8 | git diff --check | PASS: git diff --check. |
| 9 | full git status/diff review | PASS: full tracked/new-file review; all 661 frozen code/configuration files unchanged; prior contracts/tests/reports preserved; HEAD unchanged, index empty, 72 unstaged/new files. |
| 10 | secret scan | PASS: scripted repository scan; 844 deliverables checked. |
| 11 | TODO/FIXME scan | PASS: scripted TODO/FIXME/unfinished-work scan; 844 deliverables checked. |
| 12 | migration success/rollback/future-schema | PASS: prior nonempty DDL/metadata/rows preserved; transactional rollback and future schema rejection. |
| 13 | corruption | PASS: semantic, relational, projection, metadata and valid-hash forgery rejected. |
| 14 | bounds | PASS: contract, registry, snapshot, payload, lineage node/depth/byte limits fail closed. |
| 15 | hash-seed determinism | PASS: fresh seeds 0/1/42/random produce identical canonical digest; dedicated and full-suite replay runs both passed. |
| 16 | insertion-order determinism | PASS: normal/reversed hypothesis, family, trial and correction-request insertion order in eight fresh builds. |
| 17 | restart replay | PASS: eight fresh builds and restart retain semantic bytes; full-run replay passed in 863.129s. |
| 18 | concurrency | PASS: second SQLite writers cannot change frozen trial, registry or adjusted evidence. |
| 19 | exact sign test | PASS: independent integer enumeration and known exact one/two-sided sign fixtures. |
| 20 | Bonferroni | PASS: independent Fraction oracle with full declared denominator. |
| 21 | Holm | PASS: independent Fraction oracle; stable ties and monotone step-down values. |
| 22 | BH | PASS: independent Fraction oracle; explicit dependence requirements and monotone step-up values. |
| 23 | tie handling | PASS: immutable identity resolves correction and selection ties; order invariant. |
| 24 | family-size semantics | PASS: failed, unavailable, unsupported and missing opportunities all retain declared slots. |
| 25 | open-family semantics | PASS: OPEN/PARTIAL reports cannot make final rejection; COMPLETE cannot omit an attempt. |
| 26 | p-value bounds | PASS: invalid p-values rejected; positive extreme tails conservatively saturate. |
| 27 | effect preservation | PASS: all four corrections retain the exact original effect artifact. |
| 28 | TEST reuse | PASS: exact native seals, counts 1/2/3, heavy threshold, untracked and validation-only statuses. |
| 29 | adaptive status | PASS: adaptive/unknown families retain explicit interim interpretation and parent chronology. |
| 30 | selection event | PASS: four caller-recorded rules and full candidate pool; forged selection outcomes reject. |
| 31 | winner-spread diagnostics | PASS: independent winner/median/runner-up spread fixtures; missing candidates suppress full-pool claims. |
| 32 | no auto-selection | PASS: analysis never selects/promotes/searches automatically; model artifacts unchanged. |
| 33 | no auto-prune | PASS: failed and nonsignificant opportunities remain present; no outcome-driven pruning. |
| 34 | target-free registration | PASS: target-free registration and cached later-truth/result reads blocked. |
| 35 | held-out family isolation | PASS: native TEST truth corrections cannot mutate frozen family definitions/results. |
| 36 | AFRE-5 through AFRE-18 source integration | PASS: native AFRE-5–18 complete-family integration; ranking context has no fabricated IC inference. |
| 37 | actual 1h/1d identity | PASS: actual native 1h and 1d targets/folds/sources retain separate opportunity identities. |
| 38 | multi-environment family | PASS: two distinct PIT environments retain separate opportunity slots and exact membership. |
| 39 | multi-cost family | PASS: two distinct native cost scenarios retain separate opportunity slots and units. |
| 40 | matched sample/truth semantics | PASS: exact per-side sample/truth/origin/unit matching; missing paired rows remain exclusions. |
| 41 | no-direct external-engine regressions | PASS: AFRE-19 AST/import regression rejects direct external-engine and executable runtime dependencies. |
| 42 | docs consistency | PASS: documentation checker validates 168 documents, exact 26 phase names/count, versions, links, preserved historical reports, all 72 A–BT items and 45 gates. |
| 43 | 36-step demo | PASS: all 36 checked native demo steps; independent correction-oracle maximum error 0.0. |
| 44 | benchmark/profile | PASS: measured native25-trial/4-report profile; 239 artifacts, 2008 audit nodes, explicit overlapping timings. |
| 45 | zero runtime dependency check | PASS: pyproject runtime dependencies=[]; Python 3.11+ and stdlib/native AFRE only. |

## Reproduction and measured limits

Run `.venv311/bin/pytest -q tests/multiple_testing`, `.venv311/bin/ruff check .`,
`.venv311/bin/ruff format --check .`, `.venv311/bin/mypy`, `git diff --check`,
`PYTHONPATH=src .venv311/bin/python scripts/check_repository.py` and
`PYTHONPATH=src .venv311/bin/python scripts/check_documentation.py`.
The final full suite blocks socket construction, create_connection, getaddrinfo,
gethostbyname, gethostbyname_ex, gethostbyaddr and socketpair before pytest imports,
and runs `--cov=afre --cov-branch --cov-report=json --cov-report=term-missing`.
Fresh replay children also block all seven surfaces before AFRE imports.

The [36-step demo](../examples/multiple_testing_demo.py) verifies native sources,
unsupported/failed slots, OPEN/COMPLETE, TEST reuse, adaptivity, caller-recorded selection,
median/runner-up gaps, preserved effects/old results, actual 1h/1d, environments/costs,
registry, restart/digest and bounded lineage. The [measured profile](multiple-testing-profile.json)
reports each timed stage separately, including registration/context and family construction separately, trial publication,
family correction/publication, persistence admission/insertion, registry, audit and restart. Substage timing overlaps inclusive stage timing. Native source construction is
reported separately; 2000-slot arithmetic is a separate measurement, not native capacity.

See [controls](multiple-testing-controls.md), [registry](research-trial-registry.md),
[families](hypothesis-families.md), [FWER](fwer-controls.md), [FDR](fdr-controls.md),
[TEST reuse](test-reuse.md), [selection](selection-bias.md), [overfitting](research-overfitting.md).

**Stop after AFRE-19.** AFRE-20 Hyperparameter & Model Selection Framework remains deferred.
No commit, push, model promotion, portfolio construction, risk optimization or execution.

Dedicated fresh replay: eight builds passed in 1047.15s; all use semantic digest `d7c5ac84433bf9b1163baed547159e0c499b672767b68e256d8eb2955ab732ff`. Final 36-step demo maximum correction-oracle error 0.0.

Final verification evidence: coverage 7.16.2 JSON reports branch coverage enabled, 27191 statements, 5692 branches, 200 missing statements and 236 missing branches. The full JUnit record contains 2700 cases, 208 for AFRE-19, with zero failures/errors/skips. The full AFRE-19 replay test passed in 863.129s; all 208 AFRE-19 cases total 3416.952s of recorded test time.

Git state at verification: branch `main`, HEAD `fd4f92fbad7a17ba43a16521a2b6f5b8b19e2392`; 18 tracked modifications and 54 new deliverables (72 total), no staged files, no commit or push. AFRE-20 remains unimplemented.

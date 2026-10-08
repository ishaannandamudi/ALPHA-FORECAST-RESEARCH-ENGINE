# AFRE-18 completion report — A–BS

Client date: 2026-10-07. Implemented scope: Transaction-Cost-Aware Research Evaluation.
AFRE-0 through AFRE-18 complete; engine 0.19.0, transaction-cost-research schema 1.0,
shared store 1.18/SQLite 19. Earlier public schemas remain 1.0; runtime dependencies empty.
The frozen advanced roadmap remains 26 distinct phases, AFRE-0 through AFRE-25.

All 50 quality gates pass. The full suite passed 2,492 tests in 4,601.13 seconds
(1:16:41), with socket/DNS blocked before collection and throughout execution.
Combined statement/branch coverage is 98.645787%; statement coverage is 99.250311%
and branch coverage is 95.773348%. The 617 Python/config files match the frozen manifest.
No changes are staged; HEAD is unchanged. No commit or push was made.

| Item | Scope | Implementation and evidence |
| --- | --- | --- |
| A | architecture | Provider-neutral immutable inputs → frozen per-security path → component/total cost → later truth evaluation → diagnostics; no execution or optimization interfaces. |
| B | package structure | 23 small modules in src/afre/costs separate contracts, inputs, sources, exposure/turnover, numerical models, aggregation, diagnostics, storage/replay and lineage. |
| C | schema | Transaction-cost-research schema 1.0; all earlier public schema constants and contracts unchanged. |
| D | engine/store versions | Engine 0.19.0; shared store 1.18, SQLite 19. Additive transactional 18→19 migration preserves prior DDL, metadata and rows. |
| E | cost component types | SPREAD, EXPLICIT_FEE, SLIPPAGE, MARKET_IMPACT and CUSTOM_COST implemented. BORROW_COST is typed but explicitly unsupported by component specs. |
| F | cost input references | Immutable exact security/provider/source/version/schema/venue/unit/as-of refs retain quality, revision, six clocks and qualified reconstruction evidence. |
| G | unit semantics | Bps, return fraction, price, currency/unit and currency total convert through explicit price/notional into compatible RETURN_FRACTION contributions; UNIT_QUANTITY only for liquidity. No FX mixing. |
| H | cost scenarios | Exact target/horizon/fold/source/sample IDs, rule, complete component bindings, liquidity, timing, participation, units, age, missing/fallback, quality and declaration are identity-bearing. |
| I | evaluation timing modes | HISTORICAL_CAUSAL final availability ≤ exact origin cutoff; EX_POST_RESEARCH explicitly permits later evidence, never origin-time metadata. |
| J | exposure rules | SIGN, THRESHOLD_SIGN, FIXED_UNIT_NOTIONAL and DECLARED_SCALAR_EXPOSURE; closed parameters and exact threshold units. RANK_BUCKET unsupported. |
| K | exposure bounds | Explicit finite min/max within −100..100 containing 0, participation ≤ declared maximum ≤ 1, lowered runtime work/payload bounds. |
| L | position-change semantics | Per stable security ordered trade_delta = exposure−prior exposure, exact prior sample ID; same-time security ambiguity rejects. |
| M | turnover | Sum absolute exposure changes; explicit ZERO/DECLARED_INITIAL, no terminal liquidation, no pool-exit close or cross-security netting. Full-path deltas survive exclusions/cohorts. |
| N | gross research return | Exposure × exact immutable simple-return TargetVintage known by evaluation cutoff. Truth cannot enter path/cost metadata. |
| O | net research return | Gross−sum compatible costs; retains gross, cost and net separately. Arithmetic contributions only, no equity/compounding/portfolio PnL. |
| P | round-trip semantics | Per-side/per-turnover, declared round-trip halving and flat PER_TRADE currency fees are explicit. Spread side conversion cannot double halve. |
| Q | spread costs | FIXED_HALF_SPREAD and OBSERVED_BID_ASK_SPREAD with positive exact bid≤ask and explicit FULL_SPREAD/2 crossing convention. |
| R | explicit fees | Generic explicit bps/return/quantity/notional/flat per-trade fees; no hardcoded venue behavior, maker/taker assumptions or rebates. |
| S | slippage | Fixed rates, provider estimates and explicit linear/sqrt participation slippage. No fill behavior claim. |
| T | market impact | Linear coefficient_bps×p and sqrt coefficient_bps×sqrt(p), plus neutral provider estimates; horizon/version/quality/liquidity pinned. |
| U | participation | Hypothetical quantity/declared volume; excess declared bound rejects without clipping. Quantity=abs(delta)×reference notional/reference price. |
| V | liquidity inputs | Explicit provider-neutral exact price/notional/positive horizon-bound volume refs. Missing liquidity cannot silently receive an inferred fallback. |
| W | external microstructure/TCA inputs | Neutral provider MODEL_VALUE cost estimates and available-volume/quote evidence; no actual AME/MCE/EIE/options/TCA imports or copied algorithms. |
| X | cost quality states | VALID/MISSING/STALE/DEGRADED/UNSUPPORTED/INVALID; degradation requires scenario opt-in; missing costs retain explicit reasons. |
| Y | missing/fallback semantics | FAIL, EXCLUDE_SAMPLE or identity-bearing DECLARED_FALLBACK rate. No hidden5bps/zero fallback; only known zero trade or explicit zero rate is zero. |
| Z | component estimates | Exact scenario/change/component/input/liquidity IDs, rate/unit/conversion/quantity/participation/amount/quality/fallback/timing/actual clocks; semantic replay. |
| AA | total cost | Exact complete component IDs, compatible return fractions, exposure/delta and availability; nullable excluded totals retain reason. |
| AB | double-count protection | Provider included_components must exactly match spec covers; scenario category sets must be disjoint, including provider-embedded spread. |
| AC | sample evaluation | Exact path/change/source/truth/sample/origin/target/horizon/cost links, gross/cost/net state/reason and optional independent uncertainty attachment. |
| AD | aggregate evaluation | Exact included/excluded counts, arithmetic sums/means, all-truth gross, full/included turnover, cost per turnover and positive fractions; minimum support explicit. |
| AE | break-even total cost | Included gross budget; common per-side bps threshold = gross/(turnover/10000), with explicit support/nonnegative-budget/nonzero-denominator states. |
| AF | break-even spread | Selected spread threshold keeps other costs fixed; observed full PRICE spread includes exactly one half-spread multiplier; fixed-half units remain half-spread. |
| AG | break-even slippage | Selected fixed/provider slippage threshold in explicit input rate unit; other included costs held fixed. |
| AH | break-even impact | Linear/sqrt impact coefficient threshold when denominator identifiable and support adequate; fixed participation, explicit unavailable otherwise. |
| AI | cost sensitivity | Frozen supplied canonical Cartesian rate/participation/intensity grid ≤ 64 points; no automatic grid search or interpolation. |
| AJ | turnover sensitivity | Cost-intensity multiplier ≤ 10 scales transitions/participation while gross is held fixed; flat fees stay flat. This is not a newly realized exposure path or sizing optimizer. |
| AK | signal comparison | Exact matched sources/truth/cutoff/inclusion and identical policies; right−left descriptive gross/net/turnover differences, no winner or ranking mutation. |
| AL | event breakdown | Native AFRE-10 PIT event evidence, class/materiality/surprise-capable AFRE-17 membership rules; bounded demo uses earnings and event-by-regime compound. |
| AM | regime breakdown | Native hard and soft AFRE-11 regime memberships, explicit weights/effective support; no state/refit/selection changes. |
| AN | sector/universe breakdown | Exact native PIT sector/industry and historical universe evidence, original full-path changes and weighted arithmetic metrics. |
| AO | AFRE-17 environments | Native time, quality, neutral/market-state and compound environments; exact membership grids, minimum/effective support and immutable definitions. |
| AP | multi-horizon treatment | Actual independent 1h/1d targets and native forecast datasets assessed separately. Mismatched horizons yield INCOMPARABLE, no pooled cost outcome. |
| AQ | cost-to-gross ratio | Total included cost/abs(included gross sum); null at zero gross, no division by an invented denominator. |
| AR | edge-survival diagnostics | Fraction of included positive-gross rows retaining strictly positive net; null when no positive-gross support. Gross/net positive fractions also retained. |
| AS | participation sensitivity | Supplied rates within declared maximum; linear/sqrt diagnostics, out-of-bound intensity states unavailable. No capacity or executable-size claim. |
| AT | forecast/signal immutability | Cost/scenario/evaluation artifacts are separate; byte checks preserve native forecasts/residuals and all prior tables in non-TEST cost workflow. |
| AU | uncertainty integration | AFRE-15 exact forecast/sample/fold/target/horizon decomposition, one per sample, actual availability by cutoff; attachment does not alter cost. |
| AV | orthogonal-signal integration | AFRE-16 available residuals accepted with exact projection/target/fold/source and residual threshold units; no orthogonalization rewrite. |
| AW | TEST boundary | Frozen predeclared settings/grid before TRAIN cutoff; explicit native TestEvaluation seal. Later target correction cannot alter pinned scenario/path/cost bytes. Caller declaration cannot prove human blindness. |
| AX | target-free cost metadata | Feature-only guard blocks TargetVintage and later response artifacts before/after validation-cache fill; origin-time metadata additionally checks actual output availability. |
| AY | correction semantics | Append-only new revision IDs; later evidence must use ex-post timing or qualified historical evidence. Old results replay against old exact IDs, never latest queries. |
| AZ | audit | Bounded immutable audit answers sources/rules/units/side/fallback/availability/turnover/gross/cost/net/TEST and limitations; cohort/curve/break-even roots add their exact evidence. |
| BA | lineage | Unified native TRAIN/source/input/cost/truth/PIT environment/uncertainty/TEST graph; node/depth/byte/cycle limits and completed native-fit evidence. |
| BB | persistence/migration | Three immutable cost tables plus exact reference projections; migration success/rollback/future20 rejection and old DDL/metadata/row preservation tested. |
| BC | indexes/performance | Seven indexes cover scenario/source, component/provider, security/origin, target/horizon, timing/cutoff/TEST, change and reverse links. Offline profile separates workflow from arithmetic load. |
| BD | deterministic replay | Fresh native builds across seeds 0/1/42/random and normal/reversed components/samples/scenarios/requests; canonical restart digest equality (all eight fresh builds passed). |
| BE | concurrency | Real second SQLite writer appends cost/forecast/target corrections during pinned reads; path/totals/evaluation bytes unchanged, corrected refs require new scenario identity. |
| BF | numerical correctness | Independent half-spread, fee, bps, linear/sqrt, turnover, initial exposure, gross/net, algebraic thresholds and sensitivity/intensity oracles; bounded profile reports max error. |
| BG | security | Canonical structured data only; no eval/exec/pickle/joblib/shell/network/dynamic executable imports/provider paths in costs. Full suite socket/DNS blocked. |
| BH | documentation | Eight new focused guides, README/master and native integration docs updated; historical completion reports untouched, roadmap remains 26 distinct phases 0..25. |
| BI | tests added | 130 new cost tests, all passing in the full suite, including the eight-build fresh seed/order/restart matrix. The focused run excluding that matrix passed 129 tests in 187.45s. All earlier assertions are preserved. |
| BJ | full pytest | PASS: 2,492 tests in 4,601.13s (1:16:41), including all 2,362 earlier tests and 130 new cost tests, against the frozen 617-file Python/config tree. |
| BK | coverage | PASS: combined 98.645787%, statement 99.250311%, branch 95.773348%; branch-enabled full suite with socket/DNS blocked before collection and throughout execution. |
| BL | Ruff | PASS: full lint; format check reports 775 files already formatted. |
| BM | mypy | PASS: strict mypy, no issues in 616 source files. |
| BN | diff review | PASS: tracked/untracked changes reviewed; 617 frozen Python/config hashes match, 574 prior Python files and 18 prior reports unchanged, HEAD unchanged, index empty and git diff --check clean. |
| BO | secret/TODO scan | PASS: scripted scan of 790 deliverables for secrets, unfinished work and whitespace. |
| BP | benchmark/profile | Bounded native 24 sample evaluations, two scenarios, five components, 11 cohorts and 19 grid points; clocks/storage/restart/audit and numerical error recorded in costs-profile.json. No SLA. |
| BQ | dependencies | Zero runtime dependencies; standard library and unchanged native AFRE contracts/primitives only. |
| BR | remaining limitations | Simple-return targets only; borrow/rank bucket/FX/terminal liquidation/inferred liquidity fallback unsupported. Caller-attested provenance/predeclaration, model-dependent participation, arithmetic cost-intensity rather than executable fill path; no significance/profitability/causal/capacity proof. |
| BS | exact AFRE-19 scope | AFRE-19 deferred: multiple-hypothesis/FDR/FWER controls, repeated research trials, selection bias, appropriate deflated statistics and trial registry; explicit no-causal-proof, no broad model selection (AFRE-20). Stop after 18, no commit/push. |

## Required 50 quality gates

| Gate | Requirement | Result |
| --- | --- | --- |
| 1 | focused AFRE-18 tests | PASS |
| 2 | full pytest | PASS |
| 3 | branch-enabled coverage >=95% | PASS |
| 4 | socket/DNS blocked full suite | PASS |
| 5 | Ruff lint | PASS |
| 6 | Ruff format | PASS |
| 7 | strict mypy | PASS |
| 8 | git diff --check | PASS |
| 9 | full status/diff review | PASS |
| 10 | secret scan | PASS |
| 11 | TODO/FIXME scan | PASS |
| 12 | migration success/rollback/future-schema | PASS |
| 13 | corruption | PASS |
| 14 | bounds | PASS |
| 15 | hash-seed determinism | PASS |
| 16 | insertion-order determinism | PASS |
| 17 | restart replay | PASS |
| 18 | concurrency | PASS |
| 19 | fixed spread fixture | PASS |
| 20 | fee fixture | PASS |
| 21 | fixed slippage | PASS |
| 22 | impact fixture | PASS |
| 23 | participation bounds | PASS |
| 24 | missing cost semantics | PASS |
| 25 | no zero-cost default | PASS |
| 26 | double-count prevention | PASS |
| 27 | turnover fixture | PASS |
| 28 | initial exposure semantics | PASS |
| 29 | gross contribution | PASS |
| 30 | net contribution | PASS |
| 31 | break-even total cost | PASS |
| 32 | break-even spread/slippage | PASS |
| 33 | cost sensitivity | PASS |
| 34 | historical-causal availability | PASS |
| 35 | ex-post labeling | PASS |
| 36 | target-free pre-evaluation metadata | PASS |
| 37 | held-out scenario isolation | PASS |
| 38 | TEST boundary | PASS |
| 39 | event/regime/sector/universe breakdowns | PASS |
| 40 | AFRE-17 environment integration | PASS |
| 41 | actual 1h/1d identity | PASS |
| 42 | AFRE-16 residual source | PASS |
| 43 | AFRE-15 uncertainty attachment | PASS |
| 44 | neutral external cost inputs | PASS |
| 45 | no-direct external-engine regressions | PASS |
| 46 | corrected cost revision identity | PASS |
| 47 | docs consistency | PASS |
| 48 | 40-step demo | PASS |
| 49 | benchmark/profile | PASS |
| 50 | dependency check | PASS |

## Validation evidence

- Full pytest: **2,492 passed in 4,601.13s (1:16:41)**, exit status 0; no failures or skips.
- Coverage: **98.64578653488223% combined**, **99.25031075201989% statement**,
  **95.77334809892949% branch**. Covered 25,551/25,744 statements and 5,189/5,418 branches
  across all 361 `afre` source files. The configured 95% combined gate passed.
- The same full run enforced branch coverage and blocked all seven socket/DNS surfaces
  before pytest import/collection. The autouse fixture maintained blocking during each test;
  fresh replay subprocesses also blocked the same seven surfaces. The surfaces were `socket`, `create_connection`, `getaddrinfo`,
  `gethostbyname`, `gethostbyname_ex`, `gethostbyaddr` and `socketpair`.
- Focused final cost run: **129 passed in 187.45s**, excluding the fresh replay matrix.
  All 130 cost tests, including the eight-build matrix, passed again in the full run.
- Fresh replay: seeds 0/1/42/random × normal/reversed components, samples, scenarios and
  requests; all eight builds and restart reads yielded the same 935-artifact canonical digest
  recorded below. The 40-step demo passed in every build.
- Measured bounded profile: 24 native sample evaluations across two scenarios, five
  components per sample, 11 cohorts, 19 grid points, 632 audit nodes and 310 cost artifacts.
  Canonical payloads occupied 527,365 bytes; measured SQLite size was 28,794,880 bytes.
  Maximum numerical error was **4.440892098500626e-16**, below the asserted 1e-12 tolerance.
  Native timings and the separate 32 × 2,000 arithmetic loop are in `costs-profile.json`.
- Ruff lint passed; format check reported **775 files already formatted**. Strict mypy
  passed with **no issues in 616 source files**.
- Documentation consistency passed for **159 documents**, including exact 26-phase
  roadmap names, versions, links, historical reports, all 71 A–BS items and all 50 gates.
  The repository scan passed for **790 deliverables**: secrets, unfinished work and whitespace.
  `git diff --check` passed.
- Complete tracked and new-file changes were reviewed. All **617 Python/config files**
  match the final frozen manifest. **574 earlier Python files** retain their original hashes;
  the only two modified prior Python files are the version constants and documentation checker.
  All **18 earlier completion reports** are unchanged. Runtime dependencies remain empty.
- Git status: **`main...origin/main`**, **16 tracked files modified**, **50 new files**,
  all unstaged. The index is empty and HEAD remains
  `b11e3d86d50d152ee58998c39ef9b333c0c843b5`. No commit or push was made.
- AFRE-19 remains unimplemented. Its exact deferred scope is in item BS. Work stops
  after AFRE-18; the roadmap retains 26 distinct phases, AFRE-0 through AFRE-25.

See [research semantics](transaction-cost-aware-research.md), [cost scenarios](cost-scenarios.md),
[exposure](research-exposure-rules.md), [cost units](spread-fee-slippage.md),
[impact](market-impact-research.md), [turnover](turnover-diagnostics.md),
[break-even](break-even-cost.md), [sensitivity](cost-sensitivity.md) and
[the bounded measured profile](costs-profile.json).

**Stop after AFRE-18.** AFRE-19 remains unimplemented. Portfolio construction, risk
optimization and execution are downstream. No profitability, capacity or live-fill claim.
No commit or push.

## Files changed

16 tracked files modified; 50 new files. The 574 unchanged earlier Python
files retain their baseline hashes; the only modified prior Python files are the version
constants and documentation checker.
Earlier completion reports are unchanged.

- `README.md`
- `benchmarks/costs_profile.py`
- `docs/AFRE_18_COMPLETION_REPORT.md`
- `docs/AFRE_MASTER_SPEC.md`
- `docs/break-even-cost.md`
- `docs/cost-scenarios.md`
- `docs/cost-sensitivity.md`
- `docs/costs-profile.json`
- `docs/cross-sectional-ranking.md`
- `docs/event-conditioned-forecasting.md`
- `docs/forecast-uncertainty-decomposition.md`
- `docs/invariance-stability-research.md`
- `docs/market-impact-research.md`
- `docs/mixture-of-experts.md`
- `docs/nonlinear-feature-interactions.md`
- `docs/regime-conditioned-forecasting.md`
- `docs/research-exposure-rules.md`
- `docs/research-reproducibility.md`
- `docs/signal-orthogonalization.md`
- `docs/spread-fee-slippage.md`
- `docs/stability-evaluation.md`
- `docs/temporal-sequence-models.md`
- `docs/transaction-cost-aware-research.md`
- `docs/turnover-diagnostics.md`
- `examples/costs_demo.py`
- `examples/costs_fixture.py`
- `examples/costs_replay.py`
- `examples/costs_workflow.py`
- `pyproject.toml`
- `scripts/check_documentation.py`
- `src/afre/costs/__init__.py`
- `src/afre/costs/artifacts.py`
- `src/afre/costs/breakeven.py`
- `src/afre/costs/cohorts.py`
- `src/afre/costs/comparisons.py`
- `src/afre/costs/components.py`
- `src/afre/costs/cost_inputs.py`
- `src/afre/costs/definitions.py`
- `src/afre/costs/engine.py`
- `src/afre/costs/evaluation.py`
- `src/afre/costs/exposures.py`
- `src/afre/costs/fees.py`
- `src/afre/costs/impact.py`
- `src/afre/costs/lineage.py`
- `src/afre/costs/repository.py`
- `src/afre/costs/schema.py`
- `src/afre/costs/sensitivity.py`
- `src/afre/costs/sources.py`
- `src/afre/costs/spread.py`
- `src/afre/costs/storage.py`
- `src/afre/costs/totals.py`
- `src/afre/costs/turnover.py`
- `src/afre/costs/validation.py`
- `src/afre/version.py`
- `tests/costs/__init__.py`
- `tests/costs/conftest.py`
- `tests/costs/helpers.py`
- `tests/costs/test_availability.py`
- `tests/costs/test_boundaries.py`
- `tests/costs/test_concurrency.py`
- `tests/costs/test_evaluation.py`
- `tests/costs/test_integration.py`
- `tests/costs/test_limits.py`
- `tests/costs/test_numeric.py`
- `tests/costs/test_replay.py`
- `tests/costs/test_repository.py`

Fresh replay compares 935 canonical cost artifacts per build. All eight combinations
(seeds 0/1/42/random × normal/reversed insertion) have SHA-256 digest
`badd988c4ecfd85470eb26b90123ec2f7895d4aad8b16d2412f39249c7482a13`.
The checked 40-step demo and bounded profile passed; maximum reported numerical error
is 4.440892098500626e-16.

# AFRE-2 completion report — Forecast Targets & Label Construction

Completed 2026-10-04 in the working tree. Base: `main` at
`0fbb416 Add point-in-time feature store`. No commit, staging or push performed.
The frozen roadmap remains **26 distinct phases, AFRE-0 through AFRE-25**.
AFRE-0/1 source contracts, validation/serialization/hash logic, providers, persistence
and all original tests are byte-identical to the starting baseline. Only shared
version constants change in existing source. The old AFRE-1 demo dataset explicitly
pins engine 0.2.0, preserving its prior materialization hash and existing assertions.

| Item | Area | Delivered behavior and evidence |
| --- | --- | --- |
| A | Architecture | Dedicated target truth layer with immutable contracts, deterministic construction, isolated target persistence, indexed training queries and deep replay. No forecast-time feature conversion. |
| B | Package structure | `src/afre/target_engine/`: schema, definitions, windows, market_data, corporate_actions, residuals, quality, models, builders, repository, validation, engine and public exports. The original `targets.py` is unchanged. |
| C | Target schema | Independent target schema 1.0, closed target classes/enums, distinct `target_` hash domains and existing canonical JSON rules. Foundation and feature-store schemas remain 1.0. |
| D | Engine/store versions | Engine/project 0.3.0; additive SQLite store 1.2/user_version=3. Historical foundation/feature metadata remains unchanged; explicit target extension metadata identifies the new store. |
| E | Target definitions | Semantic target namespace/name/version, target type, typed horizon, origin/endpoint policy/tolerance, close field, calendar/bar stream, session policy, source datasets, action policy, benchmark/path estimator and builder version are immutable identity. Unsupported parameters/builders fail closed. |
| F | Target types | Implemented simple/log/residual/absolute/downside returns, realized volatility and signed adverse/favorable close excursions. Dimensionless returns; no profitability/trade-direction interpretation. |
| G | Horizon/window semantics | Nominal elapsed interval (T,T+H]; supplied exact session closes or eligible completed stream observations resolve other horizons. UTC integer nanoseconds, explicit calendars/streams, no nearest-bar or N×24h inference. |
| H | Origin price selection | Default exact completed close at T; separately fingerprinted bounded last-at/before or first-strictly-after policies. Foundation TargetSpec first-after-T remains unchanged and has no implicit cast. |
| I | Endpoint selection | Exact close, bounded last-at/before or first-at/after, explicit tolerances and typed deviation flags. Actual selected endpoints stay pinned; nonpositive actual price intervals fail rather than fabricate outcomes. |
| J | Target completion | Window must end, required observations/dependencies must be available and physically processed. PRESENT completion is at least nominal/actual endpoint and every required input availability/processing clock. Absent rows do not claim a completed label. |
| K | Label availability | Six source/output clocks preserve publication, source availability, actual receipt/ingestion/computation and final availability. Late endpoint/benchmark/actions constrain labels; final ≥ completion. No publication-only or reconstructed-target backdating. |
| L | Market-data vintages | Target-only raw completed bars pin stable instrument, period, OPEN/CLOSE/END_EXCLUSIVE convention, session/grid, source dataset/build, price/state/quality, six clocks and compatible predecessor. Source builds pin every admitted exact vintage. |
| M | Target revisions | Correction creates a new source build, vintage and target dataset identity. Old materializations/rows remain immutable and byte-identical; training queries can select an exact frozen dataset instead of a silent global latest version. |
| N | Target states | PRESENT requires finite output and complete evidence. MISSING, NOT_APPLICABLE, NOT_AVAILABLE_YET, INVALID and UNKNOWN remain typed states. Missing/delisted/halted/zero endpoints preserve grid cells; no zero imputation or invented terminal loss. STALE is rejected as a target state. |
| O | Target quality | Independent source quality, exact/tolerated selection flags, missing/halt/delist/nonpositive evidence, path counts/coverage, source revision, reconstruction and unverified-source flags. Partial/unverified outcomes cannot train. |
| P | Corporate actions | RAW, split-only and explicit positive price-factor streams remain separate. Origin-share split adjustment is effective-time and stable-security scoped, with exact action coverage/vintages/knowledge. TOTAL_RETURN/dividend reinvestment explicitly rejects as contract-only. |
| Q | Residual benchmarks | Supplied neutral benchmark subtraction, exact nominal window and actual price-endpoint alignment, stable benchmark/dataset/version, immutable vintages, own delivery/completion clocks; no factor fitting. |
| R | Realized-volatility targets | sqrt(sum squared consecutive sampled close log returns), explicit interval/minimum count/coverage, no mean subtraction, optional explicit positive variance annualization multiplier. Missing intervals break return chains. |
| S | MAE/MFE | Signed min/max sampled adjusted close/P0−1 including zero. Uses future closes, not intrabar extrema or trading recommendations; deterministic paths and adjustment provenance are pinned. |
| T | Path completeness | Exact sampled grid, exact origin/endpoint, ordered source evidence, fail-missing default. Explicit minimum-coverage research outcome is flagged partial and training-ineligible. Origin sampling phase and source interval compatibility are checked. |
| U | Sessions/calendars | Supplied versioned nonoverlapping UTC sessions, explicit regular/extended policy, holidays/weekends/short sessions respected. Session count means N closes strictly after T; bar count means N declared completed observations after T. |
| V | Overlapping intervals | Every resolved row records full origin and nominal interval plus selected source endpoints/completion/availability. Interval indexes retain overlap evidence for later AFRE-4 purge/embargo; no splitting is implemented. |
| W | Training-cutoff eligibility | Pure helper and indexed API require PRESENT/VERIFIED, complete nonpartial value, origin before cutoff and endpoint/completion/availability ≤ cutoff. Equality eligible; completed-but-undelivered and later reconstructed labels excluded. |
| X | Target sets | Exact sorted immutable definition fingerprints, duplicate/conflicting name-version rejection, independent set identity. Changes to horizon/policy/actions/benchmark/estimator/implementation change content identity. |
| Y | Target dataset manifests | Exact origin × definition grid including absent outcomes, supplied historical universe, source build (calendar/actions/benchmarks), frozen row IDs, source cutoff, physical construction, builder and engine versions. Atomic bounded batch materialization. |
| Z | Feature/target separation | Unchanged AFRE-1 target-provenance exclusions, closed feature storage families, DAG feature types and normalization vintage types reject target injection. All earlier transitive leakage regressions remain green. |
| AA | Target audit/lineage | Immutable audit answers definition/origin/window, actual prices/path, source revisions/actions/benchmark, clocks/quality/reason. Bounded depth/nodes/bytes and cycles fail closed; deep store audit recalculates exact labels and evidence. |
| AB | Persistence/migration | Additive 2→3 transactional migration and direct foundation upgrade preserve prior rows/metadata bytes. Immutable artifact/index/membership triggers, validated idempotence, rollback, strict layouts and future-version rejection tested. |
| AC | Indexed query APIs | Freeze/build/rows/known-by/audit APIs; SQL indexes cover source cutoff, build/security/bar time, definition/availability, full origin identity, intervals, source/benchmark and frozen dataset/set. All query/materialization/serialized/path/lineage bounds fail explicitly. |
| AD | Deterministic replay | Hash seeds 0/1/42/random, reverse source insertion order, restart, future correction and concurrent writer tests preserve canonical bytes for the same pinned inputs. Demo and profile also verify restart replay. |
| AE | Security | Stdlib only; closed data contracts/JSON, finite scalars and bounded decode. No executable provider data, dynamic provider imports, networking, shell, source-selected paths, eval/exec/pickle in the package. Store path chosen by caller. |
| AF | Documentation | Five required target documents plus benchmark/report; README, master, temporal, reproducibility, feature/target contracts and feature-store handoff updated. Exact advanced 26-phase roadmap and AFRE-3 deferred boundary checked. |
| AG | Tests added | 65 target cases across builders, calendars, contracts, queries and repository integrity. All 219 baseline cases unchanged. Includes required math, latency, split/unsupported dividends, residual/path, holiday/short session/ticker reuse, bounds and isolation. |
| AH | Full pytest | 284 tests passed. Every test blocks sockets/DNS; subprocess target determinism also explicitly blocks socket/DNS APIs. Focused target suite: 65 passed. |
| AI | Coverage | Branch-enabled combined coverage **98.94%**; statements **99.44%** (3,219/3,237), branches **96.68%** (698/722). All exceed the 95% gate; no old assertions or leakage guards weakened. |
| AJ | Ruff | `ruff check .` and `ruff format --check .` pass for the complete repository. |
| AK | mypy | Strict mypy passes source, examples, benchmarks, tests and scripts; runtime remains Python 3.11+. |
| AL | Diff review | Reviewed existing tracked diff and all new package/test/example/document/profile files. Baseline byte-hash comparison finds only existing source `version.py` changed; original tests/contracts/migrations are untouched. `git diff --check` passes. |
| AM | Secret/TODO scan | Existing repository script scans tracked and untracked deliverables for secret patterns, unfinished-work markers, whitespace and executable package boundaries; passes. Documentation checker validates exact phase list, versions, links and A–AQ coverage. |
| AN | Benchmark/profile | 20,000 observations, 12,000 labels, 20 securities, 4,000 origins, two horizons and three target types including path evidence. Construction/persistence, 600-row cutoff retrieval, lineage, deep validation, storage and restart measured; indexed query plan and canonical replay verified. See profile document for local numbers; no SLA. |
| AO | Dependencies | Zero runtime dependencies; no NumPy/pandas/Polars/Arrow/sklearn/ML frameworks. Existing pinned development tooling retained. |
| AP | Remaining limitations | Close-only prices/excursions; supplied calendars/raw bars/actions/benchmark returns; no dividends/total-return/FX/tax semantics, benchmark fitting, live connectors or inferred missing outcomes. Qualified historical sources preserve physical reconstruction; historical target-computation backdating is unsupported. Authentication/attestor truth requires provider audit. Bounded workloads require explicit partitioning; no production SLA. |
| AQ | Exact AFRE-3 scope | Only Point-in-Time Universe & Security Eligibility: historical membership/security master, listing intervals, ticker/name changes, delistings/corporate lifecycle, index/ETF constituent vintages, liquidity/price/tradability/exchange-session rules, stable identity, knowledge-time membership and survivorship prevention. Deferred; no AFRE-3 ingestion implemented. |

Validation commands:

```sh
.venv311/bin/pytest tests/target_engine -q
.venv311/bin/pytest -q --cov=afre --cov-branch --cov-report=term-missing
.venv311/bin/ruff check .
.venv311/bin/ruff format --check .
.venv311/bin/mypy --strict
.venv311/bin/python scripts/check_repository.py
.venv311/bin/python scripts/check_documentation.py
.venv311/bin/python -m examples.foundation_demo
.venv311/bin/python -m examples.feature_store_demo
.venv311/bin/python -m examples.target_demo
.venv311/bin/python -m benchmarks.targets
git diff --check
git status --short --branch
```

Final full suite: **284 passed in 10.12 seconds**, including all 219 unchanged
baseline cases and 65 target cases. Focused suite: **65 passed in 1.88 seconds**.
Ruff lint clean; **100 files formatted**; strict mypy clean across **78 source files**.
Repository scan: **103 deliverables** clean. Documentation consistency:
**22 documents**, exact 26-phase list, all local links/versions and both historical
A–AS/current A–AQ reports validated. All three offline examples pass. Target profile
passes with **32,011 validated artifacts**, exact restart bytes and indexed retrieval.
Combined coverage is **98.94%** with branch instrumentation enabled.
Demo dataset:
`afre.target_dataset:1.0:1765c546e8e30022bc904eefe6fe08342278b7dee026391528139c4e306ec697`.

Coverage and profile measurements are recorded from the final validation runs.
See [offline profile](target-benchmark.md) for exact workload and timing boundaries.

Changed deliverables: new target package, five target test modules and package
fixtures, target demo/profile, five required target documents plus benchmark/report;
updated README/master/temporal/reproducibility/feature/target/feature-store documents,
documentation consistency checker, project/version constants and the old example's
explicit engine-0.2.0 fixture pin. All changes remain unstaged on `main` for review.
No AFRE-3, splitting, predictive fitting, calibration, portfolio, risk optimization
or execution work is included. No commit or push was made. **Stop after AFRE-2.**

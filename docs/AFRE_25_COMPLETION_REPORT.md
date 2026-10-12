# AFRE-25 completion report — final integration, hardening and research audit

Release decision: **RELEASE_CANDIDATE**. Engine 1.0.0 completes the audited research architecture. Service API and public schemas remain 1.0; store 1.24 / SQLite schema 25 remain unchanged. No production deployment or profitability claim is made.

Starting state was clean `main`, committed AFRE-24 at `16b20e42dbfa865677c1e873e0a65fd018691056`. Historical completion reports are unchanged. No commit, push or staging is performed.

The audit also corrected earlier-class frozen staging for selection and fusion trial registration on the final store; concrete layouts and configured bounds are preserved. No native model mathematics is changed.

The genuine compatibility defect was current-engine-only validation of snapshots, audits, catalogs and reply envelopes. The closed 0.25.0/1.0.0 public catalog and recorded-version replay fix preserve historical content. New 1.0.0 publications have a new identity. Immutable service_engine_version=0.25.0 remains creation provenance, not the current serving version.

| Item | Audit concern | Evidence / result |
| --- | --- | --- |
| A | architecture completion | All existing native phase modules retained; [final architecture](AFRE_FINAL_ARCHITECTURE.md). Recorded-version compatibility and native staging across later store layouts are hardened. |
| B | frozen 26-phase roadmap | 26 distinct phases, AFRE-0 through AFRE-25; master table checked against the exact 26 names. AFRE-24 remains the service boundary; no later phase. |
| C | engine version | ENGINE_VERSION and pyproject 1.0.0; source manifest pins exact package content. |
| D | service API version | AFRE_SERVICE_API_VERSION=1.0; methods, public fields and enum values retained. |
| E | all public schemas | All earlier and service/snapshot/registry public schemas remain 1.0; complete catalog in afre-release-manifest.json. |
| F | store/SQLite versions | Store 1.24 / SQLite user_version 25. No new persisted contract needs migration 26. Immutable creation metadata retained. |
| G | runtime dependencies | dependencies=[]; Python>=3.11; dev tools remain pinned and are not runtime dependencies. |
| H | public exports | afre.service.__all__ preserved exactly against committed baseline; manifest lists exports. Public-only consumer regression. |
| I | cross-phase integration | Actual service native fixtures cover AFRE-0–16 and21–24; bounded native selection/multiple-testing, invariance/cost and correction workflows supplement them. No mocked forecasts. |
| J | point-in-time evidence | tests/feature_store and tests/service/test_availability.py enforce exact vintage, receipt, approval and lineage clocks. |
| K | target correctness | tests/target_engine cover typed returns/volatility/extremes, exact endpoints, benchmark/action/path completion and (T,T+H]. |
| L | leakage-safe datasets | tests/research_datasets cover historical eligibility, purging/embargo, label completion and fold-local preprocessing. |
| M | TRAIN boundary | TRAIN-fitted state and preprocessing; native model audit proves corrected full TRAIN evidence separately from public target-free leaves. |
| N | VALIDATION boundary | Finite declared VALIDATION criterion and exact sample/truth support; no silent TEST substitution. |
| O | TEST boundary | Sealed post-selection TEST and before-cache service truth rejection; existing phase guard tests remain intact. |
| P | multiple testing | tests/multiple_testing cover complete opportunities/failures, Bonferroni/Holm/BH/BY, adaptivity and assumptions. |
| Q | model selection | Native finite selection on existing service fixture folds, complete registry and AFRE-19 trials; no automatic refit. |
| R | probabilistic correctness | Native Gaussian/actual empirical/finite mixture/quantile-only laws; GT/GE/LT/LE ties, proper scores, independent oracles; no fabricated density. |
| S | calibration | tests/calibration exercise all native methods, isolated fit reservations, corrections, diagnostics and TEST exclusion; assumptions documented. |
| T | multi-horizon | Actual 1h/1d native outputs, separate labels/fit/context and canonical public bundles. Existing horizon regressions cover calibration/ranking/uncertainty/health/challenge; no invented joint law. |
| U | event conditioning | Native event contexts preserve publication, receipt, expectation/actual, materiality, novelty, overlap and fallback evidence. |
| V | regime conditioning | Native FILTERED regime snapshots; tests reject hindsight/future evidence and incompatible memberships/quality. |
| W | expert mixtures | Native exact expert mixtures retain atom ties, law components, gates, contribution and explicit missing-source behavior. |
| X | nonlinear interactions | Native nonlinear interaction fixtures and tests cover masks, zeros, availability, TRAIN state and proper scoring. |
| Y | temporal sequences | Native sequence fixtures and tests cover causal histories, gaps/masks/zeros, TRAIN normalization and deterministic temporal dynamics. |
| Z | uncertainty decomposition | Native uncertainty context and tests retain component identifiability/unavailability, parameter covariance certificate and nonadditive limitations. |
| AA | orthogonalization | TRAIN-only projection/residual audit; orthogonal does not imply independent; no hidden pruning. |
| AB | invariance | Native invariance workflow and tests are descriptive stability research; no causal-proof or automatic-action claim. |
| AC | cost-aware research | Native cost scenarios retain exact side/round-trip/fee/slippage/impact/turnover and missing/zero assumptions; no executable portfolio. |
| AD | fusion | Native fixed/learned fusion tests and source correction preserve exact source sets, law mixtures, TRAIN weights, contribution and diversity. |
| AE | health monitoring | Descriptive native health context/thresholds and truth-gated diagnostics; no automatic training/calibration. |
| AF | champion/challenger | Native exact-role common matched evaluation, predeclared criteria and MANUAL_ONLY advice; no active pointer. |
| AG | final snapshots | Exact source/producer/target/horizon/universe/clocks/context/lineage are part of immutable snapshot identity. |
| AH | public registry | Frozen explicit catalogs, exact registry IDs and query-pinned pagination; no hidden latest. |
| AI | public service | Actual public service version/capability/law/context/error/pagination/restart regression; read-only protocol does not train or deploy. |
| AJ | provider-neutral boundaries | StableSecurityId, UTCns, units, quality, six clocks and neutral SourceReference; no external engine dependency. |
| AK | external adapter | examples/downstream_client.py and tests/release/test_external_consumer.py use supported public imports only. |
| AL | time/availability audit | Live 10:00 publication/10:02 receipt excludes 10:01; adapter and existing PIT tests reject backdating. |
| AM | reconstruction audit | Unqualified later archive is not causal; qualified reconstruction pins attestation plus historical availability while retaining actual later receipt. |
| AN | public contract compatibility | Actual committed 0.25.0 golden snapshot/audit/catalog/reply bytes, original0.25.0 SQLite snapshot/audit replay under 1.0.0 (release-compatibility-evidence.json), and native recorded-engine semantic replay/reopen. Unknown engine/catalog combinations reject. |
| AO | numerical audit | Existing independent QR/rank/conditioning/ridge/covariance/score/calibration oracles plus final 8-sigma Gaussian-tail check; no silent pseudoinverse. |
| AP | correction/immutability audit | Actual feature→dataset→TRAIN model→point→fusion→snapshot correction creates new identities; old full native model audit and old public bytes survive. |
| AQ | migration-chain audit | All 25 actual repository constructors migrate0→25 with foundation rows from schema 1 and native feature/source/vintage rows from schema 2; priorDDL/metadata/rows compared. |
| AR | corruption audit | Legacy service tests detect payload/index/link/layout/metadata corruption and semantic forgery with a valid content hash. |
| AS | concurrency audit | Separate SQLite connections append feature/target/forecast/event/regime/trial/health/challenge/registry/snapshot evidence while frozen reader counts/bytes remain unchanged. |
| AT | deterministic replay | Fresh-process native correction chain under0/1/42/random and reversed inputs; legacy ordering/restart/frozen-snapshot regressions retained. |
| AU | research-trial accounting | Every native selection candidate produces a registered research opportunity/completion; failed/incompatible trials remain counted. |
| AV | TEST reuse | Immutable TEST seals, explicit recorded reuse/adaptivity, no fusion/selection/threshold/program tuning from TEST; statistical caveats remain. |
| AW | cost/impact assumptions | Cost/impact assumptions are scenario inputs, not execution truth, capacity or guaranteed profitability. |
| AX | security | Static forbidden import/executable-data scan plus closed decoder, malicious payload, corruption and socket/DNS-blocked suite. |
| AY | resource bounds | Existing bounds regressions cover payload/depth/nodes/atoms/components/contexts/pages/catalog/artifacts/backups and native operation budgets. |
| AZ | release manifest | Deterministic afre-release-manifest.json; source digest excludes mutable generated docs/reports/manifest to avoid cycles. |
| BA | version consistency | Current engine/API/schema/store declarations, public catalog, manifest and active docs checked; historical reports/goldens/creation metadata retain original versions. |
| BB | documentation | Ten final audit documents plus active README/master/service/reproducibility docs; historical completion reports preserved. |
| BC | tests added | New tests/release: compatibility, consumer, native corrections, all-stage migrations, fresh-process determinism, security/numerical boundaries and multilayer concurrency. 34 new release tests evidence recorded below. |
| BD | final full pytest | PASS: 3,288 passed; 0 failures, 0 errors, 0 skips. Pytest 11,974.22s; JUnit 11,974.087s; wrapper 11,974.530869917013s; exit 0. All 3,254 earlier tests plus 34 AFRE-25 release tests passed in one frozen offline invocation. |
| BE | combined coverage | PASS: 40,720/41,409 combined statements and branch destinations = 98.33611050737763%; minimum 95%. |
| BF | statement coverage | 33,791/34,141 statements = 98.97483963562871%; 350 missing; 468 excluded lines under the unchanged coverage configuration. |
| BG | branch coverage | PASS: branch coverage enabled; 6,929/7,268 branch destinations = 95.33571821684095%; 339 missing, 293 partial; minimum 95%. |
| BH | Ruff | PASS: Ruff lint and formatting checks completed before the freeze; unchanged frozen files preserve those results. No redundant rerun. |
| BI | strict mypy | PASS: strict mypy, 871 source files. |
| BJ | network isolation | PASS: socket/DNS denial installed before AFRE imports. Fresh socket/DNS subprocess probes passed; guard propagated even when child environments were replaced. Complete guarded suite passed. |
| BK | migration gates | New nonempty migration chain/rollback/future regressions plus existing migration/storage tests in the single final full gate. |
| BL | source freeze | 877 source/test/configuration/compatibility-fixture files frozen; HEAD 16b20e42 unchanged; freeze SHA256 c8dfd59d165c3833e4aa484c8994e958da65a1c89aad7216698c419e2637366a. PASS: full wrapper checked the exact inventory and HEAD before and after; resume verification independently matched all 877 files and the saved freeze hash. |
| BM | diff review | Complete tracked/untracked source/test/docs review; git diff --check passed. Public exports/schema identifiers and DDL unchanged; no tests weakened or exclusions added. |
| BN | secret scan | PASS: pre-freeze repository/security scan. Final scan covers 1136 tracked/untracked deliverables, including saved validation evidence; no secrets, unfinished markers, forbidden runtime imports or whitespace errors. |
| BO | unfinished-work scan | Same repository scan checks all tracked/untracked deliverables for unfinished markers; no exclusions added. |
| BP | final demonstration | PASS: 85 actual native/public checks in the successful measured demo; detailed checks in release-demo-evidence.json. |
| BQ | measured profile | PASS: 15 measured native categories, 536.2180835420731s instrumented offline run. Explicit fixture/solver/validation/persistence/audit stages and profiling rules in release-profile.json / AFRE_PERFORMANCE_AUDIT.md; no SLA. |
| BR | known limitations | Bounded synthetic offline research evidence, qualified-source trust, exchangeability/nonstationarity/selection caveats, no joint-law or hardware-bit guarantee, no production SLA. [Formal research audit](AFRE_RESEARCH_AUDIT.md). |
| BS | release status | RELEASE_CANDIDATE: all critical frozen full, branch, compatibility, migration, corruption, concurrency, deterministic replay, consumer, static and offline gates passed. Research release only. |
| BT | handoff | [Public contract handoff](AFRE_INTEGRATION_HANDOFF.md); downstream owns portfolio/risk/execution. No real external integration. |
| BU | Git state | main at 16b20e42dbfa865677c1e873e0a65fd018691056; 84 changed files (37 modified, 47 untracked), all unstaged. No commit or push; release-candidate changes remain in the working tree. |
| BV | release conclusion | AFRE-25 and the distinct AFRE-0 through AFRE-25 / 26-phase architecture are complete as a tested research release candidate. No further phase is introduced. Stop with uncommitted working-tree changes. |

## Exact validation evidence

The 877 source, test and configuration files were frozen after focused integration and static gates. The single socket/DNS-blocked full pytest invocation passed all 3,288 tests, with branch coverage enabled and both coverage thresholds satisfied. The wrapper verified the identical inventory and HEAD before and after; resume verification confirmed the same hashes. Only documentation, manifest status and saved validation artifacts were finalized after that run. No successful test or static source gate was repeated.

Focused covered gate: 123 passed, 0 failures, 871.15s. Service coverage: 1252/1258 statements (99.52305246422894%), 226/232 branches (97.41379310344827%), 1478/1490 combined (99.19463087248322%). This is focused service coverage, not a repository-wide coverage claim.

Original committed 0.25.0 SQLite snapshot/audit replay is recorded in [compatibility evidence](release-compatibility-evidence.json). Actual package exports, public enums/schema identifiers, storage DDL/metadata, all 25 historical completion reports and HEAD were compared to the starting state and preserved.

[Exact validation evidence](release-validation-evidence.json) records counts, exact coverage totals, environment, the unchanged HEAD and 877-file freeze, per-family test counts, network guards, artifact hashes, earlier static results and the Git change inventory. Durable copies include [full log](release-validation/full.log), [JUnit](release-validation/full-junit.xml), [coverage JSON](release-validation/full-coverage.json), [wrapper result](release-validation/full-result.json), [offline runner](release-validation/offline-runner.txt), [child guard](release-validation/offline-guard.txt), [focused log](release-validation/focused-final.log) and [strict mypy output](release-validation/strict-mypy.log). Original temporary artifact paths and SHA256 hashes are retained; copies add only a final newline where necessary. Local timing/page-size diagnostics are not semantic identity.

## Limits and release interpretation

The full native TRAIN lineage audit is separate from public snapshot lineage, which retains frozen fitted artifacts as leaves and does not reopen response truth. The migration-chain regression carries real nonempty foundation/feature rows across all schemas; independent per-phase tests cover each native family, rollback and corruption. The profile measures actual bounded workflows and reports cumulative versus exclusive-time rules; categories can overlap and do not imply isolated throughput.

No forecasting engine guarantees trading profitability. No new persisted contract, model family, runtime dependency, external engine import, active pointer, automatic training/calibration/promotion, risk optimizer, portfolio or execution is added. Optional enhancements are post-1.0 considerations, not another roadmap phase.

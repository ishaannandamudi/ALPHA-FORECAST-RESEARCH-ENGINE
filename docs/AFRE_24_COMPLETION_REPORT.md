# AFRE-24 completion report — Forecast Snapshot, Registry & Service

AFRE-24 is implemented and validated in the working tree. All 50 quality gates pass. The final frozen, branch-enabled, socket/DNS-blocked full run passed 3,254 tests in 11,204.83 seconds (3:06:44), with zero failures, errors or skips. Coverage is 98.335306% combined, 98.974479% statement and 95.330579% branch. All 857 frozen file hashes and HEAD matched before and after. No commit or push. The frozen roadmap remains 26 distinct phases, AFRE-0 through AFRE-25; AFRE-25 remains deferred.

| Item | Topic | Implementation / evidence |
| --- | --- | --- |
| A | architecture | Separate native adapters, immutable publisher, additive repository and read-only provider protocol. |
| B | package structure | 22 focused modules under `src/afre/service`; public exports in `afre.service`. |
| C | schema | Forecast service schema 1.0; earlier public schemas unchanged. |
| D | engine/store versions | Engine 0.25.0, store 1.24, SQLite25; additive migration from SQLite24. |
| E | public API version | AFRE_SERVICE_API_VERSION=1.0, separate from implementation/store versions. |
| F | snapshot schema version | FORECAST_SNAPSHOT_SCHEMA_VERSION=1.0. |
| G | registry schema version | REGISTRY_SCHEMA_VERSION=1.0. |
| H | ForecastSnapshot | Exact native source, producer, models, security/origin/target/horizon, universe, output, context, registry and lineage. |
| I | snapshot identity | All semantic fields, requested context, publication version/time and versions contribute to domain-separated identity. |
| J | snapshot publication | Separate SnapshotPublisher validates, persists and indexes append-only; no source mutation. |
| K | final availability | Maximum of native output and all used forecast-time context; never later than origin cutoff. |
| L | publication time | Publication clock is separate from causal availability and bounds historical metadata receipt. |
| M | forecast output contract | Stable ForecastOutput with optional scalar/law/marginals/interval and exact units/IDs. |
| N | point output | Exact native target/horizon point value and availability; no allocation semantics. |
| O | probabilistic output | Gaussian location/scale, bounded actual empirical atoms, exact weighted component mixtures. |
| P | Gaussian-mixture preservation | Native AFRE12/21 mixtures stay finite mixtures; no Gaussian collapse. |
| Q | quantile-only output | Sparse quantile sets remain quantile-only; no invented CDF/tails. |
| R | threshold probabilities | GT/GE/LT/LE preserve empirical atom ties; quantile-only threshold queries are unavailable. |
| S | calibration metadata | Exact state/method/artifact/version/fit cutoff/availability and full-law preservation flag; no refit. |
| T | multi-horizon snapshot | Independent actual 1h/1d native snapshots; no pooling or horizon synthesis. |
| U | horizon ordering | Canonical horizon-fingerprint ordering independent of request order. |
| V | partial bundle | COMPLETE/PARTIAL/UNAVAILABLE with an exact requested/missing horizon grid. |
| W | ranking output | Exact security score/rank/percentile/group/universe/tie policy and native artifact. |
| X | portfolio-boundary treatment | Ranks and predictive metrics are research outputs, not portfolio weights or profitability evidence. |
| Y | event context | Exact event IDs/classes/windows/materiality/novelty/surprise/timing clocks from native contracts. |
| Z | regime context | Exact taxonomy/version, scope and hard/soft membership; FILTERED only, rejecting smoothed/ex-post state. |
| AA | uncertainty context | Native decomposition values/statuses replay using frozen covariance certificates without reopening TRAIN responses. |
| AB | uncertainty statuses | Null unavailable components and native identifiability statuses retained; missing is never zero. |
| AC | orthogonal context | Exact residual/source/projection/spec metadata and target/horizon compatibility. |
| AD | fusion context | Exact fusion artifact/spec/sources/family/weights/effective contributors/missingness; no executable logic. |
| AE | health metadata | Exact compatible ModelHealthSnapshot, aggregate/metric statuses and cutoff/availability; NONE_DESCRIPTIVE_ONLY. |
| AF | health lookup semantics | Exact pinned context ID only; no silent latest-compatible lookup. |
| AG | champion/challenger metadata | Exact ChallengeProgram/champion/challengers/run/assessment statuses; MANUAL_ONLY. |
| AH | no-active-model-switch boundary | No active champion/deployment switch or mutation methods. |
| AI | registry | Immutable artifact/model metadata with explicit anchor source and compatibility. |
| AJ | registry entry types | Closed implemented categories MODEL, FORECAST_ARTIFACT, CALIBRATION, RANKING, EVENT_CONDITIONED, REGIME_CONDITIONED, MIXTURE, NONLINEAR, SEQUENCE, UNCERTAINTY, ORTHOGONALIZATION, FUSION, HEALTH_SNAPSHOT, CHALLENGE_PROGRAM, CHALLENGE_RUN, FORECAST_SNAPSHOT. |
| AK | registry append-only semantics | Canonical append-only records and immutable SQLite insert/update/delete triggers. |
| AL | registry status | AVAILABLE only; imported lifecycle transition support is not advertised. |
| AM | registry lookup | Exact entry ID and frozen artifact/producer/target/horizon queries. |
| AN | registry query ordering | Canonical registry-entry fingerprint ordering. |
| AO | public service façade | ForecastResearchService / AFREService implement ForecastServiceProvider. |
| AP | public methods | Exact snapshot/origin/bundle/registry/list/health/challenge/version/catalog/audit reads. |
| AQ | no-training boundary | No fit/train/select/recalibrate/promote/execute consumer methods. |
| AR | snapshot-by-ID | Exact ID retrieval verifies canonical/projection/link and native semantic replay. |
| AS | snapshot-for-origin | Exact frozen origin/producer/target/horizon/universe/as-of catalog query. |
| AT | SnapshotQuery/selector | Immutable SnapshotQuery with EXACT_ONE_V1 policy and API version. |
| AU | selector identity | Query is a canonical domain-separated fingerprinted contract. |
| AV | no-lookahead | Native source and used forecast-time contexts must be available by origin cutoff. |
| AW | target-free service | Mandatory guards run before get/resolve/get_any caches for TargetVintage and later outcomes. |
| AX | historical reconstruction | Existing qualified native delivery evidence only; provider publication never implies AFRE receipt. |
| AY | reconstruction label | RECORDED_CAUSAL / QUALIFIED_RECONSTRUCTED with exact qualified evidence and actual clocks retained. |
| AZ | context requests | Eight exact optional sections: ranking/event/regime/uncertainty/orthogonal/fusion/health/challenge. |
| BA | context identity policy | Snapshot identity includes every requested section; separate forecast output identity stays unchanged. |
| BB | snapshot profiles | Explicit exact context requests; no ambiguous presets or inferred latest metadata. |
| BC | bounds | Configured hard ceilings for artifacts, registry/page/horizon/context/event/atom/component/lineage/payload/read-snapshot resources. |
| BD | pagination | Deterministic keyset pages against an explicit PublicationCatalog. |
| BE | cursor semantics | RegistryCursor pins complete query fingerprint and last entry; changed filters/page size/catalog reject it. |
| BF | registry snapshot pagination | Catalog entry membership and as-of are immutable; concurrent appends do not reorder pages. |
| BG | VersionInfo | Engine/API/snapshot/registry/store/SQLite/Python/dependency/catalog identities are public. |
| BH | schema catalog | All current public schema constants exposed, excluding internal DDL and legacy store metadata. |
| BI | capability catalog | Fifteen implemented capabilities; snapshot-specific requested capability checks. |
| BJ | unsupported capabilities | Explicit UNAVAILABLE for unknown or absent requested capabilities. |
| BK | public errors | NOT_FOUND, INCOMPATIBLE, UNAVAILABLE, INSUFFICIENT_DATA, INVALID_REQUEST, VERSION_MISMATCH, BOUNDS_EXCEEDED, CORRUPT_ARTIFACT; sanitized messages. |
| BL | serialization | Existing closed canonical JSON, with service-only public roots and exact immutable typed payloads. |
| BM | time serialization | Integer UTC nanoseconds; no locale or timezone serialization ambiguity. |
| BN | float serialization | Existing finite-float canonical rules; NaN/infinity rejected. |
| BO | hashing | Existing domain-separated SHA-256 over canonical payloads. |
| BP | snapshot hash | Fingerprint reproduces after restart and correction preserves prior bytes. |
| BQ | ETag/content hash | Snapshot fingerprint is exposed as immutable etag. |
| BR | no-network-server boundary | In-process only; no HTTP framework or network daemon. |
| BS | provider protocol | Stable ForecastServiceProvider protocol, no consumer private DB/module dependency. |
| BT | downstream adapter boundary | Downstream adapters consume public contracts; no external HFT/AME/MCE/EIE/options/TCA engine import. |
| BU | snapshot publication contract | SnapshotPublication pins source, publication version/time and exact context requests. |
| BV | publish idempotence | Exact republish validates old bytes and is idempotent. |
| BW | publish correction | New native source or included context produces a new publication identity. |
| BX | snapshot-registry links | Separate deterministic snapshot registry entry avoids a circular hash; contributor entries are pinned. |
| BY | model-registry links | Exact contributing native model/artifact registrations bound to the publication anchor. |
| BZ | lineage | Source/models, target definitions, feature evidence, universe, calibration and context IDs; no future truth expansion. |
| CA | lineage bounds | Node/depth/byte/cycle limits checked before traversal; fitted TRAIN and historical evaluation certificates are bounded leaves. |
| CB | public audit | SnapshotAudit includes full snapshot, exact own registry entry, versions, lineage and explicit limitations/outcomes-read=false/action boundaries. |
| CC | snapshot replay | Canonical immutable snapshot replay after persistence/restart. |
| CD | registry replay | Exact registry bytes and frozen catalog pagination replay. |
| CE | service replay | Exact query/reply semantic bytes across restart and hash seeds. |
| CF | concurrency | One frozen SQLite read and validation scope per consumer request. |
| CG | snapshot isolation | Every constituent source/registry/context/audit read shares the same pinned snapshot. |
| CH | concurrent publication | Concurrent source/snapshot/registry append cannot affect open reads or frozen catalogs. |
| CI | correction isolation | Source/health/challenge corrections append IDs; old reads remain intact. |
| CJ | no-latest-pointer mutation | No latest/active pointer or deployment lifecycle state. |
| CK | persistence/migration | Additive SQLite24→25 with exact legacy preservation, rollback and future-version rejection. |
| CL | indexes/performance | Exact artifact/producer/target/horizon/origin/universe/availability indexes and immutable reference links. |
| CM | deterministic replay | Seeds 0/1/42/random, reversed sources/requests/contexts/registry/horizons and restart preserve canonical semantics. |
| CN | numerical correctness | Independent Gaussian/empirical/mixture/threshold fixtures; exact native output/context/rank values, version/catalog and ordering checks. |
| CO | security | No eval/exec/pickle/joblib/runtime shell/network/dynamic executable imports or provider-selected paths. |
| CP | documentation | Eight service documents, updated current roadmap references, public API boundaries and historical reports preserved. |
| CQ | tests added | 78 service tests cover native families/context, availability, bounds, semantic forgery, migration, replay/concurrency, public errors and independent oracles. All pass. |
| CR | full pytest | Final frozen full invocation: 3,254 passed; zero failures/errors/skips; pytest 11,204.83s (3:06:44), JUnit 11,204.696s. This same invocation measured branch coverage and enforced offline execution. |
| CS | coverage | 98.335306% combined (40,700/41,389); statements 98.974479% (33,779/34,129, 350 missing); branches 95.330579% (6,921/7,260, 339 missing, 293 partial). Branch measurement enabled. 468 excluded lines under unchanged coverage configuration; no exclusions added. Focused package: 99.191375% combined, 97.413793% branch. |
| CT | Ruff | Full Ruff lint passes; formatting passes for 1,068 files. |
| CU | mypy | Strict repository-wide mypy passes; final verification covers src/tests/examples/benchmarks/scripts. |
| CV | diff review | Reviewed all 64 files: 17 tracked modifications, 47 new files; nothing staged. Earlier source/tests are unchanged except required version constants; the example fixture ordering correction preserves original assertions. Final diff whitespace check passes. |
| CW | secret/TODO scan | Scripted secret/unfinished-work/whitespace scan passes for 1,089 deliverables. |
| CX | benchmark/profile | 77 asserted offline demo checks pass. service-profile.json contains all requested bounded measurements, with no SLA. Independent Gaussian maximum absolute error is 2.775558e-17; empirical/mixture atom-tie fixtures are exact. |
| CY | dependencies | Python3.11+, standard library only, zero runtime dependencies. |
| CZ | remaining limitations | In-process read-only façade; exact-ID health/challenge only, AVAILABLE registry lifecycle only, bounded finite laws/catalogs. TRAIN fit/covariance and historical evaluation certificates are not refit/rescored by service; native upstream audit remains separate. |
| DA | exact AFRE-25 scope | Final Integration, Hardening & Research Audit remains deferred: cross-phase integration/schema/provider/causality/reproducibility/migration/security/performance/API/docs audits, final repository gate and release candidate; no new research family unless correctness requires it. |

## Quality gates

| Gate | Check | Result |
| --- | --- | --- |
| 1 | focused AFRE-24 tests | PASS — 78 focused service tests; package coverage 99.191375% combined, 97.413793% branch. |
| 2 | full pytest | PASS — 3,254 passed; zero failures/errors/skips; 11,204.83s (3:06:44). |
| 3 | combined branch-enabled coverage >=95% | PASS — branch-enabled combined 98.335306%; statement 98.974479%; branch 95.330579%. |
| 4 | socket/DNS-blocked full suite | PASS — sockets/DNS denied before AFRE imports and in fresh Python children; the same completed full invocation. |
| 5 | Ruff lint | PASS — repository-wide Ruff lint. |
| 6 | Ruff format | PASS — 1,068 files already formatted. |
| 7 | strict mypy | PASS — strict mypy, 855 source files. |
| 8 | git diff --check | PASS — final git diff --check. |
| 9 | full status/diff review | PASS — all 64 changed/new files reviewed, unchanged earlier contracts/tests verified, nothing staged. |
| 10 | secret scan | PASS — scripted repository scan, 1,089 deliverables. |
| 11 | TODO/FIXME scan | PASS — scripted unfinished-work/TODO/FIXME scan. |
| 12 | migration success/rollback/future-schema | PASS — test_storage.py covers additive 24→25, rollback and future-version rejection. |
| 13 | corruption | PASS — test_storage.py and test_integrity.py reject byte/index/link/layout corruption and valid-hash semantic forgeries. |
| 14 | bounds | PASS — configured bounds and contract limits in test_boundaries.py and test_storage.py. |
| 15 | hash-seed determinism | PASS — seeds 0/1/42/random in test_replay.py and the offline demo. |
| 16 | insertion-order determinism | PASS — reversed publications, sources, requests, contexts, registry and horizons preserve canonical semantics. |
| 17 | restart replay | PASS — persisted/reopened snapshot, registry and service response replay. |
| 18 | concurrency | PASS — concurrent writer against a frozen reader in test_replay.py; frozen catalog pagination in test_requests.py. |
| 19 | exact snapshot identity | PASS — exact republish is idempotent; semantic corrections change identity while retaining old bytes. |
| 20 | point output | PASS — native point value/unit/artifact/version checks in test_workflow.py. |
| 21 | probabilistic output | PASS — Gaussian, empirical, calibrated, mixture and other native probabilistic families. |
| 22 | Gaussian mixture preservation | PASS — native mixtures retain component laws and weights; independent mixture oracle. |
| 23 | quantile-only handling | PASS — actual quantile-only native forecast; no invented complete law or threshold CDF. |
| 24 | calibration metadata | PASS — exact native calibration state/method/artifact/version/fit cutoff. |
| 25 | multi-horizon bundle | PASS — independent actual 1h/1d snapshots and canonical horizon ordering. |
| 26 | partial bundle | PASS — COMPLETE, PARTIAL and UNAVAILABLE requested/missing horizon grids. |
| 27 | ranking output | PASS — exact score/rank/percentile/universe/tie metadata in test_context.py. |
| 28 | event context | PASS — exact event references/windows/timing/materiality and rejection checks. |
| 29 | regime context | PASS — native filtered hard/soft regime metadata; smoothed/ex-post rejection. |
| 30 | uncertainty context | PASS — native decomposition values and identifiability statuses, including unavailable components. |
| 31 | orthogonal context | PASS — exact projection/spec/source references and compatibility checks. |
| 32 | fusion context | PASS — exact fusion sources/weights/contributors/missingness and law preservation. |
| 33 | health metadata | PASS — exact compatible health metadata and NONE_DESCRIPTIVE_ONLY boundary. |
| 34 | challenge metadata | PASS — exact program/run/champion/challengers/assessments and MANUAL_ONLY boundary. |
| 35 | registry entry | PASS — exact native artifact/model metadata and snapshot registry links. |
| 36 | registry ordering | PASS — canonical entry ordering and frozen catalog keyset pages. |
| 37 | version info | PASS — engine/API/schema/store/SQLite/Python/dependency identities in replies and VersionInfo. |
| 38 | capability catalog | PASS — advertised capabilities match implemented and snapshot-specific availability. |
| 39 | unsupported capability | PASS — explicit UNAVAILABLE for unsupported or absent capabilities. |
| 40 | stable public errors | PASS — stable typed errors expose sanitized constant messages. |
| 41 | target-free snapshot/service | PASS — all closed outcome classes guarded before read/caches, including warmed TargetVintage. |
| 42 | late-artifact rejection | PASS — late sources/contexts rejected; live receipt, later archive and qualified reconstruction distinguished. |
| 43 | corrected-source identity | PASS — corrected native source appends a new snapshot identity; prior bytes preserved. |
| 44 | corrected-context identity | PASS — corrected health/challenge context creates a new included-context identity. |
| 45 | no hidden latest | PASS — exact IDs or versioned explicit catalogs/selectors; ambiguous matches fail closed. |
| 46 | no direct external-engine regressions | PASS — provider-neutral contracts, no external-engine/runtime-network imports; scripted scan. |
| 47 | docs consistency | PASS — 213 documents checked; exact 26-phase roadmap, versions, links and report structure. |
| 48 | demo | PASS — 77 asserted deterministic offline demo checks. |
| 49 | benchmark/profile | PASS — all 12 requested bounded profile measurements recorded in service-profile.json; no production SLA. |
| 50 | dependency check | PASS — Python 3.11+, standard library only; project runtime dependency list remains empty. |

## Changed files and status

64 files: 17 tracked modifications and 47 new files, all unstaged on `main`. HEAD remains `0a0765520ac2b9f7c366a6bea280f00dd72b8b80`. Every earlier `src/` and `tests/` file remains byte-identical to the baseline except the required version constants in `src/afre/version.py`. The earlier challenger example now orders outputs by partition/time instead of content hash; native challenger code and assertions are unchanged. No commit or push.

### Tracked modifications

- [README.md](../README.md)
- [docs/AFRE_MASTER_SPEC.md](AFRE_MASTER_SPEC.md)
- [docs/champion-challenger.md](champion-challenger.md)
- [docs/drift-decay-model-health.md](drift-decay-model-health.md)
- [docs/ensemble-signal-fusion.md](ensemble-signal-fusion.md)
- [docs/forecast-uncertainty-decomposition.md](forecast-uncertainty-decomposition.md)
- [docs/invariance-stability-research.md](invariance-stability-research.md)
- [docs/model-selection-framework.md](model-selection-framework.md)
- [docs/multiple-testing-controls.md](multiple-testing-controls.md)
- [docs/nonlinear-feature-interactions.md](nonlinear-feature-interactions.md)
- [docs/research-reproducibility.md](research-reproducibility.md)
- [docs/stability-evaluation.md](stability-evaluation.md)
- [docs/transaction-cost-aware-research.md](transaction-cost-aware-research.md)
- [examples/challenger_fixture.py](../examples/challenger_fixture.py)
- [pyproject.toml](../pyproject.toml)
- [scripts/check_documentation.py](../scripts/check_documentation.py)
- [src/afre/version.py](../src/afre/version.py)

### New files

- [benchmarks/service_profile.py](../benchmarks/service_profile.py)
- [docs/AFRE_24_COMPLETION_REPORT.md](AFRE_24_COMPLETION_REPORT.md)
- [docs/afre-service-api.md](afre-service-api.md)
- [docs/artifact-registry.md](artifact-registry.md)
- [docs/forecast-snapshot.md](forecast-snapshot.md)
- [docs/service-errors.md](service-errors.md)
- [docs/service-profile.json](service-profile.json)
- [docs/service-reproducibility.md](service-reproducibility.md)
- [docs/service-versioning.md](service-versioning.md)
- [docs/snapshot-context.md](snapshot-context.md)
- [docs/snapshot-retrieval.md](snapshot-retrieval.md)
- [examples/service_demo.py](../examples/service_demo.py)
- [examples/service_fixture.py](../examples/service_fixture.py)
- [src/afre/service/__init__.py](../src/afre/service/__init__.py)
- [src/afre/service/audit.py](../src/afre/service/audit.py)
- [src/afre/service/bounds.py](../src/afre/service/bounds.py)
- [src/afre/service/context.py](../src/afre/service/context.py)
- [src/afre/service/context_builder.py](../src/afre/service/context_builder.py)
- [src/afre/service/facade.py](../src/afre/service/facade.py)
- [src/afre/service/lineage.py](../src/afre/service/lineage.py)
- [src/afre/service/native.py](../src/afre/service/native.py)
- [src/afre/service/outputs.py](../src/afre/service/outputs.py)
- [src/afre/service/publisher.py](../src/afre/service/publisher.py)
- [src/afre/service/queries.py](../src/afre/service/queries.py)
- [src/afre/service/registry.py](../src/afre/service/registry.py)
- [src/afre/service/registry_entries.py](../src/afre/service/registry_entries.py)
- [src/afre/service/repository.py](../src/afre/service/repository.py)
- [src/afre/service/responses.py](../src/afre/service/responses.py)
- [src/afre/service/schema.py](../src/afre/service/schema.py)
- [src/afre/service/serialization.py](../src/afre/service/serialization.py)
- [src/afre/service/snapshot_builder.py](../src/afre/service/snapshot_builder.py)
- [src/afre/service/snapshots.py](../src/afre/service/snapshots.py)
- [src/afre/service/storage.py](../src/afre/service/storage.py)
- [src/afre/service/validation.py](../src/afre/service/validation.py)
- [src/afre/service/versions.py](../src/afre/service/versions.py)
- [tests/service/__init__.py](../tests/service/__init__.py)
- [tests/service/conftest.py](../tests/service/conftest.py)
- [tests/service/test_availability.py](../tests/service/test_availability.py)
- [tests/service/test_boundaries.py](../tests/service/test_boundaries.py)
- [tests/service/test_context.py](../tests/service/test_context.py)
- [tests/service/test_integrity.py](../tests/service/test_integrity.py)
- [tests/service/test_outputs.py](../tests/service/test_outputs.py)
- [tests/service/test_queries.py](../tests/service/test_queries.py)
- [tests/service/test_replay.py](../tests/service/test_replay.py)
- [tests/service/test_requests.py](../tests/service/test_requests.py)
- [tests/service/test_storage.py](../tests/service/test_storage.py)
- [tests/service/test_workflow.py](../tests/service/test_workflow.py)

## Validation history

The final runtime/source/test/config freeze contains 857 files and pins the baseline HEAD. Earlier incomplete attempts found a test-module collection collision (zero tests ran), resolved by the service test package marker, and a hash-sensitive prior example ordering failure (191 passed, one failed before stopping). The smallest fixture ordering correction preserved native contracts and all prior assertions; the affected boundary/context/integrity tests passed (35 tests). The final frozen full invocation completed successfully: 3,254 passed and zero failures/errors/skips. No focused tests or expensive full gate were repeated after the resume request; only final static/documentation checks and this report were completed.

## Exact final validation evidence

- Full gate exit code: `0`. Pytest duration: `11204.83s`; JUnit duration: `11204.696s`; gate wrapper duration: `11205.108676333912s`.
- Full test count: `3254`; failures `0`; errors `0`; skips `0`; service test cases in the full JUnit report: `78`.
- Combined coverage: `98.3353064823987%`; statements: `98.97447918192739%`; branches: `95.3305785123967%`.
- Exact coverage: `33779` covered / `350` missing statements (`34129` total); `6921` covered / `339` missing branches (`7260` total), including `293` partial branches.
- Coverage JSON records `branch_coverage=true`. Socket/DNS denial was installed before importing AFRE; fresh-child socket/DNS probes also passed, including replaced child environments.
- Both frozen inventory/HEAD checks passed. Freeze manifest SHA-256: `5b634c186c04fcbc88a11489186619ebfc3e46488b0522a30953ac9161d18018`.
- Independent Gaussian threshold maximum absolute error: `2.7755575615628914e-17`; known empirical/mixture atom-tie oracle error: `0.0`. The profile reports the latter fixture, not a universal error guarantee.
- Offline demo/profile: `77` asserted checks, all 12 requested measurement categories; measured storage `35889152` bytes. These are bounded synthetic measurements without a production SLA.

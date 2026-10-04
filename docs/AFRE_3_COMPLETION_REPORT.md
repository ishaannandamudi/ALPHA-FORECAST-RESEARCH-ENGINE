# AFRE-3 completion report — A–AT

AFRE-3 — Point-in-Time Universe & Security Eligibility is complete. Engine 0.4.0;
universe/foundation/feature/target schemas 1.0; SQLite store 1.3/user_version=4.
The advanced roadmap remains 26 distinct phases, AFRE-0 through AFRE-25.
AFRE-4 is deferred. Changes remain unstaged and uncommitted on main.

| Item | Area | Implementation and acceptance evidence |
| --- | --- | --- |
| A | Architecture | Typed immutable identity/evidence → exact input build → bitemporal membership → separate eligibility → frozen snapshot → existing foundation manifest. No ticker-derived identity. |
| B | Package structure | Dedicated 18-module afre.universe package: schema, identity, evidence, securities, listings, lifecycle, calendars, definitions, membership, models, queries, liquidity, eligibility, providers, repository, engine, validation and exports. Symbols live with listings; relationships with lifecycle. |
| C | Universe schema | New universe schema 1.0 and u_ identity domains. Foundation, feature-store and target schemas remain 1.0. |
| D | Engine/store versions | Engine/project 0.4.0; additive store 1.3/user_version=4. Historical metadata retains foundation 0.1.0, feature 0.2.0 and target 0.3.0. |
| E | Security master | Immutable SecurityRecord/IssuerRecord with supplied opaque IDs, type/share class/asset class/country/currency/jurisdiction and temporal source evidence. Conflicting master identities fail; no fuzzy reconciliation. |
| F | Issuer/security separation | Distinct typed StableIssuerId and StableSecurityId; shared issuer does not collapse preferred, ADR, warrant or other security identities. Tests create different securities under one issuer. |
| G | Listing identity | Separate ListingId, temporal venue/currency/primary/calendar records and explicit selected_listing policy. Multiple admissible listing choices conflict; secondary listings are selectable explicitly. |
| H | Symbol history | Immutable SymbolAssignment with listing/security, venue, valid/knowledge intervals and six clocks. Resolver requires symbol, venue and both cutoffs plus admitted listing evidence. |
| I | Ticker changes/reuse | OLD→NEW retains one stable security; ABC before/after old delisting resolves to unrelated IDs/listings. Historical venue/dual-listing and ambiguity regressions pass. |
| J | Lifecycle events | Typed IPO/direct listing, spinoff, merger/acquisition, bankruptcy, delisting/relisting, share-class/name/ticker/venue events preserve source/effective/knowledge clocks. Delisting is evaluated even after listing end. |
| K | Security relationships | Typed issued-by, primary-listing, ADR, successor/predecessor and spinoff relationships, independently bitemporal and validated against supplied identities. No historical identity rewrite. |
| L | Universe definitions | Semantic name/version uniqueness; separate membership source category, neutral source, eligibility, supplied calendar and trusted builder. Current-constituent historical definitions rejected. |
| M | Membership vintages | INCLUDED/EXCLUDED/UNKNOWN/CONFLICTED, immutable source/delivery/valid/knowledge evidence and compatible predecessor chains. Corrections add vintages; equal-precedence contradictions conflict. |
| N | Bitemporal semantics | Independent [start,end) valid/knowledge intervals; publication is not receipt. Late archives remain late knowledge. Qualified historical reconstruction requires exact source/entity and locally approved attestor, retaining actual later physical clocks. |
| O | Membership query | membership_as_of uses indexed universe/security/cutoff candidates within exact frozen build. It reports used and known-future record IDs plus explicit coverage; announcements do not confer earlier effective membership. |
| P | Snapshots | UniverseInputBuild freezes exact admitted evidence and AFRE-1 market vintage IDs, policy/cutoff/actual construction. UniverseSnapshot pins sorted full membership/eligibility grids, coverage, definition/calendar and engine/builder identities. Later/backdated inserts cannot alter old bytes. |
| Q | Completeness | COMPLETE/KNOWN_GAPS/UNKNOWN are explicit. Absence is exclusion only under a complete source contract; uncertain/conflicted/not-yet-available decisions downgrade complete coverage. Query overflow fails rather than truncates. |
| R | Eligibility policy | Immutable explicit security/venue/country/currency/listing/session/price/liquidity/history/tradability/missing rules. Results contain typed state, first failing reason and exact evidence; membership is retained separately. |
| S | Price eligibility | Latest completed effective price, with per-observation AFRE-1 revision/tie/freshness rules, must be positive/PRESENT/VERIFIED and effective <= T, available <= min(T,known). Future price/adjustment and currency regressions pass. |
| T | Liquidity eligibility | Exact elapsed (T-lookback,T] window, minimum count, trailing share-volume sum and mean aligned price × shares. Future delivery, missing/negative volume and missing price alignment cannot contribute. No implicit FX or imputation. |
| U | History/tradability | Listing age counts supplied completed sessions separately from usable market observations. Historical HALTED/SUSPENDED/DELISTED/UNKNOWN, session closures and explicit extended hours have typed outcomes. |
| V | Security types | All eleven requested categories: COMMON_STOCK, PREFERRED_STOCK, ADR, ETF, FUND, REIT, SPAC, WARRANT, RIGHT, UNIT, OTHER_EQUITY. Common-only rules reject each other category in parameterized tests. |
| W | PIT resolution | Symbol + venue + valid_at + known_as_of yields exact stable security/listing, missing or explicit conflict. Inadmissible listing evidence cannot resolve a symbol. Security/universe/snapshot histories are bounded. |
| X | Survivorship protection | Historical A/B/C retains C after its later delisting. Current existence/constituents are never used to filter old samples. Known future D and late discoveries remain separate. |
| Y | Delisting/merger/spinoff | Old delisted membership/snapshot remains stored. Merger and spinoff events/relationships preserve original membership, prices and stable IDs. Relisting/contradictory terminal events follow explicit temporal rules. |
| Z | Feature compatibility | Complete causal snapshot projects to unchanged UniverseManifest at [T,T+1ns), with snapshot fingerprint in identity. Real AFRE-1 feature joins accept matching full origins and reject wrong security/universe. No old rows rewritten. |
| AA | Target compatibility | Real AFRE-2 target dataset uses the same projected universe/full origin as features. Wrong origin/security/universe evidence is rejected. Snapshot changes alter downstream dataset identity. |
| AB | Provider contracts | Typed neutral protocols for security master, listings, symbols, lifecycle, constituents, tradability and eligibility market vintages. OfflineUniverseProvider and OfflineEligibilityMarketProvider are deterministic data-only sources. |
| AC | Persistence/migration | Eight immutable universe tables, exact input-membership indexes and registered artifact families. Additive AFRE-1/2→4 migration preserves previous payload/table/DDL/metadata values; injected migration failure rolls back to valid target store. Unknown future versions fail. |
| AD | Indexes/performance | Security/issuer/listing/symbol/membership/identifier/lifecycle/relationship/snapshot/eligibility access uses temporal indexes and bounded retrieval. Benchmark plans show u_symbol_idx, u_membership_idx and fs_history_idx. Coverage/validated identity caching is scoped to one pinned transaction. |
| AE | Deterministic replay | Canonical snapshot bytes match seeds 0/1/42/random, reversed insertion, restart and frozen-build replay. Existing foundation/feature/target demo identities remain stable; AFRE-2 demo explicitly pins its historical engine-0.3.0 fixture. |
| AF | Concurrency | Actual second SQLite writer inserts a backdated correction while a read snapshot remains pinned. Old input build/current read preserve bytes; subsequent new build reflects correction and gets another identity. |
| AG | Audit/provenance | audit_security identifies policy/member/listing/calendar/security/relationships/lifecycle and exact price/volume sources. Deep audit recalculates results from frozen inputs and checks payload/hash/index/orphan integrity. Demo security audit has 17 lineage nodes. |
| AH | Security | Closed data-only canonical decoding, immutable contracts, bounded payload/history/lineage, no package network/shell/eval/exec/pickle/dynamic executable loading, no provider-selected paths or fuzzy identity inference. Tests block sockets/DNS, including child processes. |
| AI | Documentation | Six required universe documents plus benchmark and this report; README/master/temporal/reproducibility/feature/target documentation and consistency checker updated. Exact 26-phase roadmap preserved; next phase is explicitly AFRE-4. |
| AJ | Tests added | 97 AFRE-3 cases across five test modules plus fixtures: identity/types, membership/qualification/revisions, symbols/listings, eligibility, survivorship/lifecycle, migration/corruption/immutability/bounds, four seeds/order/restart/concurrency and actual feature/target compatibility. Original test files byte-identical. |
| AK | Full pytest | 381 passed, including original 284. Focused universe suite: 97 passed. Full suite's autouse guard blocks sockets/DNS; subprocess determinism independently blocks those APIs. |
| AL | Coverage | 98.85% combined statement/branch coverage; 4,516/4,543 statements and 983/1,020 branches covered. Separate statement coverage 99.41%, branch coverage 96.37%; required combined threshold >=95% passed. |
| AM | Ruff | Whole-repository lint and format checks pass. |
| AN | Mypy | Whole-repository strict mypy passes, 105 source files. |
| AO | Diff review | Tracked diff and all added implementation/tests/docs/example/profile reviewed; git diff --check clean. Prior implementation hashes unchanged except version.py; only old demo change explicitly pins historical fixture engine identity. No staging, commit or push. |
| AP | Secret/TODO scan | Scripted repository scan passes secrets, unfinished-work markers, whitespace and executable-data boundary checks over tracked and untracked deliverables. |
| AQ | Benchmark/profile | Offline 2,000-security / 12,002-universe-record / 8,000-market-vintage workload passes repeated snapshot/restart/audit. Unprofiled repeated snapshot 16.470s; ingestion 22.462s; persistence with replay 26.060s; full audit 47.177s; database 119,549,952 bytes. Full measurements and query plans are in universe-benchmark.md; no production SLA. |
| AR | Dependencies | Zero runtime dependencies, Python 3.11+. Existing pinned development dependencies unchanged. |
| AS | Remaining limitations | Supplied IDs, clocks, calendar schedules, source completeness and delivery attestations require external authenticity audits. Master classifications are immutable; explicit lifecycle/listing/relationship histories describe changes. One selected listing per security per universe definition; no fuzzy mapping, FX/borrow/shorting or live adapters. Coarse input builds pin all admitted repository evidence; default universe bounds are 2,000 securities, 100,000 inputs, 5,000 per-query vintages, 1,000 snapshots, 100,000 lineage nodes, depth 64 and 8 MiB per universe artifact/query/audit. Foundation canonical decoder's 16 MiB/depth-64 limits also remain. Timings are local observations, not a service SLA. |
| AT | Exact AFRE-4 scope | Dataset Builder & Leakage-Safe Splitting only: PIT universe snapshots, PIT feature joins, completed target joins, exact sample identity, purged walk-forward folds, embargo, overlapping-label exclusion, rolling/expanding windows, fold-local preprocessing, fit/validation/test boundaries, dataset manifests, contamination audits and reproducible split identity. Deferred, with no split generation or predictive fitting in AFRE-3. |

Acceptance commands:

```sh
.venv311/bin/pytest tests/universe -q
.venv311/bin/pytest -q --cov=afre --cov-branch --cov-report=term-missing
.venv311/bin/ruff check .
.venv311/bin/ruff format --check .
.venv311/bin/mypy --strict
.venv311/bin/python scripts/check_repository.py
PYTHONPATH=src:. .venv311/bin/python scripts/check_documentation.py
git diff --check
PYTHONPATH=src:. .venv311/bin/python -m examples.foundation_demo
PYTHONPATH=src:. .venv311/bin/python -m examples.feature_store_demo
PYTHONPATH=src:. .venv311/bin/python -m examples.target_demo
PYTHONPATH=src:. .venv311/bin/python -m examples.universe_demo
PYTHONPATH=src:. .venv311/bin/python -m benchmarks.universes
```

See [PIT universes](point-in-time-universes.md), [security master](security-master.md),
[identity](security-identity.md), [membership](universe-membership-vintages.md),
[eligibility](security-eligibility.md), [survivorship](survivorship-bias-controls.md)
and [benchmark](universe-benchmark.md).

All AFRE-0/1/2 contracts/tests are preserved. Portfolio construction, risk
optimization and execution remain downstream. Predictive metrics do not establish
trading profitability. **Stop after AFRE-3. No commit or push was made.**

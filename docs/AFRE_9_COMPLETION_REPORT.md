# AFRE-9 completion report

Scope: Cross-Sectional Alpha & Ranking. Stop after AFRE-9.
All changes remain in the working tree for review; no commit or push is performed.
The advanced roadmap remains 26 distinct phases, AFRE-0 through AFRE-25.

| Item | Area | Evidence / result |
| --- | --- | --- |
| A | Architecture | Additive same-origin research layer above unchanged AFRE-0–8 contracts; pure computations, frozen reads and atomic immutable publication. |
| B | Package structure | 20 modules in `afre.cross_sectional`, separating contracts, source extraction, peer transforms, models, diagnostics, bounded queries, persistence and audit. |
| C | Schema | Cross-sectional schema1.0; all earlier public schema versions remain1.0. Closed registered types and finite scalar safe JSON. |
| D | Engine/store versions | Engine0.10.0, global store1.9, SQLite user_version10; additive transactional9→10. |
| E | Cross-section identity | Full ForecastOrigin context except instrument, exact rich target/horizon, universe snapshot, eligibility policy, stable security order and supplied scoring/peer policies. |
| F | Universe/eligibility | Exact INCLUDED/ELIGIBLE AFRE-3 snapshot grid and its listing evidence; historical delisted members remain rankable, current constituents cannot project backward. |
| G | Canonical ordering | Stable security fingerprint order, exact duplicate rejection; reversed security, group and external-signal insertion yields identical artifacts. |
| H | Observation contract | Own full origin/security, exact source and optional historical group reference, snapshot listing; unsupported issuer enrichment rejects instead of guessing. |
| I | Score source types | POINT_PREDICTION, POINT_EXPECTATION, MEDIAN, QUANTILE, THRESHOLD_PROBABILITY and EXTERNAL_SIGNAL; exact native model/calibration state or provider semantics/version/unit. |
| J | Rank direction | Explicit HIGHER_BETTER or LOWER_BETTER. Rank1 means best; percentile transform retains the declared favorable direction. |
| K | Tie semantics | AVERAGE_RANK, MIN_RANK, MAX_RANK and DENSE_RANK on exact equality; percentile1−(rank−1)/(N−1), singleton0.5. Dense ranks retain the N denominator. |
| L | Normalization | Origin-local NONE, population/sample z-score and percentile; exact admitted peers, explicit minimum N, zero-scale output0 with CONSTANT quality. Separate from learned TRAIN preprocessing. |
| M | Robust normalization | Deterministic median/MAD with supplied identity-bearing scale multiplier; zero MAD explicit. No winsorization or implicit clipping. |
| N | Missingness | EXCLUDE_MISSING, FAIL_ON_MISSING and RETAIN_UNRANKED; all eligible cells remain visible, no imputation and supplied maximum missing fraction. |
| O | Quality states | VALID, TOO_SMALL, CONSTANT, EXCESSIVE_MISSINGNESS and UNAVAILABLE cross-sections; per-security missing/future/invalid/unsupported/group-unavailable reasons. |
| P | PIT group memberships | SECTOR/INDUSTRY/SUBINDUSTRY/CUSTOM, provider/taxonomy/version, valid interval and known/delivery clocks; future reclassification cannot change frozen ranks. |
| Q | Group-neutral scoring | Exact admitted group demeaning; FAIL, LEAVE_RAW or MARK_UNAVAILABLE small-group policy. Missing classification is withheld; raw/global/group outputs have separate immutable references. No group z-score. |
| R | Cross-sectional model semantics | Completed AFRE-5 CROSS_SECTIONAL_LINEAR wrapper, admitted DesignMatrix and existing QR solver, individual squared-error loss, exact same-origin TRAIN groups and optional TRAIN target centering. |
| S | Training causality | AFRE-5 replayed TRAIN admission/target cutoffs and completed fit required; relative fitting cannot precede baseline evidence. Held-out targets never enter fit. |
| T | Target-free prediction | Feature-only AFRE-5 scaffold and exact preprocessing; original relative coefficients recomputed, no current realized target or contemporaneous target mean. Ranking construction reads no truth. |
| U | External signal contract | Immutable provider/version/schema, stable security, optional venue, name/version/semantics, as-of, six clocks, scalar/unit, typed quality, SourceReference and fingerprint; ordinary FeatureVintage bridge. |
| V | External signal availability | Actual receipt bounds live use; source timestamps alone never establish historical availability. Late archive reconstruction requires exact qualified delivery evidence and explicitly approved attestor; actual later physical clocks remain intact. |
| W | Provider-neutral boundary | Data-only ExternalSignalProvider; no AME imports, private SQLite registry, sibling paths or copied algorithms. Downstream HFT integration owns adapters. Execution-state fields reject. |
| X | Rank artifact | Complete immutable eligible grid, raw/normalized/group scores, ordinal/percentile ranks, source/peer references, typed reasons, coverage and computation/availability. |
| Y | Rank availability | Inputs must be available by exact origin cutoff; ranking computation is at/after origin and at/before cutoff. Current causal build requires cutoff=origin and never backdates later composition. |
| Z | Exclusions/coverage | Exact ranked/eligible fraction, explicit withheld cells and reasons; evaluation retains its own score/truth intersection and exclusions. Missingness bias documented. |
| AA | Truth construction | Later exact full-origin/rich-target vintages or explicit absence on the complete grid; native truth must match pinned AFRE-4 sample. REQUIRE_COMPLETE or AVAILABLE_INTERSECTION is explicit. |
| AB | Pearson IC | Stable AFRE-5 Pearson on the exact selected-score/truth intersection; N always retained, small/constant inputs yield explicit undefined metrics. Positive/negative/constant fixtures passed. |
| AC | Rank IC | Correlation of declared deterministic tied ranks on the same exact intersection. Average ranks implement conventional Spearman; alternative tie policies are explicitly documented rank correlations. |
| AD | Top/bottom diagnostics | Exact K with N≥2K, canonical ID splitting at boundary ties, exact realized means and descriptive top-minus-bottom spread; never a tradable portfolio return. |
| AE | Bucket diagnostics | Worst-to-best balanced integer partitions, exact membership/counts/means and weak monotonicity fraction; insufficient N explicit, no executable strategy. |
| AF | Group-neutral evaluation | Pooled demeaning of both score and truth within the evaluation intersection using pinned PIT groups and minimum counts; separate exact group sample and N. |
| AG | IC aggregation | Compatible chronological evaluations with unique cross-section identities; total/defined counts, mean, median, population stddev and positive fraction. No significance or selection claims. |
| AH | Stability | Explicit compatible ordered origin pair, same-members or intersection mode; intersection Spearman, top-K overlap, full-rank displacement and separate eligible/ranked membership turnover. No execution cost conversion. |
| AI | Multi-horizon treatment | Each exact horizon ranks independently; no cross-horizon fused scalar, shared rank or implicit target conversion. Existing AFRE-8 artifacts remain unchanged. |
| AJ | Probabilistic ranking | Exact requested expectation/median/quantile/event; raw/calibrated statistics distinct. Calibrated expectation only when full distribution preserved; unsupported statistics withheld. |
| AK | TEST boundary | Native TEST sources require explicit evaluation identity and existing AFRE-4 seals/reuse; truth/sample/cutoff pinned, exact repeat idempotent, changed access evidence rejects. |
| AL | Audit | Semantic replay checks exact universe/origin, eligible/ranked sets, exclusions, score/normalization/group/tie/availability, truth cutoff, TEST and historical-admissibility evidence. |
| AM | Lineage | Unified bounded ranking→spec→scores→peer/group/external refs→model/fit→fold/TRAIN→features/targets/universe traversal; explicit node/depth/byte limits. |
| AN | Persistence/migration | Immutable three-table extension with canonical JSON/hash/type/schema/index validation. Migration success, injected rollback, future rejection, prior rows/DDL/metadata preservation, idempotence and corruption passed. |
| AO | Indexes/performance | Indexed origin/target/horizon/universe/security/group/provider/source/model/rank/evaluation-cutoff/availability lookups. Bounds apply to query results and serialized outputs. Profile measures validation/persistence separately. |
| AP | Deterministic replay | Fresh processes with seeds0/1/42/random, normal/reversed securities/groups/signals, restart full audit and byte-identical semantic replay passed. |
| AQ | Concurrency | Second writer inserts corrected universe, group, target and external evidence while ranking snapshot is open; old reader cannot see writes, exact published old bytes remain unchanged. Explicit correction creates a new identity. |
| AR | Numerical correctness | Independent mean/std, median/MAD, percentile, group mean, Pearson, tied-rank, stability and top/bottom references. Profile maximum error1.1102230246251565e-16. |
| AS | Security | Closed finite scalar/registered JSON, explicit allocation/store/lineage bounds; no eval/exec/pickle/joblib, runtime shell/network, executable imports or provider paths. Tests and replay workers block socket/DNS; static no-AME regression passed. |
| AT | Documentation | Six requested scope docs, singular PIT-universe guide, profile/report and updated README/master/universe/split/fit/multi-horizon/reproducibility references; 26 phases AFRE-0–25 preserved. |
| AU | Tests added | 143 focused AFRE-9 tests passed in 76.88s, including migration, numerical, causal, TEST, bounds, corruption, concurrency and eight seed/order combinations. |
| AV | Full pytest | PASS: 1,136 tests in 386.24s, including all 993 earlier tests and 143 AFRE-9 tests. Full suite blocks socket/DNS. |
| AW | Coverage | PASS: branch mode enabled, 99.03% combined coverage against 95% threshold; 1,136 tests passed in 1002.22s. Statements 12,607/12,672 (99.49%); branches 2,653/2,738 (96.90%). |
| AX | Ruff | PASS: lint and formatting checks across 358 Python files, including the updated documentation checker. |
| AY | Mypy | Strict full-repository check passed across 282 source files. |
| AZ | Diff review | Additive AFRE-9 package/tests/demo/profile/docs and version/documentation gate updates. Baseline SHA256 comparison confirms earlier runtime/tests unchanged except src/afre/version.py. No staged changes, commit or push. |
| BA | Secret/TODO scan | PASS: 363 deliverables scanned for secrets, unfinished-work markers and whitespace; git diff --check clean. Documentation checker passed 76 documents, exact 26 phases and 57 A–BE report items. |
| BB | Benchmark/profile | 12×1,000 pure numerical cells with 20 groups; separate two-origin four-eligible/three-ranked persisted pipeline, 56 AFRE-9 artifacts, 82 audit nodes and 9,326,592-byte SQLite. Demo and profile passed; no SLA. |
| BC | Dependencies | Python3.11+ and standard library only; project runtime dependencies remain[]. No new optional runtime loaders or direct external engine dependency. |
| BD | Remaining limitations | No later historical ranking composition, issuer enrichment, group z-score, winsorization, learned ranking loss, automatic origin adjacency, significance or cross-horizon fusion. Scalars cannot authenticate provider claims. Large profile measures numerical kernels; persisted causal fixture is smaller. |
| BE | Exact AFRE-10 scope | Deferred Event-Conditioned Forecasting: EIE event classes, materiality, novelty, surprise, event-time alignment, pre/post-event information, windows, event-specific calibration/evaluation, overlapping events, cross-sectional effects and neutral external reaction/microstructure inputs. No AFRE-10 implementation. |

See [rank semantics](cross-sectional-ranking.md), [external availability](external-signal-integration.md)
and [reproducible profile](cross-sectional-benchmark.md). Predictive metrics do not
establish trading profitability. Portfolio construction, risk optimization and
execution remain downstream projects after AFRE. AFRE-18 transaction-cost-aware
evaluation, AFRE-19 overfitting controls, AFRE-20 model selection, AFRE-21 ensemble,
AFRE-22 drift, AFRE-23 challenger evaluation, AFRE-24 forecast service and AFRE-25
final hardening remain distinct deferred phases.

Working tree: `main...origin/main`, 10 modified tracked files and 43 new files;
no staged changes. HEAD remains `66590ae Add multi-horizon forecast architecture`.
No commit or push is performed.

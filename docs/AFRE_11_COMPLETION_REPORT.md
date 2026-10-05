# AFRE-11 completion report

Scope: Regime-Conditioned Models. Stop after AFRE-11. No commit or push.
Roadmap: 26 distinct phases, AFRE-0 through AFRE-25.

| Item | Topic | Evidence / result |
|---|---|---|
| A | Architecture | Separate provider-neutral regime layer above frozen completed phases0–10. |
| B | Package structure | 21 focused modules in afre.regime_conditioned; new offline fixtures/tests/profile. |
| C | Schema | Regime-conditioned1.0; every earlier public schema remains1.0. |
| D | Versions | Engine0.12.0; store1.11; SQLite12; Python3.11+. |
| E | Provider reference | Exact provider/version/schema/taxonomy/version/method/source identity. |
| F | Taxonomy | Ordered state IDs/labels/descriptions, category, provider, dimensionality/version. |
| G | States | Provider data; no provider/state-name-specific behavior. |
| H | Snapshot clocks | As-of distinct from publication/source/receipt/ingestion/computation/final availability. |
| I | Scope | GLOBAL/MARKET/SECURITY/PIT SECTOR; VENUE/CUSTOM explicit unsupported matching. |
| J | Hard membership | Exactly one taxonomy state, explicit one-hot fitting weights. |
| K | Soft membership | Complete ordered finite nonnegative vector, declared tight sum tolerance, no normalization/argmax. |
| L | Causal-state semantics | FILTERED only; SMOOTHED/EX_POST stored but excluded from causal forecasting. |
| M | Quality/staleness | Explicit quality exclusions and inclusive elapsed maximum age. |
| N | Matching | Explicit candidate/mapping refs, latest(final availability,as-of), exact-as-of/fail-on-multiple; equal-clock ambiguity fails. |
| O | Spec | Exact target/base/taxonomy, membership/scope/matching/count/weight/fallback/calibration/seed versions. |
| P | Samples | Full ResearchSample/origin/PIT universe, exact regime/target/availability/partition/transition bindings. |
| Q | TRAIN causality | Exact admitted AFRE-4 TRAIN matrix and labels known by fit cutoff; regimes usable at own origin. |
| R | Families | Hard state target mean, hard fitted-residual offset, soft weighted offset; no regime-linear/learned gate. |
| S | Hard conditioning | TRAIN means/offsets with exact sample IDs, state counts and support. |
| T | Soft conditioning | Supplied probability weighted residual means and sum(p*offset), minimum effective support. |
| U | Fallback | FAIL, USE_BASE or matched-TRAIN GLOBAL_OFFSET; insufficient positive soft state invokes whole-output fallback. |
| V | Base linkage | Immutable exact AFRE-5 point/raw AFRE-6 or declared AFRE-10 event refs. |
| W | Point conditioning | State mean replacement or residual shift over exact base. |
| X | Probability conditioning | Raw location translation preserves shape/scale; quantiles/thresholds recomputed; no joint law. |
| Y | Calibration | Scarcity/unavailable/incompatible assessment; SUPPORTED reserved and rejected; no calibrator fitted. |
| Z | Forecast | Distinct safe artifact pins model/spec/sample/membership/base/output/composition/clocks. |
| AA | Availability | All inputs and actual computation <= origin cutoff; live receipt never backdated; qualified reconstruction retains physical clocks. |
| AB | Truth-free application | TargetVintage and TRAIN-matrix read guard; base bytes unchanged. |
| AC | Cross-sectional integration | Exact derived neutral signals into AFRE-9, same-origin target/horizon and PIT group controls. |
| AD | Event base | Exact compatible target-mean location replacement in base→event→regime order; TEST/matched/lineage preserved. |
| AE | Multi-horizon | Actual1h/1d independent AFRE-8 bindings/models/forecasts sharing exact regime evidence; no parameter pooling. |
| AF | Transitions | Exact consecutive supplied causal-history hard/soft adjacencies, vector mass change and identity. |
| AG | Transition causality | New state must be known; future switches/smoothed states excluded. |
| AH | Duration | Observed elapsed lower bound; no future completed duration or completeness claim. |
| AI | Truth/evaluation | Explicit later exact available truth and existing point/proper scoring metrics. |
| AJ | Matched baseline | Identical sample/truth vintage set on both sides; deltas descriptive. |
| AK | State breakdowns | Hard groups plus probability-weighted soft diagnostics/count/effective support/entropy/low-confidence. |
| AL | Transition breakdowns | Transition/recent/stable/unknown cohorts with declared minimum counts. |
| AM | Regime IC | AFRE-9 Pearson/rank IC; constant predictions remain explicitly undefined. |
| AN | Drift | Known ordered disjoint windows: state probability/error and transition-frequency changes, explicit scarcity/null components. |
| AO | No auto-refit | Descriptive drift never changes fit/model/taxonomy, tunes/selects/promotes. |
| AP | Coverage/exclusions | Supplied eligible grid: matched/unmatched/stale/invalid/unsupported, plus exact truth exclusions. |
| AQ | TEST | Explicit native seal/reuse; calibration excludes TEST; derived ranking wrapper preserves controls. |
| AR | Audit | Six clocks, semantics/scope/matching/TRAIN/model/base/fallback/calibration/horizon/TEST/reconstruction replay. |
| AS | Lineage | One bounded traversal spans regime/provider/source, optional event, folds/TRAIN/features/targets. |
| AT | Persistence | Immutable canonical JSON/indexes; transactional11→12 additive migration, idempotence/conflict checks. |
| AU | Indexes | Provider/taxonomy/state/scope/subject/as-of/availability/origin/target/horizon/spec/model/cutoff/transition/drift/TEST projections. |
| AV | Replay | Seeds0/1/42/random; reversed taxonomy/snapshot/request order; restart semantic bytes identical. |
| AW | Concurrency | Concurrent regime/target/taxonomy corrections preserve exact frozen origin computation. |
| AX | Numerical accuracy | Independent state/soft/shift/vector/metric/IC/drift oracles; profile maximum absolute error 2.7755575615628914e-17. |
| AY | Security | Safe data only; no eval/exec/pickle/joblib/shell/network/dynamic provider imports/filesystem paths. |
| AZ | Docs | Seven regime documents plus benchmark/profile/report; required earlier boundaries/README/master/checker updated. |
| BA | Focused tests | 140 focused AFRE-11 tests pass; all required causal/numerical/migration/corruption/bounds/replay/concurrency regressions covered. |
| BB | Full pytest/offline | 1,426 tests pass with socket/DNS blocked in 661.94s; coverage run also passes all 1,426 tests in 1465.57s. Frozen source fingerprints match. |
| BC | Coverage | Branch-enabled full suite passes: 98.93% combined statement/branch coverage, 99.44% statements and 96.53% branches; required combined minimum95%. |
| BD | Ruff | Repository lint passes;441 files formatted. |
| BE | Mypy | Strict mypy passes across347 source files. |
| BF | Git diff/status | Complete tracked/untracked diff reviewed; git diff --check passes. main tracks origin/main;14 modified and45 new files, no staged changes. Earlier implementation/tests unchanged except central version file. No commit/push. |
| BG | Secret/TODO scan | Scripted secret/TODO/FIXME/whitespace scan passes for448 tracked/untracked deliverables. |
| BH | Profile | 37-step offline demo/restart passes. Saved profile:1,000 extra snapshots,8 taxonomy versions,3 state models,12 causal TRAIN samples/model plus separate50,000-row arithmetic kernel; max error2.7755575615628914e-17; no SLA. |
| BI | Dependencies | Zero runtime dependencies; stdlib only, no upstream ML/HMM libraries. |
| BJ | Limits | In-sample residual bias, observed-history duration only, external evidence authenticity, no learned gating/linear/calibrator/joint law/venue adapter/profitability. |
| BK | Exact AFRE-12 scope | Mixture of Experts: expert definitions; point/prob/event/regime/external microstructure/macro/optional options experts; fixed/learned causal gating with availability/missingness, calibration/evaluation and contribution diagnostics. Deferred; no arbitrary nonlinear framework. |

See [forecasting](regime-conditioned-forecasting.md), [profile](regime-conditioned-benchmark.md) and [saved measurements](regime-conditioned-profile.json). Earlier completion reports remain historical records. Portfolio construction, risk optimization and execution are downstream. Predictive metrics never establish trading profitability.

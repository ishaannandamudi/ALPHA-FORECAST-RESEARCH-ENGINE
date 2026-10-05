# AFRE-10 completion report

Scope: Event-Conditioned Forecasting. Stop after AFRE-10.
AFRE-11 remains deferred. No commit or push.

| Item | Topic | Result |
| --- | --- | --- |
| A | Architecture | Frozen causal event evidence → independent TRAIN model → exact-base application → matched later evaluation; prior implementations preserved. |
| B | Package structure | 19 modules under src/afre/event_conditioned; separate contracts, matching, fitting, forecasts, evaluation, bridge, storage, validation and lineage. |
| C | Schema | New event-conditioned1.0; every earlier public schema remains1.0. |
| D | Engine/store versions | Engine0.11.0; store1.10; SQLite11; Python3.11+. |
| E | Event reference | Immutable ID/revision/provider/schema, optional occurrence, six-clock evidence, source, quality and attributes; neutral EIE snapshot retained when supplied. |
| F | Event classes/subtypes | Twelve generic typed classes; stable subtype/tags are data. |
| G | Subject/scope | Exact security, issuer, historical sector, market/universe and macro matching; CUSTOM metadata has no matching adapter. |
| H | Event clocks | Occurrence, publication, source availability, actual receipt/ingestion/computation and final availability distinct; qualified reconstruction retains later physical clocks. |
| I | Materiality | Provider/fixed-rule numeric value with exact method/version/unit/bounds; fixed inclusive thresholds. |
| J | Novelty | Exact provider/method/version/cutoff/source; no corpus recomputation. |
| K | Surprise | Exact actual/expectation sources and units, positive normalization; both inputs available before computation. |
| L | Event windows | Elapsed UTC only, exact anchor, lookback/delay/maximum age, inclusivity, target/horizon and implementation. |
| M | Event-origin relations | PRE_EVENT, AT_EVENT, POST_EVENT and POST_EVENT_DELAYED; no implicit calendar/bar windows. |
| N | Event matching | PIT eligibility and explicit mapping refs; exact class/subtype/attributes/window/reactions; every exclusion pinned. |
| O | Event samples | MatchSet and observations pin sample/full origin, fold scope, target metadata, event/reaction refs and signed distance. |
| P | Training causality | Exact admitted TRAIN matrix responses known at fit cutoff; event/reaction available at each origin; held-out samples excluded. A read guard forbidding every non-TRAIN TargetVintage reproduces the exact fitted model. |
| Q | Overlap policies | Fail-on-multiple, canonical nearest tie-break, all-events-separate; unit relation weights with distinct counts, correlated repeated labels and unique-sample evaluation. |
| R | Reaction-signal integration | Unchanged AFRE-9 ExternalSignal/ScoreSpec; own clocks, security and semantic keys; no EIE/AME adapter or algorithm. |
| S | Event conditioning spec | Exact base/target/window/criteria/thresholds/features/overlap/minimum counts/numerical policies/attestors. |
| T | Conditioned model families | Class conditional target mean and materiality/surprise/declared-feature linear QR; independent target regression, no in-sample residual claim. |
| U | Base forecast linkage | Exact completed AFRE-5 model/point forecast and optional raw AFRE-6 forecast; base bytes preserved. |
| V | Point conditioning | Class mean or declared linear prediction; shift computed relative to exact base; explicit unaffected/insufficient-class fallbacks. |
| W | Probabilistic conditioning | Location translation of Gaussian/empirical/sparse quantile output; fixed scale/shape; recomputed thresholds. |
| X | Calibration semantics | Separate unique VALIDATION evidence; insufficient/unavailable assessment. Fitted conditioned calibration is unsupported; unconditioned AFRE-7 state rejected. |
| Y | Event-conditioned forecast | Immutable conditioned output with exact spec/model/observation/base/input refs, value/shift/state and optional probability view. |
| Z | Forecast availability | Physical composition follows every input and occurs within origin cutoff; late forecast-computation reconstruction unsupported. |
| AA | Target-free application | Guard test forbids TargetVintage reads during application; truth is read only by fit/evaluation/audit. |
| AB | Cross-sectional event conditioning | Neutral derived scores into unchanged AFRE-9 PIT ranking; affected/unaffected wrapper and common full origin. |
| AC | Multi-horizon treatment | Independent exact horizons/models/forecasts/evaluations; no fused ranking or joint distribution. |
| AD | Truth/evaluation | Pinned ResearchSample target vintage/full origin and later explicit cutoff; unavailable truth excluded. |
| AE | Matched baseline comparison | Baseline and conditioned metrics share exact sample/truth pairs; deltas are conditioned minus base. |
| AF | Event breakdowns | Class, configured attributes, age, horizon, overlap and affected status; minimum count gives explicit insufficient data. |
| AG | Event IC | Existing AFRE-9 Pearson/rank IC; synthetic demo Pearson0.6778340786040317; independent Pearson oracle. |
| AH | Coverage/exclusions | Coverage3/4 in fixture; event, reaction, scope/window and truth exclusion reasons retained. |
| AI | TEST boundary | Explicit native TEST evaluation identity/access seal; exact reuse idempotent, conflicting reuse rejected; TEST never calibrates. |
| AJ | Audit | Full semantic replay of roots, indexes/hashes/contracts, completed fits and prior-phase lineage. |
| AK | Lineage | Bounded nodes/depth/bytes through event sources, subject/mapping/attributes/reactions, base models, folds, features and targets. |
| AL | Persistence/migration | Atomic additive10→11; older rows/metadata/DDL preserved; rollback/future rejection, immutable tables and idempotence tested. |
| AM | Indexes/performance | Event/class/scope/security/availability, origin/target/horizon, spec/base/model/cutoff and TEST indexes; profile separates kernel from causal workflow. |
| AN | Deterministic replay | Seeds0/1/42/random, reversed event/reaction/request/upstream insertion and restart preserve canonical semantic bytes. |
| AO | Concurrency | Second writer corrects event, TRAIN/held-out target and reaction during frozen reads; pinned computations and old bytes unchanged. |
| AP | Numerical correctness | Independent class means, stdlib linear regression, matched metric/group/IC oracles and exact location translation. Profile coefficient max absolute error7.81e-18. |
| AQ | Security | Canonical structured data, fixed imports/SQL; no runtime network/eval/exec/pickle/joblib/shell/provider paths or direct EIE/AME imports. |
| AR | Documentation | Pass:85 documents checked; seven required guides plus profile/report, README/master and seven integration guides;26 distinct phases AFRE-0 through AFRE-25. |
| AS | Tests added | 150 focused cases pass, including timing/receipt/reconstruction, mapping/windows, overlap, numerical models, TEST, corruption/migration/bounds/replay/concurrency. Final demo passes with378 evidence nodes. |
| AT | Full pytest | Pass:1,286 tests in522.90s with socket/DNS blocking; all1,136 earlier tests preserved and150 AFRE-10 cases added. |
| AU | Coverage | Pass: full branch-enabled combined coverage98.94%; branch coverage96.60%;95% combined gate passed. Coverage run:1,286 tests in1,224.40s. |
| AV | Ruff | Pass: full Ruff lint; formatting check reports397 files already formatted. |
| AW | mypy | Pass: strict mypy across312 source files. |
| AX | Diff review | Pass: complete tracked/new-file diff review; prior runtime/tests/examples/benchmarks unchanged except global version; source hashes frozen for final gates. Working tree:12 modified and40 untracked files, none staged, main tracks origin/main; no commit/push. |
| AY | Secret/TODO scan | Pass: scripted secret/unfinished-work/whitespace scan across403 deliverables and git diff --check. |
| AZ | Benchmark/profile | Pass: bounded offline profile,100 event refs/overlap relations,50,000 kernel checks, reaction lookup, two linear families, four forecasts/rank/IC/audit/restart;1,786 artifacts and10,973,184 SQLite bytes. No production SLA. |
| BA | Dependencies | Pass: zero runtime dependencies; imports are standard library and AFRE only; existing pinned developer tooling unchanged. |
| BB | Remaining limitations | Elapsed windows, no custom matching, class minimum fallbacks, no conditioned variance/calibrator or historical forecast-computation proof; provider authenticity unproven; conditioning is not causation/profitability. |
| BC | Exact AFRE-11 scope | Regime-Conditioned Models: MCE and neutral liquidity regimes, regime fits/evaluation/transitions, soft/hard membership, separate regime calibration/drift; no mixture-of-experts gating. Deferred. |

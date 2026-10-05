# AFRE-12 completion report

AFRE-12 — Mixture of Experts. Changes remain in the current working tree for review.
No commit or push. Frozen roadmap:26 distinct phases, AFRE-0 through AFRE-25.

| Item | Scope | Result |
| --- | --- | --- |
| A | architecture | Exact independently identified producers → causal bindings → declared gate → immutable mixture; target-free application. |
| B | package structure | 21 modules in src/afre/mixture; dedicated demo/horizon fixture,14 test modules and bounded profile. |
| C | schema | Mixture1.0; all earlier public schemas remain1.0. |
| D | engine/store versions | Engine0.13.0; store1.12; SQLite user_version13; additive12→13. |
| E | expert kinds | Native point/probability/event/regime and neutral microstructure/context/options/generic. |
| F | expert reference | Semantic ID, kind/provider/version/schema, rich target/horizon, exact model, source, output, availability and quality. |
| G | expert set | Canonical exact producer order, target/output, declared missing/fallback/age/attestor policy; duplicate aliases reject. |
| H | target/horizon compatibility | Exact rich TargetDefinition equality; mismatched duration/return/residual/benchmark/output rejects. |
| I | expert availability | Contributing producer/forecast final availability ≤ origin cutoff; receipt floor and approved historical evidence enforced. |
| J | expert quality | VALID/MISSING/STALE/DEGRADED/UNSUPPORTED/INVALID; missing values remain None. |
| K | gating modes | FIXED and LEARNED_LINEAR constant simplex weights. Contextual, softmax and neural gating deferred. |
| L | fixed gating | Finite nonnegative declared weights and explicit availability; sum1 within ≤1e-12 tolerance; no implicit normalization. |
| M | learned gate spec | Exact set/fold/cutoff/features, fixed ridge, mean-SSE objective, no intercept, numerical policy/seed/version. |
| N | gating features | Exact causal security feature, neutral signal or filtered regime state weight; audit-only, no execution/target inputs. |
| O | gate training causality | Admitted AFRE-4 TRAIN only; expert forecasts historically usable at each origin; completed verified labels known at cutoff. |
| P | gate artifact | Exact TRAIN rows/bindings/features/labels, fitted weights, objective/KKT residual, convergence and fit/availability clocks. |
| Q | missing expert semantics | FAIL, explicit DROP_AND_RENORMALIZE, exact USE_DECLARED_FALLBACK; reasons and original weights retained. |
| R | fallback semantics | Exact declared set member gets effective weight1; unavailable fallback fails; no hidden substitution. |
| S | point mixture | fsum of effective weight × exact scalar; independent1/3 weighted.25/.75 fixture gives2.5. |
| T | contribution accounting | Per-expert original/effective weight, value, contribution and reason; final sum checked exactly. |
| U | probabilistic mixture | Finite positive weighted component laws retain exact expert/binding/original distribution identities. |
| V | Gaussian mixture | Component CDF/events, stable Gaussian-only log-sum-exp NLL and analytic pair CRPS; no Gaussian collapse. |
| W | empirical mixture | Exact weighted atoms/events/CRPS; mixed Gaussian/empirical laws supported; empirical/mixed NLL unsupported. |
| X | sparse-quantile handling | No exact law/expectation from sparse quantiles; cannot contribute. All mixture quantiles explicitly unsupported; never averaged. |
| Y | mixture expectation | Weighted component means; equals probabilistic point output. |
| Z | mixture variance | Within plus between-component variance; no independence or joint-law assertion. |
| AA | threshold probabilities | Exact weighted GT/GE/LT/LE events including atom boundaries; only tolerance-boundary roundoff clamps. |
| AB | mixture forecast | Exact request/security/full origin/target/partition/gate/contributions/law/fallback/availability fingerprint. |
| AC | forecast availability | At least gate, contributing experts, gating evidence, fallback and actual computation; ≤ origin cutoff. |
| AD | target-free application | Read guards forbid TargetVintage, DesignMatrix and GateTrainingRow reads during fixed/fitted application. |
| AE | expert immutability | Exact expert bytes remain unchanged; corrections create new identities and preserve old mixtures. |
| AF | event expert | AFRE-10 native point/raw-law expert retains exact observation/sample/target/model provenance. |
| AG | regime expert | AFRE-11 native point/raw-law expert retains exact filtered-state/model/sample provenance. |
| AH | external microstructure expert | Neutral immutable specialist forecast boundary; no AME/axiom implementation import. |
| AI | external context expert | Neutral macro/context specialist producer; no MCE implementation import. |
| AJ | external options expert | Neutral options specialist point/raw-law producer; no options-engine import. |
| AK | cross-sectional integration | Explicit derived mixture score → unchanged AFRE-9 same-origin/PIT-group ranking and matched IC/TEST bridge. |
| AL | multi-horizon treatment | AFRE-8 independent architecture reused; actual1h/1d mixtures have distinct rich targets and gates; no pooling. |
| AM | expert correlation/diversity | Exact pair intersections, prediction/error Pearson correlations and mean absolute disagreement; descriptive only. |
| AN | calibration semantics | Dedicated insufficient/unavailable/incompatible assessment; component calibrators never transfer; fitting deferred. |
| AO | truth/evaluation | Later known verified exact origin/security/target truth; explicit coverage/exclusions; earlier metrics reused. |
| AP | matched expert comparison | Each expert and mixture use identical sample/truth intersection for all reported deltas. |
| AQ | weight diagnostics | Mean/median/min/max/zero frequency, availability, effective count and normalized entropy. |
| AR | contribution diagnostics | Signed/absolute contribution and positive-weight frequency; arithmetic attribution, never causal importance. |
| AS | gate drift | Known ordered disjoint windows with exact gate/set; weight/availability and MAE changes; explicit insufficient support. |
| AT | no-auto-refit | Drift, correlations, ranking and TEST evaluation never refit, retune, prune or select. |
| AU | TEST boundary | Explicit seal/reuse records; TEST cannot fit/tune/select/calibrate/alter weights; perturbation fit invariant. |
| AV | audit | Semantic replay checks experts, gates, clocks, TRAIN/TEST, weights/laws, contributions, calibration and admissibility. |
| AW | lineage | One bounded node/depth/byte traversal through all completed phases and exact completed-fit admission. |
| AX | persistence/migration | Append-only safe canonical JSON + verified projections; success/rollback/future-schema/prior row/DDL/metadata tests. |
| AY | indexes/performance | Exact expert/provider, target/horizon, security/origin, gate, availability, missingness, cutoff and TEST indexes. |
| AZ | deterministic replay | Seeds0/1/42/random × normal/reversed experts/requests; reversed feature references; byte-identical restart. |
| BA | concurrency | Second-writer expert/gate/target corrections leave frozen application and exact fit artifacts unchanged. |
| BB | numerical correctness | Independent arithmetic/CDF/events/CRPS/NLL/simplex/correlation/effective-count/matched-delta oracles; profile max error9.33e-11. |
| BC | security | No executable serialization/plugins, upstream implementation imports, runtime shell/network or provider filesystem paths. |
| BD | documentation | 8 new scope/profile guides, master/README and7 integration guides; exact26-phase roadmap preserved; A–BO report. |
| BE | tests added | 153 focused AFRE-12 tests PASS; all1,426 previous tests/assertions preserved. |
| BF | full pytest | PASS:1,579 tests in1,145.28s; full suite blocked socket creation and DNS. |
| BG | coverage | PASS:1,579 tests in2,206.72s with sockets/DNS blocked;98.86% combined,99.39% statement,96.34% branch; ≥95% gate passes. |
| BH | Ruff | PASS: ruff check . and ruff format --check .;488 files already formatted. |
| BI | mypy | PASS: strict mypy;385 source files. |
| BJ | diff review | PASS:60 files reviewed (12 modified/48 new); all prior code/tests unchanged except version metadata and documentation checker. git diff --check clean;386 frozen validation inputs match. |
| BK | secret/TODO scan | PASS:496 deliverables scanned for secrets, unfinished work and whitespace; documentation checker validates103 documents, links, versions, historical reports and exact26-phase roadmap. |
| BL | benchmark/profile | Offline profile:6 point/3 probability experts,12 causal TRAIN rows,1,000 external revisions,10,000 separately labelled arithmetic rows,50,000 point sums; workflow and numerical stages timed, no SLA. |
| BM | dependencies | Zero runtime dependencies; Python3.11+; fixed development tools unchanged. |
| BN | remaining limitations | Constant learned gates; no contextual/softmax/neural gates, signed weights, sparse-quantile law/inversion, empirical/mixed NLL or fitted mixture calibrator; no joint covariance/security-specific gate, automatic pruning/refit, late reconstructed mixture computation or real upstream adapters. Provider hashes cannot establish authenticity or opaque scalar causality. No portfolio or profitability claims. |
| BO | exact AFRE-13 scope | Deferred Nonlinear Feature Interactions: explicit interactions, nonlinear transforms, appropriate tree research models, stability, supported monotonic/shape constraints, cross-feature, event × regime, microstructure × context; no temporal/sequence models yet. No AFRE-13 implementation. |

See [scope](mixture-of-experts.md), [measured profile](mixture-profile.json),
[profile interpretation](mixture-benchmark.md) and [master specification](AFRE_MASTER_SPEC.md).

Stop after AFRE-12. AFRE-13 remains deferred. No commit. No push.

Final git status: main...origin/main;12 modified and48 new files (60 total), nothing staged.
HEAD remains c575002 Add regime-conditioned forecasting. No commit or push.

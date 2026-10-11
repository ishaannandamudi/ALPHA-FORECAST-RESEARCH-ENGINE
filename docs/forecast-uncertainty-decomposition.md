# Forecast uncertainty decomposition

AFRE-15 adds `afre.uncertainty`, engine **0.16.0**, uncertainty schema **1.0**, shared store **1.15**, SQLite **user_version=16**. Every earlier public schema stays **1.0**. Runtime dependencies remain empty. The frozen roadmap has **26 distinct phases, AFRE-0 through AFRE-25**.

`UncertaintyRepository` extends the strict AFRE-14 repository through additive transactional migration15→16. `UncertaintyEngine` fits frozen covariance, constructs target-free decompositions, extracts intervals, evaluates exact later truths, compares matched assessments, describes drift, and audits bounded lineage. Canonical immutable artifacts pin exact source/model/sample/fold/target/horizon, supplied requests, measures, identifiability policy, numerical tolerance, seed/version and availability. Separate `unc_artifacts`, `unc_records`, and `unc_links` have immutable triggers and lookup indexes. Earlier repository interfaces continue to reject future layouts.

Sources are AFRE-5 point, AFRE-6 probability, AFRE-7 calibrated, AFRE-10 event, AFRE-11 hard/soft regime, AFRE-12 mixture, AFRE-13 nonlinear, and AFRE-14 sequence forecasts. Each source must resolve an exact VALIDATION or TEST research sample. TRAIN diagnostic forecasts cannot become held-out uncertainty. Gaussian variance is sigma²; finite empirical variance uses population denominator N, not N−1. Quantile-only marginals do not identify variance. A calibrated marginal mapping cannot manufacture a complete law.

Only the exact finite-mixture within/between identity supports `EXACT_ADDITIVE` here. The compatible terms are `WITHIN_EXPERT_PREDICTIVE`, `EXPERT_DISAGREEMENT` and an explicitly requested `RESIDUAL_UNATTRIBUTED`. Closure error must lie within `tolerance * max(1,total_variance)`; a partial identity requires a residual to close. Negative residuals outside tolerance reject; even a tiny negative residual is rejected rather than silently clamped. Component shares exist only for identified, additive variance terms and positive total. Zero total yields `None` shares. OLS noise and parameter variance are not silently added to an unrelated predictive law. `APPROXIMATE_ADDITIVE` is typed but unsupported; ordinary diagnostic components are non-additive.

Availability is at least every source/estimator/alternative and actual decomposition computation time, and must be at or before origin cutoff. Existing late or reconstructed diagnostics cannot become causal AFRE-15 forecasts. Provider publication is not AFRE receipt. This phase introduces no historical reconstruction permission. Forecast construction blocks target vintages and response-bearing TRAIN matrices even through repository caches. Covariance fitting is a separate TRAIN operation. Later evaluation and full audit may read target evidence; audit does not mean forecast construction used truth.

Bounds cover16components,2000samples/atoms,17covariance dimensions,32experts/alternatives,20buckets,32drift windows,128cohorts,2m covariance work cells,8MiB payload/lineage,100k lineage nodes,depth64 and20k records per family. Callers may lower bounds. Unsupported numerical claims carry explicit status and no value.

See [identifiability](uncertainty-identifiability.md), [noise and knowledge semantics](aleatoric-epistemic-semantics.md), [parameter assumptions](parameter-uncertainty.md), [expert disagreement](expert-disagreement-uncertainty.md), [event/regime](regime-event-uncertainty.md), [calibration](uncertainty-calibration.md), [evaluation](uncertainty-evaluation.md), [profile](uncertainty-benchmark.md) and [completion report](AFRE_15_COMPLETION_REPORT.md).

Run the35-step offline demo with `PYTHONPATH=src:. .venv311/bin/python -m examples.uncertainty_demo`.

**Stop after AFRE-23. Next scope: AFRE-24 — Forecast Snapshot, Registry & Service.** AFRE-17 adds declared descriptive stability research. AFRE-18 cost-aware evaluation is complete; AFRE-20 adds declared bounded model selection. Explicit AFRE-21 fusion is complete; ranking adjustment, portfolio allocation and refit automation remain deferred.

Predictive uncertainty does not establish trading profitability. These are descriptive forecast artifacts; portfolio construction, risk optimization and execution remain downstream projects after AFRE. AFRE-15 has no direct external-engine dependency.

## AFRE-16 integration

Identified or explicitly numerical proxy diagnostics can enter supplied signal comparisons only with exact component/measure/method/units/model/covariance policy. An uncertainty quality label is not numerical variance or alpha. Candidate projections remain target-free and cannot manufacture epistemic attribution.

See [signal orthogonalization](signal-orthogonalization.md). Supplied candidate/reference sets are fixed;
no automatic pruning or broad signal search occurs. Orthogonal != independent, residuals are not
guaranteed alpha, and predictive metrics do not establish trading profitability. The frozen roadmap
remains26 distinct phases, AFRE-0 through AFRE-25; AFRE-17 Invariance & Stability Research is complete.

AFRE-17 adds [declared environment stability research](invariance-stability-research.md) over frozen artifacts. PIT memberships, target/horizon compatibility, exact intersections and minimum counts remain explicit. Input shift and error degradation are separate; there is no causal-proof, significance, profitability, auto-refit/prune or promotion claim. AFRE-18 [cost-aware research evaluation](transaction-cost-aware-research.md) is complete.

AFRE-18 [explicit hypothetical cost research](transaction-cost-aware-research.md) now
evaluates frozen native forecasts/residual signals using separate exposure, cost and later
truth artifacts. Gross and net remain separate; PIT cohorts retain full-path trade deltas.
Uncertainty does not automatically become cost and ranking/stability definitions are unchanged.
Historical-causal versus ex-post evidence is explicit, and supplied grids cannot select TEST
settings. No execution, model selection, direct external-engine dependency or profitability
proof is added. AFRE-19 Multiple Testing & Research Overfitting Controls is complete; see [the control layer](multiple-testing-controls.md).

AFRE-19 integration: [declared controls](multiple-testing-controls.md) register exact native
source/truth, target/horizon, environment and cost-scenario opportunities without mutating
prior artifacts. [Registry snapshots](research-trial-registry.md) retain failed attempts,
TEST reuse and caller-recorded selection sets. Corrections do not establish independence,
causality or profitability, and no automatic model selection or pruning occurs.

## AFRE-21 integration

AFRE-21 can attach an exact source ForecastUncertaintyDecomposition as separate post-hoc FusionMetadata. It cannot turn uncertainty into alpha or modify weights automatically. An exact probability mixture reports within-plus-between variance without claiming epistemic identification. See [fusion evaluation](fusion-evaluation.md).

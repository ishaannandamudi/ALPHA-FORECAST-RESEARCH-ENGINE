# Alpha Forecast & Research Engine (AFRE)

AFRE is a point-in-time quantitative research foundation. Its eventual output is
a calibrated multi-horizon return distribution with uncertainty, feature/model
lineage and honest out-of-sample evidence. **AFRE-0–AFRE-23 are complete.**
AFRE-4 adds Dataset Builder & Leakage-Safe Splitting: frozen causal research grids,
explicit failed cells, scoped interval purge, elapsed/session/bar embargo,
walk-forward/rolling/expanding/holdout folds, train-only simple preprocessing,
label-cutoff filters, test-evaluation records and contamination audits.
AFRE-5 adds transparent statistical baselines: TRAIN-only mean/median/reference,
causal persistence, QR OLS/ridge, deterministic lasso/elastic net, cross-sectional
and supplied-residual linear models, feature-only point forecasts and exact-sample
evaluation. Hyperparameters are fixed inputs; no automatic selection occurs.
AFRE-6 adds explicit TRAIN-only empirical/Gaussian/quantile distributions, causal
target-free forecasts, proper scores, calibration diagnostics and immutable lineage.
AFRE-6 evaluates calibration diagnostics but does NOT fit calibration transformations.
AFRE-7 adds explicit reserved causal calibration, immutable adjusted forecasts,
independent evaluation and bounded drift diagnostics.
AFRE-8 adds exact horizon sets, independent/shared point architectures, matched
TRAIN covariance, explicit partial bundles and separate horizon evaluation.
AFRE-9 adds causal same-origin relative rankings, explicit peer/group transforms,
IC/buckets/stability and receipt-aware provider-neutral external signals.
AFRE-10 adds exact causal event vintages/windows, TRAIN-only interpretable conditioning,
explicit overlap, neutral reaction features, matched evaluation and event ranks.
AFRE-11 adds exact causal hard/soft regime evidence, TRAIN-only state fits, explicit
fallback, causal transitions, matched evaluation/ranks and descriptive drift.
AFRE-12 adds exact independent experts, fixed/constant simplex learned gates, causal
availability/missingness, finite probability mixtures and matched contribution diagnostics.
Point-in-Time Feature Store, Forecast Targets & Label Construction and
Point-in-Time Universe & Security Eligibility remain compatible.

Python **3.11+**; engine **0.24.0**; foundation, feature-store, target, universe,
dataset, model, probabilistic, calibration, multi-horizon, cross-sectional, event-conditioned, regime-conditioned, mixture, nonlinear, sequence, uncertainty, orthogonalization, invariance, transaction-cost-research, multiple-testing, selection, fusion, health and champion/challenger schemas **1.0**;
shared research store **1.23**, `user_version=24` (additive to store1.22/user_version23). Runtime uses only the
standard library.

The architecture consists of immutable typed contracts, pure validation,
deterministic JSON/domain-separated SHA-256 identity, provider protocols and an
append-only transactional SQLite artifact registry. Every feature must satisfy
`available_time <= origin availability cutoff <= forecast origin`. Every training
label must be completed and available at fit cutoff. Effective time and knowledge
time remain separate. Stable security IDs and historical membership replace ticker
identity and current-constituent reconstruction.

Upstream publication and source availability, actual AFRE receipt, ingestion,
computation and final feature availability remain distinct. Live features cannot
precede physical receipt/processing. A qualified historical-delivery contract may
establish historical availability while retaining actual later reconstruction
clocks; publication alone cannot backdate an archived feature.

EIE is an external upstream system via its final provider-neutral snapshot
boundary. MCE, options and AME are optional future providers. No sibling repository
is imported or modified; no upstream SQLite schema is assumed.

## Quickstart

```sh
python3.11 -m venv .venv311
.venv311/bin/python -m pip install -e '.[dev]'
.venv311/bin/python examples/foundation_demo.py
.venv311/bin/python examples/feature_store_demo.py
.venv311/bin/python examples/target_demo.py
.venv311/bin/python examples/universe_demo.py
.venv311/bin/python -m examples.research_dataset_demo
.venv311/bin/python -m examples.statistical_baselines_demo
.venv311/bin/python -m examples.probabilistic_demo
.venv311/bin/python -m examples.calibration_demo
```

For a checkout without editable installation, use:

```sh
PYTHONPATH=src .venv311/bin/python examples/foundation_demo.py
PYTHONPATH=src:. .venv311/bin/python examples/feature_store_demo.py
PYTHONPATH=src:. .venv311/bin/python examples/target_demo.py
PYTHONPATH=src:. .venv311/bin/python examples/universe_demo.py
PYTHONPATH=src:. .venv311/bin/python -m examples.research_dataset_demo
PYTHONPATH=src:. .venv311/bin/python -m examples.statistical_baselines_demo
PYTHONPATH=src:. .venv311/bin/python -m examples.probabilistic_demo
PYTHONPATH=src:. .venv311/bin/python -m examples.calibration_demo
```

The deterministic [example](examples/foundation_demo.py) does all twelve steps:

1. Defines a stable synthetic security ID.
2. Defines the forecast origin and explicit availability cutoff.
3. Registers two immutable feature definitions.
4. Constructs typed feature values with publication availability and lineage.
5. Demonstrates rejection of a feature available one nanosecond after origin.
6. Defines an elapsed one-day simple-return target with `(T, endpoint]` semantics.
7. Defines historical membership with valid and knowledge times.
8. Builds a dataset manifest with raw-price adjustment policy.
9. Defines a metadata-only model specification with recorded seed; fits nothing.
10. Defines an experiment specification with split, evaluation and cost policies.
11. Persists six definition/specification artifacts and reopens the database.
12. Asserts all fingerprints are unchanged and audits replayed artifacts.

It also checks that a label is unavailable at origin and available at the later
training cutoff. Data and label values are synthetic, not calculated returns.
The SQLite file is caller-chosen in a temporary directory.

The [AFRE-1 walkthrough](examples/feature_store_demo.py) registers five exact
definitions, extracts completed synthetic bars and neutral EIE features, computes
returns/volatility and a supplied-state z-score, freezes a historical materialization,
adds a later revision, verifies single/batch parity and byte-identical restart,
and reports lineage/audit evidence. Clocks and statistics are explicit fixtures.
Its historical dataset fixture explicitly pins engine 0.2.0 to preserve the
completed AFRE-1 example's materialization identity across this engine release.

The [AFRE-2 walkthrough](examples/target_demo.py) computes all eight target types,
verifies endpoint delivery and same-time training eligibility, demonstrates explicit
split policy, freezes exact source/label identities, inserts a later correction,
rebuilds a distinct dataset and verifies unchanged old rows across restart.
Target creation uses actual computation clocks; upstream publication alone cannot
backdate a label, including one reconstructed from a qualified historical source.

The [AFRE-3 walkthrough](examples/universe_demo.py) defines issuers, securities,
listings and historical symbols, announces a future constituent, applies price
and liquidity rules, delists a member, demonstrates ticker reuse, freezes a
snapshot, inserts a historical correction, creates a distinct corrected snapshot,
reopens the database and verifies byte-identical replay and a full security audit.
Use `UniverseRepository` for the additive shared store. Strict earlier repository
interfaces continue to reject future store versions. AFRE-2's demo explicitly pins
its historical engine-0.3.0 dataset fixture to preserve its completed example ID.

The [AFRE-4 walkthrough](examples/research_dataset_demo.py) freezes historical
universe/feature/target samples, preserves failed cells, constructs purged and embargoed
walk-forward folds, fits TRAIN statistics, records TEST evaluation, inserts a backdated
correction and verifies unchanged old exports and byte-identical restart.
Use `DatasetRepository` for the additive shared store; prior interfaces stay strict.

## Package

| Module | Responsibility |
| --- | --- |
| schema, ids, time, version | Strict immutable contract types, stable IDs, UTC nanoseconds, versions |
| hashing, serialization | Canonical data-only JSON and domain-separated identities |
| forecast, horizons | Origins and exact elapsed/session/bar horizon contracts |
| features, lineage | Definitions, values, explicit absence states, derived provenance |
| targets | Target specs/rows and completion eligibility; no labels computed |
| datasets | Dataset/universe manifests, feature rows, symbol/adjustment contracts |
| models, experiments, evaluation | Reproducible specifications and artifact/result metadata |
| providers, validation | External as-of protocols and pure boundary checks |
| persistence | Explicit transactions, immutable registry, migration and replay |
| feature_store | Registry/vintages, delivery evidence, indexed PIT selection, DAG computation, frozen joins, normalization lineage and additive store 1.1 |
| universe | Stable identity, historical listings/symbols/lifecycle, bitemporal constituents, separate eligibility, frozen snapshots, bounded audits and additive store 1.3 |
| research_datasets | Exact frozen samples/manifests, leakage-safe folds, scoped purge, typed embargo, TRAIN preprocessing, audits/export and additive store 1.4 |
| statistical_models | Fixed typed statistical baselines, numerical solvers, exact TRAIN matrices, immutable coefficients, feature-only point forecasts, evaluation/audits and additive store 1.5 |
| probabilistic | Fixed TRAIN residual/target distributions, explicit quantiles/events/scale, proper scores, bounded lineage and additive store 1.6 |
| multihorizon | Exact horizon sets, independent/shared point architectures, matched TRAIN covariance, separate surfaces/evaluation and additive store 1.8 |
| cross_sectional | Same-origin PIT rankings, peer normalization, groups, external signals, IC/stability and additive store1.9 |
| event_conditioned | Exact event clocks/windows, TRAIN conditioning, overlap/reactions, matched evaluation and additive store1.10 |
| mixture | Exact native/neutral experts, TRAIN-only simplex weights, finite laws, matched evaluation/ranks/diagnostics, additive store1.12 |
| orthogonalization | TRAIN QR projections, causal residuals, matched matrices/partial/incremental metrics, PIT ranks, descriptive stability, store1.16 |
| costs | Explicit hypothetical exposure paths, six-clock cost inputs, gross/net contributions, break-even and supplied sensitivity, store 1.18 |
| invariance | Declared PIT environments, explicit intersections, descriptive metrics/parameters/ranks, feature shift and separate degradation, store 1.17 |
| uncertainty | Identified/proxy components, exact mixture closure, TRAIN OLS covariance, intervals, coverage/sharpness, buckets/drift, store1.15 |
| sequence | Causal ordered windows, masks, TRAIN transforms, fixed decay/state dynamics, QR readouts, matched diagnostics, additive store1.14 |
| nonlinear | Explicit causal interactions, TRAIN-only knots/scaling, QR linear models, bounded trees, matched research diagnostics, additive store1.13 |
| regime_conditioned | Neutral hard/soft filtered regimes, TRAIN state means/offsets, causal transitions, matched metrics/ranks, drift and additive store1.11 |
| target_engine | Exact windows/prices/actions/benchmarks, path estimators, immutable label datasets, cutoff queries, audit and additive store 1.2 |

## Quality gates

Every pytest test blocks sockets and DNS, including the deterministic subprocess
checks. The Python package performs no networking or shell execution.

```sh
.venv311/bin/python -m pytest --cov=afre --cov-branch --cov-report=term-missing
.venv311/bin/ruff check .
.venv311/bin/ruff format --check .
.venv311/bin/mypy
.venv311/bin/python scripts/check_repository.py
.venv311/bin/python scripts/check_documentation.py
git diff --check
PYTHONPATH=src:. .venv311/bin/python benchmarks/foundation.py
PYTHONPATH=src:. .venv311/bin/python benchmarks/feature_store.py
PYTHONPATH=src:. .venv311/bin/python benchmarks/targets.py
PYTHONPATH=src:. .venv311/bin/python benchmarks/universes.py
PYTHONPATH=src:. .venv311/bin/python -m benchmarks.research_datasets
PYTHONPATH=src:. .venv311/bin/python -m benchmarks.statistical_models
PYTHONPATH=src:. .venv311/bin/python -m benchmarks.probabilistic
```

Coverage requires ≥95% combined statements/branches. Tests include leakage,
historical membership, ticker reuse, hash seeds, restart, corruption, migration,
immutability and the example. For a new repository with untracked files, the
repository check includes whitespace checks on every deliverable; ordinary
`git diff --check` alone does not include untracked content.

## Specification and roadmap

Read the [master specification](docs/AFRE_MASTER_SPEC.md),
[temporal semantics](docs/temporal-semantics.md),
[feature contracts](docs/feature-contracts.md),
[target contracts](docs/target-contracts.md),
[reproducibility](docs/research-reproducibility.md), and
[provider boundary](docs/provider-contracts.md).
AFRE-1 details: [feature store](docs/point-in-time-feature-store.md),
[vintages and delivery clocks](docs/feature-vintages.md),
[computation DAG](docs/feature-computation-dag.md),
[point-in-time joins](docs/point-in-time-joins.md), and
[normalization](docs/feature-normalization.md).
AFRE-2 details: [forecast targets](docs/forecast-targets.md),
[window rules](docs/target-window-semantics.md),
[label availability](docs/target-availability.md),
[corporate actions](docs/target-corporate-actions.md),
[lineage/isolation](docs/target-lineage.md), and [profile](docs/target-benchmark.md).
AFRE-3 details: [security master](docs/security-master.md),
[stable identity](docs/security-identity.md), [PIT universes](docs/point-in-time-universes.md),
[membership vintages](docs/universe-membership-vintages.md),
[eligibility](docs/security-eligibility.md), [survivorship controls](docs/survivorship-bias-controls.md)
and [profile](docs/universe-benchmark.md).
AFRE-4 details: [research datasets](docs/research-datasets.md),
[splitting](docs/leakage-safe-splitting.md), [purged folds](docs/purged-walk-forward.md),
[embargo](docs/embargo-semantics.md), [preprocessing](docs/fold-local-preprocessing.md)
and [contamination audits](docs/dataset-contamination-audits.md).
AFRE-5 details: [statistical baselines](docs/statistical-baselines.md),
[fit semantics](docs/model-fit-semantics.md), [linear models](docs/linear-models.md),
[regularization](docs/regularization-semantics.md), [point evaluation](docs/point-forecast-evaluation.md)
and [model replay](docs/model-reproducibility.md). The [offline model demo](examples/statistical_baselines_demo.py)
guards every target read during prediction and proves held-out perturbations cannot
change learned parameters. Use ModelRepository for the additive shared store.
The frozen advanced roadmap has **26 distinct phases, AFRE-0 through AFRE-25**.
Transaction-cost-aware research evaluation (AFRE-18), multiple-testing/overfitting
controls (AFRE-19), model selection (AFRE-20), ensembles (AFRE-21), drift/decay
(AFRE-22) and champion/challenger shadow evaluation (AFRE-23) remain separate.
AFRE-24 is the final forecast snapshot, registry and service boundary; AFRE-25 is
final integration, hardening and research audit. Portfolio construction, risk
optimization and execution remain downstream projects after AFRE. Predictive
metrics alone do not establish trading profitability.
The [AFRE-0 completion report](docs/AFRE_0_COMPLETION_REPORT.md) records its historical
baseline; the [AFRE-1 report](docs/AFRE_1_COMPLETION_REPORT.md) records its historical
feature-store gates. The [AFRE-2 A–AQ report](docs/AFRE_2_COMPLETION_REPORT.md) records
its historical target baseline. The [AFRE-3 A–AT report](docs/AFRE_3_COMPLETION_REPORT.md)
records its historical universe baseline. The [AFRE-4 A–AS report](docs/AFRE_4_COMPLETION_REPORT.md)
records its historical dataset baseline. The [AFRE-5 A–AV report](docs/AFRE_5_COMPLETION_REPORT.md)
records its historical model baseline and limitations.

AFRE-6 details: [probabilistic forecasting](docs/probabilistic-forecasting.md),
[distributions](docs/forecast-distributions.md), [quantiles](docs/quantile-forecasts.md),
[thresholds](docs/threshold-probabilities.md), [proper scores](docs/proper-scoring-rules.md),
[evaluation](docs/probabilistic-evaluation.md), [demo](examples/probabilistic_demo.py),
[profile](benchmarks/probabilistic.py) and [A–AU report](docs/AFRE_6_COMPLETION_REPORT.md).

AFRE-7 details: [forecast calibration](docs/forecast-calibration.md),
[probability mappings](docs/probability-calibration.md),
[quantile offsets](docs/quantile-calibration.md),
[conformal intervals](docs/conformal-calibration.md),
[explicit partitions](docs/calibration-partitions.md),
[drift diagnostics](docs/calibration-drift.md), [demo](examples/calibration_demo.py),
[profile](benchmarks/calibration.py) and [A–AW report](docs/AFRE_7_COMPLETION_REPORT.md).

AFRE-8 details: [multi-horizon forecasts](docs/multi-horizon-forecasting.md),
[horizon sets](docs/horizon-sets.md), [dependence](docs/cross-horizon-dependence.md),
[consistency](docs/multi-horizon-consistency.md),
[evaluation](docs/multi-horizon-evaluation.md),
[calibration by horizon](docs/horizon-specific-calibration.md),
[demo](examples/multihorizon_demo.py), [profile](docs/multi-horizon-benchmark.md)
and [A–AW report](docs/AFRE_8_COMPLETION_REPORT.md).

```sh
PYTHONPATH=src:. .venv311/bin/python examples/multihorizon_demo.py
PYTHONPATH=src:. .venv311/bin/python benchmarks/multihorizon.py
```

AFRE-9 details: [rankings](docs/cross-sectional-ranking.md),
[normalization](docs/cross-sectional-normalization.md), [IC](docs/information-coefficient.md),
[PIT groups](docs/group-neutral-ranking.md), [stability](docs/rank-stability.md),
[external boundary](docs/external-signal-integration.md), [demo](examples/cross_sectional_demo.py),
[profile](docs/cross-sectional-benchmark.md) and [A–BE report](docs/AFRE_9_COMPLETION_REPORT.md).

```sh
.venv311/bin/python -m examples.cross_sectional_demo
.venv311/bin/python -m benchmarks.cross_sectional
```

AFRE-10 details: [forecasting](docs/event-conditioned-forecasting.md),
[clocks](docs/event-time-semantics.md), [windows](docs/event-windows.md),
[attributes](docs/event-surprise-materiality-novelty.md), [overlap](docs/event-overlap.md),
[matched evaluation](docs/event-conditioned-evaluation.md),
[reaction boundary](docs/event-reaction-signals.md), [demo](examples/event_conditioned_demo.py),
[profile](docs/event-conditioned-benchmark.md) and [A–BC report](docs/AFRE_10_COMPLETION_REPORT.md).

```sh
PYTHONPATH=src:. .venv311/bin/python -m examples.event_conditioned_demo
PYTHONPATH=src:. .venv311/bin/python -m benchmarks.event_conditioned_profile
```

AFRE-11 adds [regime forecasting](docs/regime-conditioned-forecasting.md),
[snapshots](docs/regime-snapshots.md), [hard/soft membership](docs/hard-soft-regimes.md),
[transitions](docs/regime-transitions.md), [calibration assessment](docs/regime-conditioned-calibration.md),
[drift](docs/regime-drift.md), [external integration](docs/external-regime-integration.md),
[profile](docs/regime-conditioned-benchmark.md) and the [A–BK report](docs/AFRE_11_COMPLETION_REPORT.md).
The offline demonstration is `PYTHONPATH=src:. .venv311/bin/python -m examples.regime_conditioned_demo`.

AFRE-12 adds [mixture composition](docs/mixture-of-experts.md),
[expert contracts](docs/expert-contracts.md), [gating](docs/expert-gating.md),
[missingness](docs/expert-missingness.md), [finite laws](docs/probabilistic-mixtures.md),
[contributions](docs/expert-contributions.md), [external integration](docs/external-expert-integration.md),
[profile](docs/mixture-benchmark.md) and the [A–BO report](docs/AFRE_12_COMPLETION_REPORT.md).
Run `PYTHONPATH=src:. .venv311/bin/python -m examples.mixture_demo`.
Expert weights are forecast-combination weights, never portfolio weights. Component calibration
is not mixture calibration. No expert independence is assumed. Quantile averaging is invalid.

AFRE-15 adds [uncertainty decomposition](docs/forecast-uncertainty-decomposition.md),
[identifiability](docs/uncertainty-identifiability.md), [aleatoric/epistemic semantics](docs/aleatoric-epistemic-semantics.md),
[parameter covariance](docs/parameter-uncertainty.md), [expert disagreement](docs/expert-disagreement-uncertainty.md),
[event/regime ambiguity](docs/regime-event-uncertainty.md), [calibration](docs/uncertainty-calibration.md),
[evaluation](docs/uncertainty-evaluation.md), [profile](docs/uncertainty-benchmark.md) and
[A–BM report](docs/AFRE_15_COMPLETION_REPORT.md). Run the35-step offline demo with
`PYTHONPATH=src:. .venv311/bin/python -m examples.uncertainty_demo`.
Exact finite-mixture within/between variance closes under a declared identity; other diagnostic
measures remain non-additive. OLS covariance requires explicit fixed-design iid assumptions.
Aleatoric is distinct from epistemic; disagreement is not automatically epistemic;
quality diagnostics are not variance; calibration and sharpness remain separate.
Uncertainty is horizon-specific descriptive metadata with causal availability.

AFRE-16 adds [causal signal orthogonalization](docs/signal-orthogonalization.md): exact
candidate/reference sources, TRAIN-only deterministic QR/preprocessing, target-free frozen residuals,
common-intersection Pearson/Spearman matrices, rank/condition/VIF, partial association, matched
base/augmented target-model diagnostics, temporal and historical cross-sectional panels, explicit
AFRE-1 feature export and AFRE-9 PIT sector ranking, compatible-window descriptive stability,
immutable additive16→17 persistence and bounded unified audits. Orthogonal != independent;
redundancy is metric-dependent. No broad signal search, automatic pruning or model replacement.

Run `.venv311/bin/python -m examples.orthogonalization_demo` for the 37-step offline walkthrough
and `.venv311/bin/python -m benchmarks.orthogonalization_profile` for the bounded profile.
See [the A–BP completion report](docs/AFRE_16_COMPLETION_REPORT.md),
[profile results](docs/orthogonalization-profile.json) and [temporal semantics](docs/temporal-redundancy.md).

**Next scope: AFRE-24 — Forecast Snapshot, Registry & Service.**
AFRE-23 explicit champions/challengers, matched shadow evaluation and manual promotion/rollback advice are complete. AFRE-24 snapshot/registry/service remains future scope.
AFRE-22 provides descriptive health; automatic lifecycle actions remain excluded. **Stop after AFRE-23.** Portfolio construction,
risk optimization and execution remain downstream projects after AFRE.

Contracts establish declared provenance and invariants. They cannot authenticate
an upstream timestamp or detect a scalar secretly derived from future target data.
Provider audits remain necessary. AFRE-4 executes declared purge/embargo and TRAIN
statistics. AFRE-5 adds explicit fitted coefficients and point forecasts; foundational
model metadata retains its original contract role. AFRE-7 fits calibration only
on explicit causal non-TEST reservations.
Calibration and sharpness remain distinct; no calibration metric selects models
or establishes trading profitability.

## AFRE-13 nonlinear interaction research

Explicit immutable interaction definitions pin exact semantic inputs, transforms,
parameters, units, missingness and computation policy. Ordered source vintages remain
separate from definitions. Ten finite transforms implement products, safe ratios,
differences, absolute differences, squares, cubes, signed logs, clipped linear,
identity and fixed or TRAIN-quantile piecewise interpolation. Interactions are supplied;
there is no automatic expansion or feature search. Transform fitting is TRAIN-only.

LINEAR_ON_INTERACTIONS and LINEAR_PLUS_INTERACTIONS reuse AFRE-5 QR with fixed optional
ridge. SHALLOW_REGRESSION_TREE uses bounded TRAIN midpoints, SSE, explicit depth/leaf
limits and deterministic ties. Standardization is TRAIN-only; missing model columns
fail. Monotonic/shape constraints, splines and post-hoc shape repair are unsupported.

Neutral event attributes × filtered regime probabilities, microstructure × context,
options × context and causal expert output × state share the same explicit contract.
Derived availability cannot precede inputs, fitted state, model or actual computation.
Publication is not receipt; qualified reconstruction preserves actual later physical
clocks. Prediction reads no target truth. TEST cannot choose interactions/splits/knots.

Optional AFRE-6 location translation preserves shape/scale and recomputes events and
quantiles. Upstream calibrators are incompatible; dedicated nonlinear calibration is
unavailable. AFRE-9 receives an exact neutral score; later evaluation pins matched
truths and TEST reuse. Contributions, paths and compatible-window stability are
arithmetic/descriptive diagnostics, not causal importance. No automatic pruning/model
selection, direct external-engine dependency or sequence modeling is implemented.
Predictive metrics do not establish profitability. Portfolio construction, risk
optimization and execution remain downstream.

Run the offline demo and bounded profile:

```console
python -m examples.nonlinear_demo
python -m benchmarks.nonlinear_profile
```

See [nonlinear interactions](docs/nonlinear-feature-interactions.md),
[definitions](docs/interaction-definitions.md), [transforms](docs/nonlinear-transforms.md),
[trees](docs/shallow-tree-models.md), [stability](docs/interaction-stability.md),
[cross-domain contracts](docs/cross-domain-interactions.md),
[evaluation](docs/nonlinear-evaluation.md), [profile](docs/nonlinear-benchmark.md)
and [A–BI report](docs/AFRE_13_COMPLETION_REPORT.md).

## AFRE-14 temporal sequence research

Causal fixed-count/elapsed windows preserve final availability, deterministic revisions,
exact timestamp-union alignment, masks, padding and irregular time. TRAIN-only population
normalization feeds fixed exponential-decay or stable diagonal state-space aggregates with
an AFRE-5 QR/fixed-ridge linear readout. Actual construction/fit/forecast clocks remain distinct.
Target-free application, compatible law translation, same-origin ranking, actual1h/1d
identities, matched truths, TEST seals, descriptive stability/coverage and bounded unified
lineage are retained. Session windows, recurrent networks and attention are unsupported.
There is no direct external-engine dependency, broad model search or uncertainty decomposition.

[Architecture](docs/temporal-sequence-models.md), [windows](docs/sequence-windows.md),
[masks](docs/sequence-masking.md), [time](docs/sequence-time-encoding.md),
[TRAIN causality](docs/causal-sequence-training.md), [families](docs/sequence-model-families.md),
[sources](docs/external-sequence-integration.md), [evaluation](docs/sequence-evaluation.md),
[profile](docs/sequence-benchmark.md), [A–BT report](docs/AFRE_14_COMPLETION_REPORT.md).
Run `PYTHONPATH=src:. .venv311/bin/python -m examples.sequence_demo` for the 37-step offline demo.

## AFRE-17 completed scope

Historical AFRE-17 checkpoint: engine 0.18.0, invariance/stability schema 1.0,
shared store 1.17/SQLite user_version=18; every earlier public schema remains 1.0.
The roadmap freezes 26 distinct phases, AFRE-0 through AFRE-25.

AFRE-17 adds [declared environment stability](docs/invariance-stability-research.md), exact PIT
memberships, native point/probabilistic/calibration/IC metrics, explicit intersections and
minimum counts, supplied frozen parameter diagnostics, feature-distribution distances and
separate error degradation. Stability != causal invariance proof. No significance or trading
profitability claim, TEST-driven environment selection, auto-refit, auto-prune or promotion.

Run `.venv311/bin/python -m examples.invariance_demo` for the 37-step offline demo and
`.venv311/bin/python -m benchmarks.invariance_profile` for the bounded profile. See the
[A–BW completion report](docs/AFRE_17_COMPLETION_REPORT.md) and [profile](docs/invariance-profile.json).

**Next scope: AFRE-24 — Forecast Snapshot, Registry & Service.**
AFRE-23 explicit champions/challengers, matched shadow evaluation and manual promotion/rollback advice are complete. AFRE-24 snapshot/registry/service remains future scope.
AFRE-22 provides descriptive health; automatic lifecycle actions remain excluded. **Stop after AFRE-23.** Portfolio construction,
risk optimization and execution remain downstream projects after AFRE.
## Historical AFRE-18 completed scope

AFRE-0 through AFRE-18 are complete. Engine 0.19.0, transaction-cost-research schema 1.0,
shared store 1.18/SQLite user_version=19; all earlier schemas remain 1.0 and runtime
dependencies remain empty. The frozen roadmap has 26 distinct phases, AFRE-0 through AFRE-25.

AFRE-18 adds explicit bounded per-security exposure paths, initial policies, absolute-change
turnover, six-clock provider-neutral spread/fee/slippage/impact inputs, historical-causal
and ex-post timing, matched arithmetic gross/cost/net contributions, explicit missing/fallback
policy, embedded-category protection, algebraic break-even and supplied sensitivity grids.
Native forecasts, residual signals, uncertainty metadata, PIT cohorts and actual1h/1d
assessments remain distinct. No execution optimization, fill, capacity, profitability,
portfolio performance, automatic selection or TEST-driven tuning claim is made.

See [cost research](docs/transaction-cost-aware-research.md),
[scenarios](docs/cost-scenarios.md), [exposure rules](docs/research-exposure-rules.md),
[spread/fees/slippage](docs/spread-fee-slippage.md), [impact](docs/market-impact-research.md),
[turnover](docs/turnover-diagnostics.md), [break-even](docs/break-even-cost.md),
[sensitivity](docs/cost-sensitivity.md), [measured profile](docs/costs-profile.json) and
[the A–BS report / 50 gates](docs/AFRE_18_COMPLETION_REPORT.md).
Run `PYTHONPATH=src:. .venv311/bin/python -m examples.costs_demo` for the checked 40-step
offline demo and `PYTHONPATH=src:. .venv311/bin/python -m benchmarks.costs_profile` for the profile.

**Next scope: AFRE-24 — Forecast Snapshot, Registry & Service.**
AFRE-23 explicit champions/challengers, matched shadow evaluation and manual promotion/rollback advice are complete. AFRE-24 snapshot/registry/service remains future scope.
AFRE-22 provides descriptive health; automatic lifecycle actions remain excluded. **Stop after AFRE-23.** Portfolio construction,
risk optimization and execution remain downstream projects after AFRE.

## Historical AFRE-19 completed scope

AFRE-0 through AFRE-19 are complete. Engine 0.20.0; multiple-testing schema 1.0;
shared store 1.19/SQLite user_version=20. Earlier public schemas remain 1.0.
Earlier completed-scope version statements above are historical release checkpoints.

Immutable planned opportunities and their separate completions retain exact source,
hypothesis, target/horizon, fold, environment, cost, preprocessing and inspected-choice
identities. Every frozen family retains failed, unavailable and missing attempts in its
full denominator. Conditional exact sign tests require explicit caller-attested
independence, fair nonzero signs, nonoverlapping native labels and exact pairing.
Bonferroni/Holm control nominal FWER; BH requires independence/PRDS; BY supports
arbitrary dependence of valid marginal p-values. The level and every reported method
are fixed in the family before the held-out boundary. Open, adaptive, unknown and
retrospective analyses carry interpretation limits and make no final discovery claim.

P-value != effect size. Median effects are separate; CI/SE, normal/correlation inference
and Sharpe/generic deflation are unsupported. Corrections do not eliminate data snooping,
leakage, adaptivity or nonstationarity. Significance != causality; significance !=
profitability. Selection events describe caller-supplied outcomes and retain candidate
sets, ordering/ties and TEST involvement. No model selection, promotion, pruning or
automatic follow-up hypotheses occur. Registry snapshots contain all visible registered
opportunities; exact TEST seals, reuse thresholds and untracked native history remain
explicit. New evidence creates new IDs while frozen old results remain byte-identical.

See [controls](docs/multiple-testing-controls.md), [registry](docs/research-trial-registry.md), [families](docs/hypothesis-families.md), [FWER](docs/fwer-controls.md), [FDR](docs/fdr-controls.md), [TEST reuse](docs/test-reuse.md), [selection](docs/selection-bias.md), [overfitting](docs/research-overfitting.md), [profile](docs/multiple-testing-profile.json) and [A–BT report](docs/AFRE_19_COMPLETION_REPORT.md).

**Next scope: AFRE-24 — Forecast Snapshot, Registry & Service.**
AFRE-23 explicit champions/challengers, matched shadow evaluation and manual promotion/rollback advice are complete. AFRE-24 snapshot/registry/service remains future scope.
AFRE-22 provides descriptive health; automatic lifecycle actions remain excluded. **Stop after AFRE-23.** Portfolio construction,
risk optimization and execution remain downstream projects after AFRE.

## AFRE-20 completed boundary

AFRE-20 is the [declared model selection framework](docs/model-selection-framework.md).
Engine 0.21.0; selection schema 1.0; shared store 1.20/SQLite user_version=21;
earlier public schemas remain 1.0 and runtime dependencies remain empty.
TRAIN fits; VALIDATION selects; TEST evaluates only later under native seals and
AFRE-19 reuse accounting. Selection references the immutable TRAIN-fitted model.

Complete bounded Cartesian grids, explicit native recipes, exact request cutoffs,
deterministic fingerprint ties, failure/incompatibility/minimum-support states and
complete candidate registries preserve the inspected opportunity denominator. Native
families AFRE-5/6/10/11/13/14 are integrated. An explicit causal AFRE-16 residual feature
can enter the native nonlinear input; earlier TEST rows cannot become selection rows.
MIN_MSE, MIN_MAE, MAX_R2, Gaussian/empirical CRPS and Gaussian NLL are supported.
IC/rank IC, AFRE-18 cost selection, automatic calibration and AFRE-12 orchestration
are deferred. Native AFRE-19 SelectionEvent is emitted only on exact metric/direction/
ordering compatibility; otherwise the full AFRE-20 decision/trial pool stays explicit.

Frozen snapshots, additive transactional20→21 migration, immutable indexed storage,
source/label correction identities, bounded audits, hash-seed/order/restart replay and
real second-writer regressions preserve old result bytes. There is no hidden adaptive
search, TEST tuning, validation-based early stopping, automatic final refit, ensemble
fusion, model promotion or production deployment. Independent walk-forward/horizon
calls are supported; nested, coupled, random/Bayesian/continuous and partial search
are unsupported. VALIDATION selection does not prove generalization or profitability.

See [spaces](docs/search-spaces.md), [registry](docs/candidate-registry.md),
[validation](docs/validation-selection.md), [budgets](docs/resource-budgets.md),
[families/comparisons](docs/model-family-comparison.md),
[TEST isolation](docs/test-isolation-selection.md),
[reproducibility](docs/selection-reproducibility.md),
[measured profile](docs/selection-profile.json) and
[A–CB report](docs/AFRE_20_COMPLETION_REPORT.md).
Run `PYTHONPATH=src:. .venv311/bin/python -m examples.selection_demo` for 35 verified
steps and `PYTHONPATH=src:. .venv311/bin/python -m benchmarks.selection_profile` for
separate bounded timing/storage measurements. There is no production SLA.

**Next scope: AFRE-24 — Forecast Snapshot, Registry & Service.**
AFRE-23 explicit champions/challengers, matched shadow evaluation and manual promotion/rollback advice are complete. AFRE-24 snapshot/registry/service remains future scope.
AFRE-22 provides descriptive health; automatic lifecycle actions remain excluded. **Stop after AFRE-23.** Portfolio construction,
risk optimization and execution remain downstream projects after AFRE.

## AFRE-21 completed scope

Engine 0.22.0; fusion schema 1.0; shared store 1.21/SQLite user_version=22; earlier public schemas remain 1.0; Python 3.11+; zero runtime dependencies.

Immutable source references, predeclared fixed point/signal/probability rules and TRAIN-only unconstrained QR weights produce separate frozen fusion artifacts. Application is target-free. Exact Gaussian/empirical mixtures preserve their laws; no averaged quantiles, Gaussian collapse or invented joint distribution. Missingness and contribution reconstruction are explicit. Prediction diversity stays separate from forecast quality. Every inspected fusion rule counts under AFRE-19. AFRE-20 owns candidate selection; its optional fusion-candidate adapter and stacking are unsupported. There is no hidden source selection or TEST tuning. Actual native source families, AFRE-16 residuals, separate AFRE-15/17 metadata, AFRE-18 cost evaluation, 1h/1d independence, corrections, replay, migration and corruption checks are included.

See [fusion guide](docs/ensemble-signal-fusion.md), [evaluation](docs/fusion-evaluation.md), [profile](docs/fusion-profile.json) and [A–CR completion report](docs/AFRE_21_COMPLETION_REPORT.md).

**Stop after AFRE-23.**

**Next scope: AFRE-24 — Forecast Snapshot, Registry & Service.** Future work covers the final immutable snapshot, provider-neutral registry and service facade. No automatic production replacement is implied. AFRE-23 owns champion/challenger evaluation, AFRE-24 the final forecast service boundary and AFRE-25 final integration/hardening. Portfolio construction, risk optimization and execution remain downstream. No AFRE phase establishes trading profitability merely from predictive metrics.

## AFRE-22 completed scope

Engine 0.23.0; health schema 1.0; shared store 1.22/SQLite user_version=23; all earlier public schemas remain 1.0; Python 3.11+; zero runtime dependencies.

[Drift, decay and model health](docs/drift-decay-model-health.md) pins frozen monitored artifacts, explicit windows/rules, target-free input/prediction drift and later-cutoff errors/calibration. Drift != failure; input drift != error degradation. Health is descriptive: no retrain, recalibrate, weight changes, replacement, promotion, retirement, routing or notifications. No causal explanation, health probability or profitability claim follows. Immutable histories, fixed-reference trends, native AFRE-17 environments and AFRE-19/20/21 context retain exact identities and availability. See [A–CB completion report](docs/AFRE_22_COMPLETION_REPORT.md), [rules](docs/health-rules.md) and [snapshots](docs/health-snapshots.md).

**Stop after AFRE-23.**

**Next scope: AFRE-24 — Forecast Snapshot, Registry & Service.** Future scope: final immutable forecast snapshots, exact registry/version exposure and reproducible provider-neutral retrieval. No automatic deployment or production service. AFRE-24 remains the final forecast service boundary and AFRE-25 final integration/hardening. Portfolio construction, risk optimization and execution remain downstream.

## AFRE-23 completed scope

Engine 0.24.0; champion/challenger schema 1.0; shared store 1.23 / SQLite user_version=24. Earlier public schemas remain 1.0; Python 3.11+; zero runtime dependencies.

[Champion/challenger research](docs/champion-challenger.md) freezes explicit participant roles, programs/windows/criteria, target-free native shadow records and one common matched truth support. Point, native probabilistic and same-origin ranking metrics produce independent challenger comparisons. Promotion/rollback assessments are MANUAL_ONLY; no global winner, deployment, retraining, recalibration or weight changes. Native AFRE-18 costs, AFRE-19 research/TEST history, AFRE-20 provenance, AFRE-21 fusion and AFRE-22 health remain separate exact context. Corrections append new immutable runs. See [audit](docs/challenge-audit.md), [context](docs/challenge-health-cost-context.md), [A–CR completion report](docs/AFRE_23_COMPLETION_REPORT.md) and [measured profile](docs/challenge-profile.json).

**Stop after AFRE-23.**

**Next scope: AFRE-24 — Forecast Snapshot, Registry & Service.** Final immutable forecast snapshot; public provider-neutral AFRE API; artifact/model registry; exact versions/schemas; point/probability/calibration/horizon/ranking/context outputs; stable service facade; snapshot publication; reproducible retrieval; health/champion metadata. No execution or portfolio optimization. AFRE-25 remains final integration/hardening. The roadmap freezes 26 distinct phases, AFRE-0 through AFRE-25; portfolio construction, risk optimization and execution remain downstream. Predictive metrics do not establish trading profitability.

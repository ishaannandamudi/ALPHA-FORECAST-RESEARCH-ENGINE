# Alpha Forecast & Research Engine (AFRE)

AFRE is a point-in-time quantitative research foundation. Its eventual output is
a calibrated multi-horizon return distribution with uncertainty, feature/model
lineage and honest out-of-sample evidence. **AFRE-0 through AFRE-13 are complete.**
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

Python **3.11+**; engine **0.14.0**; foundation, feature-store, target, universe,
dataset, model, probabilistic, calibration, multi-horizon, cross-sectional, event-conditioned, regime-conditioned, mixture and nonlinear schemas **1.0**;
shared nonlinear store **1.13**, `user_version=14` (additive to store1.12/user_version13). Runtime uses only the
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

**Next scope: AFRE-14 — Temporal / Sequence Models.** Ordered historical feature
sequences, causal masking/lookbacks, missing sequence observations, sequence lengths,
time encoding, training-only transforms, horizon-specific outputs and supplied
event/regime/microstructure sequences. Appropriate recurrent/state-space/attention
research models belong to AFRE-14; uncertainty decomposition remains AFRE-15.
**Stop after AFRE-13.** AFRE-14 remains deferred. Downstream HFT integration supplies
real provider adapters. Predictive metrics do not establish profitability. Portfolio
construction, risk optimization and execution remain downstream projects after AFRE.

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

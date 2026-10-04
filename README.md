# Alpha Forecast & Research Engine (AFRE)

AFRE is a point-in-time quantitative research foundation. Its eventual output is
a calibrated multi-horizon return distribution with uncertainty, feature/model
lineage and honest out-of-sample evidence. **This repository completes AFRE-0
only.** It contains no predictive model fitting, feature store, portfolio sizing,
orders or execution.

Python **3.11+**; engine **0.1.0**; foundation and SQLite schemas **1.0**. The runtime
uses only the standard library.

The architecture consists of immutable typed contracts, pure validation,
deterministic JSON/domain-separated SHA-256 identity, provider protocols and an
append-only transactional SQLite artifact registry. Every feature must satisfy
`available_time <= origin availability cutoff <= forecast origin`. Every training
label must be completed and available at fit cutoff. Effective time and knowledge
time remain separate. Stable security IDs and historical membership replace ticker
identity and current-constituent reconstruction.

EIE is an external upstream system via its final provider-neutral snapshot
boundary. MCE, options and AME are optional future providers. No sibling repository
is imported or modified; no upstream SQLite schema is assumed.

## Quickstart

```sh
python3.11 -m venv .venv311
.venv311/bin/python -m pip install -e '.[dev]'
.venv311/bin/python examples/foundation_demo.py
```

For a checkout without editable installation, use:

```sh
PYTHONPATH=src .venv311/bin/python examples/foundation_demo.py
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

## Quality gates

Every pytest test blocks sockets and DNS, including the deterministic subprocess
checks. The Python package performs no networking or shell execution.

```sh
.venv311/bin/python -m pytest --cov=afre --cov-branch --cov-report=term-missing
.venv311/bin/ruff check .
.venv311/bin/ruff format --check .
.venv311/bin/mypy
.venv311/bin/python scripts/check_repository.py
PYTHONPATH=src:. .venv311/bin/python benchmarks/foundation.py
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
The frozen advanced roadmap has **26 distinct phases, AFRE-0 through AFRE-25**.
Transaction-cost-aware research evaluation (AFRE-18), multiple-testing/overfitting
controls (AFRE-19), model selection (AFRE-20), ensembles (AFRE-21), drift/decay
(AFRE-22) and champion/challenger shadow evaluation (AFRE-23) remain separate.
AFRE-24 is the final forecast snapshot, registry and service boundary; AFRE-25 is
final integration, hardening and research audit. Portfolio construction, risk
optimization and execution remain downstream projects after AFRE. Predictive
metrics alone do not establish trading profitability.
The [completion report](docs/AFRE_0_COMPLETION_REPORT.md) records gates and limits.

**Next scope: AFRE-1, point-in-time feature store.** It will add immutable feature
vintages, a registry/computation DAG, point-in-time joins, stale/missing handling,
market/EIE features, optional neutral adapters, materialization, training/serving
parity, normalization lineage, leakage audits and efficient historical batches.
Label construction starts at AFRE-2; actual predictive baselines start at AFRE-5.

Contracts establish declared provenance and invariants. They cannot authenticate
an upstream timestamp or detect a scalar secretly derived from future target data.
Provider audits remain necessary. Split metadata does not execute purging, and
model metadata does not constitute trained or calibrated forecasts.

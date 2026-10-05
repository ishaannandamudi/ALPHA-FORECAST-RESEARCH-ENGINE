# Point-in-Time Feature Store (AFRE-1)

AFRE-1 answers which exact immutable feature vintage was usable for a stable
security at an explicit forecast origin. Engine 0.2.0 retains foundation schema
1.0, adds feature-store schema 1.0 and an additive SQLite store 1.1 migration.
AFRE-0 contract semantics and tests remain intact.

`FeatureStore` composes `FeatureRegistry`, `FeatureStoreRepository` and one indexed
selection function. `feature_as_of`, `features_as_of`, `point_in_time_join` and
`materialize` all use that function. An audit identifies the selected vintage,
its full clocks, source, state, freshness, query policy and scope mapping.
`feature_history`, `lineage` and `audit` expose history and deeper validation.

Definitions, feature sets, source references, vintages, scope bindings,
computation graphs/specifications/receipts, supplied normalization artifacts and
materializations are immutable data artifacts. They use the existing canonical
JSON envelope and domain-separated fingerprints with separate `fs_*` domains.
Source records require an explicit caller-owned writer transaction. Computation
and materialization manage their own transactions; reads pin a SQLite snapshot.

The package is divided into `schema`, `models`, `freshness`, `registry`, `dag`,
`computation`, `normalization`, `providers`, `queries`, `materialization`,
`repository` and `engine`. Transformation implementations are a static enum
registry. No provider payload selects code, paths, imports or shell commands.
Runtime dependencies remain empty; tests block sockets and DNS.

## Causal selection

For each requested definition/entity, selection chooses the latest admissible
final availability at or before the origin cutoff. Equality remains admissible.
LAST_OBSERVATION also requires effective time at or before origin; INTERVAL
requires origin inside [effective, valid_until); KNOWN_FACT permits an explicitly
known scheduled fact whose effective time is later. Equal-time incompatible
vintages raise `VintageConflict` unless a predecessor chain establishes a unique
winner. Arrival order and fingerprint ordering never choose a conflicting value.

A newly appended correction preserves older rows. A newly qualified historical
reconstruction can change a fresh historical query; it cannot mutate a previously
frozen materialization. Freeze the exact artifact for reproducible research.
Historical causality and literal historical operation are different claims.

## Integration and limits

Feature rows project into unchanged AFRE-0 `FeatureValue` and
`ForecastFeatureRow` contracts. The projection pins the complete AFRE-1 vintage
fingerprint, including physical delivery clocks, and includes freshness/query
policy identity. Stale values remain in audits while their AFRE-0 projections
withhold the numeric value. Query absence never reveals a future vintage.

Direct target/result namespaces are excluded and typed dependencies accept only
feature vintages. Append/computation validation and deep audits traverse source
parents, inputs, revisions and normalization fit samples. Opaque provider bytes
can still contain falsely described information: references establish consistency,
not external authenticity. Historical delivery attestors require explicit local
approval; no automatic trust is granted by a provider timestamp.

Scope broadcasts require explicit historical `ScopeBinding` evidence. Supported
scopes are SECURITY, ISSUER, SECTOR, MARKET and MACRO. Cross-scope computation is
rejected. Source datasets, adjustment identity, calendar, build context and
historical universe must agree, or a dataset compatibility policy must explicitly
name additional sources. Stable IDs are used throughout; tickers are metadata.

See [vintages](feature-vintages.md), [DAG computation](feature-computation-dag.md),
[joins](point-in-time-joins.md) and [normalization](feature-normalization.md).
The offline walkthrough is `examples/feature_store_demo.py`; the measured local
workload is `benchmarks/feature_store.py`. No real upstream integration, learned
normalization fitting, label engine, predictive model or forecast service is
implemented by AFRE-1. AFRE-2 now supplies the separate
[target engine](forecast-targets.md); it preserves this feature-store boundary.
AFRE-3 supplies [historical universes](point-in-time-universes.md). AFRE-4 now
uses this exact PIT join and retains selected vintages in frozen research samples.
It fits simple TRAIN-only normalization through the existing AFRE-1 state contracts;
raw historical feature availability remains unchanged. See [datasets](research-datasets.md)
and [fold preprocessing](fold-local-preprocessing.md).

## AFRE-10 integration

EventReference and event attributes reuse the existing six-clock evidence unchanged. Occurrence/publication never bypass receipt/final availability. Qualified delivery preserves later reconstruction clocks and binds exact source/security plus approved attestor.
See [event-conditioned forecasting](event-conditioned-forecasting.md).

## AFRE-11 composition boundary

[Regime conditioning](regime-conditioned-forecasting.md) consumes exact causal
filtered hard/soft state evidence without changing this phase's contracts. As-of
is distinct from all six availability clocks. TRAIN state means/fitted-residual
offsets, fixed soft weighting and explicit fallback are horizon-specific. Application
preserves exact base bytes and reads no truth. Matched evaluation/ranking retains
PIT scope and TEST controls. Global calibration cannot silently transfer, and
descriptive regime drift never refits. MCE/AME remain external neutral data producers;
downstream HFT integration supplies adapters. Predictive metrics do not prove profitability.

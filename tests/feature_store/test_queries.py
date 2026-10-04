from dataclasses import replace

import pytest

from afre.feature_store import FeatureSetManifest, FeatureStore, ScopeBinding
from afre.feature_store.freshness import FreshnessBasis, FreshnessPolicy
from afre.feature_store.queries import VintageConflict
from afre.feature_store.schema import QueryBounds, QueryPolicy, StoreScope, ValidityRule
from afre.features import FeatureScope, MissingState
from afre.ids import InstrumentId
from afre.schema import ContractError
from afre.serialization import canonical_json
from afre.time import TimeRange
from examples.feature_store_demo import (
    SECURITY,
    SOURCE,
    clocks,
    dataset,
    definition,
    origin,
    source_vintage,
)


def append(store: FeatureStore, *values: object) -> None:
    from afre.schema import ensure_artifact

    with store.repository.transaction():
        for value in values:
            store.repository.put(ensure_artifact(value))


def test_future_same_time_revision_and_history(store: FeatureStore) -> None:
    feature = definition()
    old = source_vintage(feature, 5, 9, 10.0)
    revised = replace(old, clocks=clocks(11), value=11.0, predecessor_id=old.fingerprint)
    append(store, old, revised)
    assert store.feature_as_of(feature, origin(8)).selected is None
    assert store.feature_as_of(feature, origin(9)).selected == old
    assert store.feature_as_of(feature, origin(10)).selected == old
    assert store.feature_as_of(feature, origin(11)).selected == revised
    assert store.feature_history(feature, SECURITY, 10) == (old,)
    assert store.feature_history(feature, SECURITY, 11) == (old, revised)
    assert store.registry.get(feature.fingerprint) == feature


def test_equal_time_conflict_and_explicit_precedence(store: FeatureStore) -> None:
    feature = definition()
    old = source_vintage(feature, 5, 9, 10.0)
    conflicting = replace(old, value=11.0)
    append(store, conflicting, old)
    with pytest.raises(VintageConflict):
        store.feature_as_of(feature, origin(9))
    # Explicit predecessor precedence resolves a tie; no insertion ordering is used.
    other = replace(feature, definition=replace(feature.definition, name="market.other"))
    base = replace(old, feature=other)
    update = replace(base, value=11.0, predecessor_id=base.fingerprint)
    append(store, other, base, update)
    assert store.feature_as_of(other, origin(9)).selected == update
    store.repository.bounds = replace(store.repository.bounds, candidates=1)
    with pytest.raises(ContractError, match="tie bound"):
        store.feature_as_of(other, origin(9))


def test_validity_known_fact_and_staleness(store: FeatureStore) -> None:
    base = definition()
    interval = replace(
        base,
        definition=replace(base.definition, name="market.interval"),
        validity_rule=ValidityRule.INTERVAL,
    )
    value = replace(source_vintage(base, 5, 5), feature=interval, valid_until_ns=10)
    append(store, interval, value)
    assert store.feature_as_of(interval, origin(9)).selected == value
    assert store.feature_as_of(interval, origin(10)).selected is None
    scheduled = replace(
        base,
        definition=replace(base.definition, name="market.scheduled"),
        validity_rule=ValidityRule.KNOWN_FACT,
    )
    future_effective = source_vintage(scheduled, 20, 5)
    append(store, scheduled, future_effective)
    assert store.feature_as_of(scheduled, origin(6)).selected == future_effective
    for basis in (FreshnessBasis.EFFECTIVE_TIME, FreshnessBasis.SOURCE_AVAILABILITY):
        stale = replace(
            base,
            definition=replace(base.definition, name=f"market.{basis.value}"),
            freshness=FreshnessPolicy(basis, 5),
        )
        value = replace(
            source_vintage(stale, 1, 2), clocks=replace(clocks(2), upstream_available_ns=1)
        )
        append(store, stale, value)
        assert store.feature_as_of(stale, origin(6)).state is MissingState.PRESENT
        audit = store.feature_as_of(stale, origin(7))
        assert audit.state is MissingState.STALE and audit.selected is not None
        assert (
            audit.selected.value == 100.0
        )  # value retained, freshness qualification separate.
        row = store.point_in_time_join(
            (origin(7),), dataset(FeatureSetManifest((stale,))), FeatureSetManifest((stale,))
        )[0].row
        assert (
            row.features[0].value is None
            and row.features[0].missing_state is MissingState.STALE
        )
    with pytest.raises(ContractError):
        FreshnessPolicy(FreshnessBasis.NEVER, 1)
    with pytest.raises(ContractError):
        replace(value, valid_until_ns=value.effective_ns)


def test_missing_and_serving_batch_parity(store: FeatureStore) -> None:
    feature = definition()
    features = FeatureSetManifest((feature,))
    missing = store.feature_as_of(feature, origin(10))
    assert missing.state is MissingState.MISSING
    empty_row = store.point_in_time_join((origin(10),), dataset(features), features)[0]
    assert empty_row.row.features[0].value is None
    value = source_vintage(feature, 5, 9, 0.0)
    append(store, value)
    serving = store.features_as_of(features, origin(10))[0]
    joined = store.point_in_time_join((origin(10), origin(11)), dataset(features), features)
    assert joined[0].audits == (serving,)
    assert canonical_json(joined[0].audits[0]) == canonical_json(serving)
    assert joined[0].row.features[0].value == 0.0
    frozen = store.materialize((origin(10),), dataset(features), features, 11)
    revised = replace(value, clocks=clocks(12), value=4.0, predecessor_id=value.fingerprint)
    append(store, revised)
    assert store.repository.get(type(frozen), frozen.fingerprint) == frozen


@pytest.mark.parametrize(
    "scope", [StoreScope.ISSUER, StoreScope.SECTOR, StoreScope.MARKET, StoreScope.MACRO]
)
def test_explicit_scope_mapping_no_accidental_broadcast(
    store: FeatureStore, scope: StoreScope
) -> None:
    feature = replace(
        definition(),
        definition=replace(
            definition().definition, name=f"market.{scope.value}", scope=FeatureScope.ENTITY
        ),
        scope=scope,
    )
    entity = InstrumentId(scope.value, "entity1")
    value = source_vintage(feature, 1, 2, entity=entity)
    append(store, feature, value)
    assert store.feature_as_of(feature, origin(3)).state is MissingState.NOT_APPLICABLE
    binding = ScopeBinding(scope, entity, SECURITY, TimeRange(0, 10), 2, SOURCE.provenance)
    append(store, binding)
    assert store.feature_as_of(feature, origin(3)).selected == value
    assert store.feature_as_of(feature, origin(1)).selected is None
    assert store.feature_as_of(feature, origin(10)).state is MissingState.NOT_APPLICABLE
    assert (
        store.feature_as_of(feature, origin(3, InstrumentId("security", "unrelated"))).selected
        is None
    )
    alternative = replace(binding, entity=InstrumentId(scope.value, "entity2"))
    append(store, alternative)
    with pytest.raises(VintageConflict):
        store.feature_as_of(feature, origin(3))
    store.repository.bounds = replace(store.repository.bounds, candidates=1)
    with pytest.raises(ContractError, match="scope candidate"):
        store.feature_as_of(feature, origin(3))


def test_join_context_and_explicit_cross_dataset_policy(store: FeatureStore) -> None:
    feature = definition()
    features = FeatureSetManifest((feature,))
    manifest = dataset(features)
    with pytest.raises(ContractError):
        store.feature_as_of(feature, replace(origin(10), build_context="other"))
    with pytest.raises(ContractError):
        store.point_in_time_join(
            (origin(10),), replace(manifest, calendar_id="other"), features
        )
    with pytest.raises(ContractError):
        store.point_in_time_join(
            (origin(10),),
            replace(manifest, source_dataset_ids=(SECURITY.fingerprint,)),
            features,
        )
    approved = FeatureStore(
        store.repository, QueryPolicy(compatible_dataset_ids=(feature.source_dataset_ids[0],))
    )
    approved.point_in_time_join(
        (origin(10),), replace(manifest, source_dataset_ids=(SECURITY.fingerprint,)), features
    )
    other = replace(feature, definition=replace(feature.definition, name="market.other"))
    with pytest.raises(ContractError):
        store.point_in_time_join((origin(10),), manifest, FeatureSetManifest((other,)))


@pytest.mark.parametrize(
    "bounds",
    [
        QueryBounds(origins=1),
        QueryBounds(instruments=1),
        QueryBounds(cells=1),
        QueryBounds(serialized_bytes=1),
    ],
)
def test_join_bounds(store: FeatureStore, bounds: QueryBounds) -> None:
    feature = definition()
    features = FeatureSetManifest((feature,))
    store.repository.bounds = bounds
    origins = (origin(10), origin(11, InstrumentId("security", "other")))
    with pytest.raises(ContractError):
        store.point_in_time_join(origins, dataset(features), features)


def test_history_and_feature_bounds(store: FeatureStore) -> None:
    feature = definition()
    append(store, source_vintage(feature, 1, 2), source_vintage(feature, 3, 4))
    store.repository.bounds = replace(store.repository.bounds, history=1)
    with pytest.raises(ContractError):
        store.feature_history(feature, SECURITY, 5)
    store.repository.bounds = replace(store.repository.bounds, history=5, serialized_bytes=1)
    with pytest.raises(ContractError):
        store.feature_history(feature, SECURITY, 5)
    with pytest.raises(ContractError):
        store.features_as_of(FeatureSetManifest((feature,)), origin(0))
    store.repository.bounds = QueryBounds(features=1)
    other = replace(feature, definition=replace(feature.definition, name="market.other"))
    with pytest.raises(ContractError):
        store.features_as_of(FeatureSetManifest((feature, other)), origin(5))
    with pytest.raises(ContractError):
        QueryBounds(cells=0)

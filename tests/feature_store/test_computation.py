from dataclasses import replace
from typing import Any

import pytest

from afre.feature_store import (
    FeatureComputationGraph,
    FeatureSetManifest,
    FeatureStore,
    NormalizationSpec,
    NormalizationState,
)
from afre.feature_store.computation import transform
from afre.feature_store.dag import MissingInputPolicy, Transformation, WindowBasis
from afre.feature_store.normalization import NormalizationMethod
from afre.feature_store.queries import window_history
from afre.feature_store.schema import StoreScope
from afre.features import FeatureScope, MissingState
from afre.lineage import Parameter
from afre.schema import ContractError
from examples.feature_store_demo import (
    INPUT_ID,
    SECURITY,
    clocks,
    computation,
    dataset,
    definition,
    origin,
    source_vintage,
)
from tests.feature_store.test_queries import append


@pytest.mark.parametrize(
    "kind,expected",
    [
        (Transformation.PERCENT_CHANGE, 0.2),
        (Transformation.LOG_RETURN, 0.1823215567939549),
        (Transformation.ROLLING_MEAN, 110.0),
        (Transformation.ROLLING_STDDEV, 10.0),
    ],
)
def test_rolling_computation_availability_receipt_and_revision(
    store: FeatureStore, kind: Transformation, expected: float
) -> None:
    raw = definition()
    unit = (
        "ratio"
        if kind in (Transformation.PERCENT_CHANGE, Transformation.LOG_RETURN)
        else "currency"
    )
    output = definition(f"market.{kind.value}", unit, (raw,), lookback_ns=10)
    values = (
        source_vintage(raw, 1, 2, 100.0),
        source_vintage(raw, 3, 4, 110.0),
        source_vintage(raw, 5, 6, 120.0),
    )
    future = source_vintage(raw, 7, 20, 900.0)
    append(store, output, *values, future)
    spec = computation(output, (raw,), kind, 2, WindowBasis.ELAPSED_LOOKBACK)
    result, receipt = store.compute(spec, origin(8), clocks(9))
    assert isinstance(result.value, (int, float))
    assert float(result.value) == pytest.approx(expected)
    assert result.clocks.final_available_ns == 9
    assert receipt.input_ids == tuple(sorted(item.fingerprint for item in values))
    assert future.fingerprint not in receipt.input_ids
    assert store.feature_as_of(output, origin(8)).selected is None
    assert store.feature_as_of(output, origin(9)).selected == result
    lineage = store.lineage(result.fingerprint)
    assert receipt in lineage and all(item in lineage for item in values)
    store.audit()
    revised = replace(
        values[1], clocks=clocks(11), value=800.0, predecessor_id=values[1].fingerprint
    )
    append(store, revised)
    assert store.repository.get(type(result), result.fingerprint) == result
    newer, _ = store.compute(spec, origin(12), clocks(12))
    assert newer.fingerprint != result.fingerprint
    with pytest.raises(ContractError):
        store.compute(spec, origin(8), clocks(5))


def test_unary_binary_and_missing_computation(store: FeatureStore) -> None:
    raw = definition()
    other = definition("market.other")
    identity = definition("market.identity", "currency", (raw,))
    difference = definition("market.difference", "currency", (raw, other))
    append(
        store,
        other,
        identity,
        difference,
        source_vintage(raw, 1, 2, 100.0),
        source_vintage(other, 1, 2, 90.0),
    )
    for spec, expected in (
        (computation(identity, (raw,), Transformation.IDENTITY), 100.0),
        (computation(difference, (raw, other), Transformation.DIFFERENCE, 2), 10.0),
    ):
        value, _ = store.compute(spec, origin(3), clocks(3))
        assert value.value == expected
    empty = definition("market.empty")
    propagated = definition("market.propagated", "currency", (empty,))
    append(store, empty, propagated)
    rejecting = computation(propagated, (empty,), Transformation.IDENTITY)
    with pytest.raises(ContractError):
        store.compute(rejecting, origin(3), clocks(3))
    spec = replace(rejecting, missing_input_policy=MissingInputPolicy.PROPAGATE)
    missing, _ = store.compute(spec, origin(3), clocks(3))
    assert missing.value is None and missing.state is MissingState.MISSING
    features = FeatureSetManifest((propagated,))
    joined = store.point_in_time_join((origin(2),), dataset(features), features)[0]
    assert joined.row.features[0].missing_state is MissingState.MISSING
    with pytest.raises(ContractError):
        store.append_vintage(missing)
    with pytest.raises(ContractError):
        store.compute(replace(spec, implementation_version="untrusted"), origin(3), clocks(3))
    with pytest.raises(ContractError):
        store.compute(spec, replace(origin(3), build_context="other"), clocks(3))


def test_normalization_state_cutoff_identity_and_lineage(store: FeatureStore) -> None:
    raw = definition()
    raw_value = source_vintage(raw, 1, 2, 100.0)
    normalized = definition("market.normalized", "ratio", (raw,))
    append(store, raw_value, normalized)
    spec = NormalizationSpec(raw, NormalizationMethod.STANDARDIZE, "supplied-v1")
    state = NormalizationState(
        spec,
        (raw_value.fingerprint,),
        3,
        4,
        (Parameter("mean", 90.0), Parameter("stddev", 5.0)),
        INPUT_ID,
    )
    append(store, spec, state)
    compute_spec = computation(
        normalized, (raw,), Transformation.STANDARDIZE, normalization_state_id=state.fingerprint
    )
    with pytest.raises(ContractError, match="future normalization"):
        store.compute(compute_spec, origin(3), clocks(3))
    output, _ = store.compute(compute_spec, origin(5), clocks(6))
    assert output.value == 2.0 and output.normalization_state_id == state.fingerprint
    assert state in store.lineage(output.fingerprint)
    newer = replace(state, parameters=(Parameter("mean", 95.0), Parameter("stddev", 5.0)))
    append(store, newer)
    changed, _ = store.compute(
        replace(compute_spec, normalization_state_id=newer.fingerprint), origin(5), clocks(6)
    )
    assert changed.value == 1.0 and changed.fingerprint != output.fingerprint
    for invalid in (
        {"available_ns": 2},
        {"fit_sample_ids": ()},
        {"parameters": (Parameter("mean", 0.0), Parameter("stddev", 0.0))},
        {"parameters": (Parameter("mean", "x"), Parameter("stddev", 1.0))},
        {"parameters": (Parameter("stddev", 1.0),)},
        {"source_dataset_id": SECURITY.fingerprint},
    ):
        with pytest.raises(ContractError):
            replace(state, **invalid)
    late = source_vintage(raw, 6, 7)
    append(store, late)
    with pytest.raises(ContractError), store.repository.transaction():
        store.repository.put(replace(state, fit_sample_ids=(late.fingerprint,)))
    for method in NormalizationMethod:
        if method is NormalizationMethod.STANDARDIZE:
            continue
        other_spec = replace(spec, method=method)
        other = replace(
            state,
            spec=other_spec,
            parameters=()
            if method is NormalizationMethod.NONE
            else (Parameter("supplied_metadata", 1.0),),
        )
        append(store, other_spec, other)
        assert other.spec.method is method
        with pytest.raises(ContractError):
            transform(Transformation.STANDARDIZE, (100.0,), other)
    with pytest.raises(ContractError):
        replace(state, spec=replace(spec, method=NormalizationMethod.NONE))
    with pytest.raises(ContractError):
        replace(state, spec=replace(spec, method=NormalizationMethod.RANK), parameters=())


def test_dag_unknown_edges_and_order(store: FeatureStore) -> None:
    raw = definition()
    derived = definition("market.derived", "currency", (raw,))
    graph = FeatureComputationGraph((derived, raw))
    assert graph.topological_order() == (raw.fingerprint, derived.fingerprint)
    assert graph.fingerprint == FeatureComputationGraph((raw, derived)).fingerprint
    for nodes in ((), (derived,), (raw, raw)):
        with pytest.raises(ContractError):
            FeatureComputationGraph(nodes)
    issuer = replace(
        raw,
        definition=replace(raw.definition, scope=FeatureScope.ENTITY),
        scope=StoreScope.ISSUER,
    )
    with pytest.raises(ContractError):
        FeatureComputationGraph((issuer, derived))
    from afre.feature_store.freshness import FreshnessBasis, FreshnessPolicy

    same_core = replace(raw, freshness=FreshnessPolicy(FreshnessBasis.EFFECTIVE_TIME, 1))
    with pytest.raises(ContractError, match="duplicate foundation"):
        FeatureComputationGraph((raw, same_core))


def test_cycle_self_and_duplicate_dag_edges(monkeypatch: pytest.MonkeyPatch) -> None:
    from afre.features import FeatureDefinition

    keys = {
        name: "afre.feature_definition:1.0:" + digit * 64
        for name, digit in (("market.a", "a"), ("market.b", "b"), ("market.c", "c"))
    }
    # A corrupted persisted index can claim these IDs; validate its cyclic adjacency directly.
    monkeypatch.setattr(
        FeatureDefinition, "fingerprint", property(lambda self: keys[self.name])
    )
    nodes = []
    for name, dependency in (
        ("market.a", "market.b"),
        ("market.b", "market.c"),
        ("market.c", "market.a"),
    ):
        source = definition(name)
        from afre.features import AvailabilityRule

        node = replace(
            source,
            definition=replace(
                source.definition,
                availability_rule=AvailabilityRule.COMPUTED,
                dependency_ids=(keys[dependency],),
            ),
        )
        nodes.append(node)
    with pytest.raises(ContractError, match="cycle"):
        FeatureComputationGraph(tuple(nodes))
    self_node = replace(
        nodes[0], definition=replace(nodes[0].definition, dependency_ids=(keys["market.a"],))
    )
    with pytest.raises(ContractError, match="self"):
        FeatureComputationGraph((self_node,))
    with pytest.raises(ContractError):
        replace(nodes[0].definition, dependency_ids=(keys["market.b"],) * 2)


@pytest.mark.parametrize(
    "changes",
    [
        {"minimum_observations": 0},
        {"observation_count": 2},
        {"parameters": (Parameter("x", 1),)},
        {"transformation_version": "other"},
        {"normalization_state_id": "bad"},
        {"transformation": "eval"},
    ],
)
def test_computation_spec_validation(changes: dict[str, Any]) -> None:
    raw = definition()
    output = definition("market.derived", "currency", (raw,))
    with pytest.raises(ContractError):
        replace(computation(output, (raw,), Transformation.IDENTITY), **changes)


def test_count_window_and_missing_history(store: FeatureStore) -> None:
    raw = definition()
    output = definition("market.count_mean", "currency", (raw,), lookback_ns=10)
    append(store, output, source_vintage(raw, 1, 2, 1.0), source_vintage(raw, 3, 4, 3.0))
    spec = replace(
        computation(
            output, (raw,), Transformation.ROLLING_MEAN, 1, WindowBasis.ELAPSED_LOOKBACK
        ),
        window_basis=WindowBasis.OBSERVATION_COUNT,
        observation_count=1,
    )
    value, _ = store.compute(spec, origin(5), clocks(5))
    assert value.value == 3.0
    assert (
        window_history(store.repository, raw, SECURITY, origin(5), 3, None, store.policy)[
            0
        ].effective_ns
        == 3
    )
    for invalid in ({"observation_count": 0}, {"observation_count": None}):
        with pytest.raises(ContractError):
            replace(spec, **invalid)
    missing = replace(source_vintage(raw, 4, 5), value=None, state=MissingState.INVALID)
    append(store, missing)
    with pytest.raises(ContractError):
        store.compute(replace(spec, observation_count=3), origin(6), clocks(6))
    with pytest.raises(ContractError):
        replace(
            spec, output=replace(output, definition=replace(output.definition, lookback_ns=0))
        )


@pytest.mark.parametrize(
    "kind,values",
    [
        (Transformation.IDENTITY, (1.0, 2.0)),
        (Transformation.DIFFERENCE, (1.0,)),
        (Transformation.PERCENT_CHANGE, (0.0, 1.0)),
        (Transformation.LOG_RETURN, (-1.0, 1.0)),
        (Transformation.ROLLING_MEAN, ()),
        (Transformation.ROLLING_STDDEV, (1.0,)),
        (Transformation.DIFFERENCE, (True, 1.0)),
    ],
)
def test_static_transform_errors(kind: Transformation, values: tuple[Any, ...]) -> None:
    with pytest.raises(ContractError):
        transform(kind, values)

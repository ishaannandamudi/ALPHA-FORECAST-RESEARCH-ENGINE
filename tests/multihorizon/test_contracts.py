"""Exact typed identities, explicit sharing and finite supplied numerical policy."""

from dataclasses import replace

import pytest

from afre.horizons import ForecastHorizon, HorizonBasis
from afre.multihorizon import (
    Architecture,
    ComponentState,
    HorizonOrder,
    HorizonSet,
    MultiHorizonBounds,
    ParameterOwnership,
    ParameterSharing,
    sharing_for,
)
from afre.schema import ContractError
from afre.serialization import canonical_json, deserialize
from examples.multihorizon_demo import backbone_spec
from tests.multihorizon.conftest import Case


def test_horizon_order_and_roundtrip(case: Case) -> None:
    horizons = case.fixture.spec.horizon_set
    assert HorizonSet(tuple(reversed(horizons.targets))) == horizons
    assert [h.duration_ns for h in horizons.horizons] == [5, 15]
    assert deserialize(canonical_json(horizons)) == horizons
    assert horizons.target_for(horizons.horizons[0]) == horizons.targets[0]
    with pytest.raises(KeyError):
        horizons.target_for(ForecastHorizon(HorizonBasis.ELAPSED_TIME, duration_ns=99))
    with pytest.raises(ContractError, match="duplicate semantic"):
        HorizonSet((horizons.targets[0], replace(horizons.targets[0], name="target.alias")))


@pytest.mark.parametrize("basis", [HorizonBasis.TRADING_SESSIONS, HorizonBasis.BARS])
def test_mixed_horizon_order_is_explicit(case: Case, basis: HorizonBasis) -> None:
    t = case.fixture.spec.horizon_set.targets[0]
    h = ForecastHorizon(
        basis,
        count=1,
        calendar_id=t.calendar_id,
        bar_definition=t.bar_definition if basis is HorizonBasis.BARS else None,
    )
    second = replace(t, name="target.session", horizon=h)
    with pytest.raises(ContractError, match="incomparable"):
        HorizonSet((t, second))
    explicit = HorizonSet((second, t), HorizonOrder.EXPLICIT_CANONICAL)
    assert explicit.targets == (second, t)
    assert explicit != HorizonSet((t, second), HorizonOrder.EXPLICIT_CANONICAL)
    counts = HorizonSet((replace(second, horizon=replace(h, count=2)), second))
    assert [h.count for h in counts.horizons] == [1, 2]


@pytest.mark.parametrize(
    "changes",
    [
        {"horizon_weights": (-1.0, 2.0)},
        {"horizon_weights": (0.0, 0.0)},
        {"horizon_weights": (1.0,)},
        {"random_seed": -1},
        {"random_seed": 2**64},
        {"tolerance": 0.0},
        {"condition_limit": 0.0},
        {"ridge_penalty": -1.0},
        {"loss_policy": "automatic-selection"},
        {"implementation_version": "future"},
        {"shared_cutoff_ns": 40},
        {"horizon_weights": (float("nan"), 1.0)},
        {"sharing": ()},
        {"bindings": ()},
    ],
)
def test_spec_rejects_ambiguous_policy(case: Case, changes: dict[str, object]) -> None:
    with pytest.raises(ContractError):
        replace(case.fixture.spec, **changes)  # type: ignore[arg-type]


def test_sharing_and_bindings(case: Case) -> None:
    spec = case.fixture.spec
    assert (
        replace(
            spec, bindings=tuple(reversed(spec.bindings)), sharing=tuple(reversed(spec.sharing))
        )
        == spec
    )
    assert replace(spec, horizon_weights=(2.0, 1.0)).fingerprint != spec.fingerprint
    for b in spec.bindings:
        with pytest.raises(ContractError, match="incomplete"):
            replace(b, probability_spec_id=None)
    with pytest.raises(ContractError, match="calibration requires"):
        replace(spec.bindings[0], probability_spec_id=None, probability_model_id=None)
    shared = backbone_spec(case.fixture)
    assert any(s.ownership is ParameterOwnership.GLOBAL_SHARED for s in shared.sharing)
    group = ParameterSharing(
        "latent",
        ParameterOwnership.GROUP_SHARED,
        tuple(t.fingerprint for t in spec.horizon_set.targets),
    )
    assert deserialize(canonical_json(group)) == group
    with pytest.raises(ContractError):
        replace(group, target_ids=group.target_ids[:1])
    with pytest.raises(ContractError):
        replace(shared, shared_cutoff_ns=41)
    with pytest.raises(ContractError):
        replace(shared, horizon_weights=(0.0, 1.0))
    independent = replace(
        spec,
        architecture=Architecture.SHARED_FEATURES_SEPARATE_MODELS,
        sharing=sharing_for(spec.horizon_set, Architecture.SHARED_FEATURES_SEPARATE_MODELS),
    )
    assert case.engine.fit(independent, 55, 55, 55).shared_parameters_id is None


@pytest.mark.parametrize(
    "changes",
    [
        {"horizons": 0},
        {"horizons": 65},
        {"serialized_bytes": 17 * 1024 * 1024},
        {"audit_depth": 65},
    ],
)
def test_hard_bounds(changes: dict[str, int]) -> None:
    with pytest.raises(ContractError):
        MultiHorizonBounds(**changes)


def test_missing_entry_state(case: Case) -> None:
    entry = case.fixture.bundles[0].entries[0]
    with pytest.raises(ContractError):
        replace(entry, state=ComponentState.MISSING)
    with pytest.raises(ContractError):
        replace(entry, point_forecast_id=None)

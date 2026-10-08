"""Closed definitions, bounds and target-free pre-evaluation paths, including cached reads."""

from dataclasses import fields, replace
from typing import Any, TypeVar, cast

import pytest

from afre.costs import (
    CostComponentType,
    CostInputRole,
    CostResearchBounds,
    CostResultState,
    CostSensitivitySpec,
    CostTiming,
    CostUnit,
)
from afre.costs.artifacts import CostAwareEvaluation, ResearchExposureChange
from afre.schema import Artifact, ContractError
from afre.serialization import canonical_json
from afre.target_engine.models import TargetVintage
from tests.costs.conftest import CostCase
from tests.costs.helpers import replace_input

A = TypeVar("A", bound=Artifact)


def test_target_free_cost_metadata_and_cached_guard(
    case: CostCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    reads = []
    get = case.repo.get

    def counted(cls: type[A], identity: str) -> A:
        if cls is TargetVintage:
            reads.append(identity)
        return get(cls, identity)

    monkeypatch.setattr(case.repo, "get", counted)
    path, totals = case.engine.estimate(case.fixture.scenario.fingerprint, 70)
    assert not reads
    value = case.engine.evaluate(path.fingerprint, tuple(t.fingerprint for t in totals), 70, 70)
    assert reads
    with case.repo.read_snapshot(), case.repo.validation_cache():
        case.repo.resolve(CostAwareEvaluation, value.fingerprint)
        with case.repo.feature_only(), pytest.raises(ContractError, match="metadata"):
            case.repo.resolve(CostAwareEvaluation, value.fingerprint)
    change = case.repo.resolve(ResearchExposureChange, totals[0].change_id)
    with pytest.raises(ContractError, match="actually available"):
        case.engine.metadata(totals[0].fingerprint, change.origin)


@pytest.mark.parametrize(
    "field,value",
    [
        ("maximum_participation", 0.0),
        ("maximum_participation", 1.1),
        ("minimum_count", 0),
        ("maximum_input_age_ns", -1),
        ("implementation_version", "unknown"),
        ("signal_unit", "unknown"),
    ],
)
def test_scenario_rejects_bad_policy(case: CostCase, field: str, value: object) -> None:
    with pytest.raises(ContractError):
        changed = replace(case.fixture.scenario, **{field: cast(Any, value)})
        case.engine.declare(changed)


@pytest.mark.parametrize("field", [f.name for f in fields(CostResearchBounds)])
def test_bounds_closed(field: str) -> None:
    with pytest.raises(ContractError):
        replace(CostResearchBounds(), **{field: 0})


def test_double_count_embedded_spread(case: CostCase) -> None:
    s = case.fixture.scenario
    specs = tuple(
        replace(c, covers=(CostComponentType.SLIPPAGE, CostComponentType.SPREAD))
        if c.component is CostComponentType.SLIPPAGE
        else c
        for c in s.components
    )
    with pytest.raises(ContractError, match="double-counted"):
        replace(s, components=specs)


def test_borrow_unsupported(case: CostCase) -> None:
    c = case.fixture.scenario.components[0]
    with pytest.raises(ContractError, match="borrow"):
        replace(
            c, component=CostComponentType.BORROW_COST, covers=(CostComponentType.BORROW_COST,)
        )


@pytest.mark.parametrize(
    "quality_unit",
    [
        (CostInputRole.REFERENCE_PRICE, CostUnit.BASIS_POINTS),
        (CostInputRole.REFERENCE_NOTIONAL, CostUnit.PRICE),
        (CostInputRole.AVAILABLE_VOLUME, CostUnit.CURRENCY_TOTAL),
    ],
)
def test_liquidity_wrong_units(
    case: CostCase, quality_unit: tuple[CostInputRole, CostUnit]
) -> None:
    role, unit = quality_unit
    old = next(i for i in case.fixture.inputs if i.role is role)
    with pytest.raises(ContractError, match="units/value"):
        replace(old, unit=unit)


def test_excess_participation_no_clipping(case: CostCase) -> None:
    old = next(
        i
        for i in case.fixture.inputs
        if i.role is CostInputRole.AVAILABLE_VOLUME and i.as_of_ns == 40
    )
    value = replace(old, value=1.0, revision="thin-volume")
    s = replace_input(case, case.fixture.scenario, old.fingerprint, value, "thin")
    case.engine.declare(s)
    with pytest.raises(ContractError, match="participation exceeds"):
        case.engine.estimate(s.fingerprint, 70)


def test_grid_predeclared_not_test_selected(case: CostCase) -> None:
    s = case.fixture.scenario
    c = next(c for c in s.components if c.component is CostComponentType.MARKET_IMPACT)
    with pytest.raises(ContractError, match="grid explosion"):
        CostSensitivitySpec(
            s.fingerprint, c.fingerprint, tuple(float(i) for i in range(65)), (), (1.0,), 40
        )
    late = CostSensitivitySpec(s.fingerprint, c.fingerprint, (1.0,), (0.01,), (1.0,), 41)
    with pytest.raises(ContractError, match="before held-out"):
        case.engine.register_sensitivity(late)
    with pytest.raises(ContractError, match="held-out"):
        case.engine.declare(replace(s, scenario_id="late", declared_ns=41))


def test_forecast_and_prior_native_tables_unchanged(case: CostCase) -> None:
    oldtables = tuple(
        r[0]
        for r in case.repo._connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        if not r[0].startswith("cost_")
    )
    before = {
        t: case.repo._connection.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall()
        for t in oldtables
    }
    source_bytes = tuple(
        canonical_json(case.repo.get_any(i)) for i in case.fixture.scenario.source_ids
    )
    path, totals = case.engine.estimate(case.fixture.scenario.fingerprint, 70)
    result = case.engine.evaluate(
        path.fingerprint, tuple(t.fingerprint for t in totals), 70, 70
    )
    case.engine.breakeven(result.fingerprint, 70)
    assert before == {
        t: case.repo._connection.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall()
        for t in oldtables
    }
    assert source_bytes == tuple(
        canonical_json(case.repo.get_any(i)) for i in case.fixture.scenario.source_ids
    )
    assert not any(
        hasattr(case.engine, n)
        for n in (
            "route",
            "execute",
            "place_order",
            "optimize",
            "select_model",
            "refit",
            "prune",
            "promote",
        )
    )
    assert (
        result.timing is CostTiming.HISTORICAL_CAUSAL
        and result.state is CostResultState.AVAILABLE
    )

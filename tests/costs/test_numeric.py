"""Independent arithmetic oracles for stated cost units and hypothetical mappings."""

import math
from dataclasses import replace

import pytest

from afre.costs import (
    CostBasis,
    CostComponentType,
    CostModel,
    CostResultState,
    CostUnit,
    InitialExposurePolicy,
    ResearchExposureMode,
    ResearchExposureRule,
    SpreadMeaning,
)
from afre.costs.exposures import exposure_for
from afre.costs.fees import conversion_factor
from afre.costs.impact import impact_multiplier
from afre.costs.spread import observed_full_spread, spread_multiplier
from afre.schema import ContractError
from tests.costs.conftest import CostCase


@pytest.mark.parametrize(
    "unit,expected",
    [
        (CostUnit.BASIS_POINTS, 0.0002),
        (CostUnit.RETURN_FRACTION, 2.0),
        (CostUnit.PRICE, 0.02),
        (CostUnit.CURRENCY_PER_UNIT, 0.02),
        (CostUnit.CURRENCY_TOTAL, 0.0002),
    ],
)
def test_unit_conversion_independent(unit: CostUnit, expected: float) -> None:
    assert (
        conversion_factor(unit, CostBasis.PER_SIDE_PER_TURNOVER, 2.0, 100.0, 10_000.0)
        == expected
    )


@pytest.mark.parametrize(
    "basis,delta,expected",
    [
        (CostBasis.ROUND_TRIP_PER_TURNOVER, 2.0, 0.0001),
        (CostBasis.PER_TRADE, 2.0, 0.0001),
        (CostBasis.PER_TRADE, 0.0, 0.0),
    ],
)
def test_fee_basis_counting(basis: CostBasis, delta: float, expected: float) -> None:
    assert conversion_factor(CostUnit.CURRENCY_TOTAL, basis, delta, 100.0, 10_000.0) == expected


@pytest.mark.parametrize("unit", list(CostUnit))
def test_no_transition_cost(unit: CostUnit) -> None:
    if unit is CostUnit.UNIT_QUANTITY:
        with pytest.raises(ContractError):
            conversion_factor(unit, CostBasis.PER_SIDE_PER_TURNOVER, 1.0, 100.0, 10_000.0)
    else:
        assert (
            conversion_factor(unit, CostBasis.PER_SIDE_PER_TURNOVER, 0.0, 100.0, 10_000.0) == 0
        )


def test_round_trip_buy_then_sell_spread_fees() -> None:
    full = observed_full_spread(99.0, 101.0)
    assert full == 2.0
    costs = [
        full
        * spread_multiplier(SpreadMeaning.FULL_SPREAD)
        * conversion_factor(CostUnit.PRICE, CostBasis.PER_SIDE_PER_TURNOVER, d, 100.0, 10_000.0)
        for d in (1.0, -1.0)
    ]
    assert costs == [0.01, 0.01]
    assert sum(costs) == 0.02
    fees = [
        8.0
        * conversion_factor(
            CostUnit.CURRENCY_TOTAL, CostBasis.ROUND_TRIP_PER_TURNOVER, d, 100.0, 10_000.0
        )
        for d in (1.0, -1.0)
    ]
    assert sum(fees) == 0.0008


@pytest.mark.parametrize(
    "model,p,expected",
    [
        (CostModel.LINEAR_PARTICIPATION, 0.04, 0.04),
        (CostModel.SQRT_PARTICIPATION, 0.04, 0.2),
        (CostModel.FIXED_RATE, None, 1.0),
    ],
)
def test_impact_oracle(model: CostModel, p: float | None, expected: float) -> None:
    assert impact_multiplier(model, p) == expected


@pytest.mark.parametrize("p", [None, -0.1, 1.1])
def test_participation_invalid(p: float | None) -> None:
    with pytest.raises(ContractError):
        impact_multiplier(CostModel.LINEAR_PARTICIPATION, p)


@pytest.mark.parametrize(
    "mode,prediction,expected",
    [
        (ResearchExposureMode.SIGN, -3.0, -1.0),
        (ResearchExposureMode.SIGN, 0.0, 0.0),
        (ResearchExposureMode.SIGN, 3.0, 1.0),
        (ResearchExposureMode.THRESHOLD_SIGN, 2.0, 0.0),
        (ResearchExposureMode.THRESHOLD_SIGN, 2.1, 1.0),
        (ResearchExposureMode.FIXED_UNIT_NOTIONAL, -3.0, 1.0),
        (ResearchExposureMode.DECLARED_SCALAR_EXPOSURE, 3.0, -0.5),
    ],
)
def test_exposure_oracle(
    mode: ResearchExposureMode, prediction: float, expected: float
) -> None:
    rule = ResearchExposureRule(
        mode,
        -1.0,
        1.0,
        1.0,
        2.0 if mode is ResearchExposureMode.THRESHOLD_SIGN else 0.0,
        -0.5 if mode is ResearchExposureMode.DECLARED_SCALAR_EXPOSURE else 0.0,
        InitialExposurePolicy.ZERO,
        0.0,
        0,
    )
    assert exposure_for(rule, prediction) == expected


def test_gross_net_turnover_independent(case: CostCase) -> None:
    from afre.costs import (
        CostAwareSampleEvaluation,
        CostComponentEstimate,
        ResearchExposureChange,
    )
    from afre.target_engine.models import TargetVintage

    path, totals = case.engine.estimate(case.fixture.scenario.fingerprint, 70)
    evaluation = case.engine.evaluate(
        path.fingerprint, tuple(t.fingerprint for t in totals), 70, 70
    )
    rows = tuple(
        case.repo.resolve(CostAwareSampleEvaluation, i)
        for i in evaluation.sample_evaluation_ids
    )
    changes = tuple(case.repo.resolve(ResearchExposureChange, i) for i in path.change_ids)
    assert evaluation.path_turnover == sum(abs(c.exposure - c.prior_exposure) for c in changes)
    for row in rows:
        assert row.truth_id is not None
        truth = case.repo.resolve(TargetVintage, row.truth_id)
        change = case.repo.resolve(ResearchExposureChange, row.change_id)
        assert truth.value is not None
        assert row.gross_contribution == change.exposure * truth.value
        total = next(t for t in totals if t.change_id == change.fingerprint)
        comps = tuple(case.repo.resolve(CostComponentEstimate, i) for i in total.component_ids)
        expected = 0.0
        for c in comps:
            assert c.rate is not None and c.unit_conversion_factor is not None
            spec = next(
                s for s in case.fixture.scenario.components if s.fingerprint == c.component_id
            )
            delta = abs(change.trade_delta)
            if spec.component is CostComponentType.SPREAD:
                amount = delta * ((100.02 - 99.98) / 100.0) / 2.0
            elif spec.component is CostComponentType.EXPLICIT_FEE:
                amount = delta * 100.0 * 0.01 / 10_000.0
            elif spec.component is CostComponentType.SLIPPAGE:
                amount = delta / 10_000.0
            elif spec.component is CostComponentType.MARKET_IMPACT:
                amount = delta * (20.0 * (delta * 100.0 / 10_000.0)) / 10_000.0
            else:
                amount = delta * 0.5 / 10_000.0
            assert c.amount == pytest.approx(amount, abs=1e-15)
            expected += amount
        assert row.total_cost == pytest.approx(expected, abs=1e-15)
        assert row.net_contribution == pytest.approx(
            row.gross_contribution - expected, abs=1e-15
        )
    assert evaluation.gross_sum == math.fsum(
        r.gross_contribution for r in rows if r.gross_contribution is not None
    )
    assert evaluation.net_mean == pytest.approx(
        (evaluation.gross_sum - (evaluation.total_cost_sum or 0)) / len(rows)
    )
    assert evaluation.state is CostResultState.AVAILABLE


def test_initial_exposure_distinct(case: CostCase) -> None:
    s = case.fixture.scenario
    declared = replace(
        s,
        scenario_id="declared-initial",
        exposure_rule=replace(
            s.exposure_rule,
            initial_policy=InitialExposurePolicy.DECLARED_INITIAL,
            initial_exposure=0.5,
        ),
    )
    case.engine.declare(declared)
    from afre.costs.exposures import path_for

    with case.repo.read_snapshot(), case.repo.validation_cache():
        zero, _ = path_for(case.repo, s.fingerprint, 70)
        initial, _ = path_for(case.repo, declared.fingerprint, 70)
    first_zero = {c.sample_id: c for c in zero if c.previous_sample_id is None}
    first_initial = {c.sample_id: c for c in initial if c.previous_sample_id is None}
    assert len(first_zero) == len({c.origin.instrument.fingerprint for c in zero}) == 5
    assert all(c.prior_exposure == 0.5 for c in first_initial.values())
    assert all(
        first_initial[i].trade_delta == first_zero[i].trade_delta - 0.5 for i in first_zero
    )

"""Missingness, gross/net, algebraic thresholds and explicitly supplied sensitivity grids."""

import math
from dataclasses import replace

import pytest

from afre.costs import (
    CostComponentType,
    CostMissingPolicy,
    CostModel,
    CostQuality,
    CostResultState,
    CostSensitivitySpec,
    InitialExposurePolicy,
    ResearchExposureMode,
)
from afre.costs.artifacts import (
    CostAwareSampleEvaluation,
    CostComponentEstimate,
    ResearchExposureChange,
)
from afre.schema import ContractError
from tests.costs.conftest import CostCase
from tests.costs.helpers import replace_input, with_components


@pytest.mark.parametrize("policy", list(CostMissingPolicy))
def test_missing_policy_no_zero_default(case: CostCase, policy: CostMissingPolicy) -> None:
    s = case.fixture.scenario
    old = next(
        i
        for i in case.fixture.inputs
        if i.component is CostComponentType.CUSTOM_COST and i.role.value == "model_value"
    )
    missing = replace(old, value=None, quality=CostQuality.MISSING, revision="missing")
    specs = tuple(
        replace(c, fallback_value=2.0)
        if c.component is CostComponentType.CUSTOM_COST
        and policy is CostMissingPolicy.DECLARED_FALLBACK
        else c
        for c in s.components
    )
    changed = with_components(replace(s, missing_policy=policy), specs, "missing-policy")
    changed = replace_input(case, changed, old.fingerprint, missing, "missing-policy")
    case.engine.declare(changed)
    before = case.repo._connection.execute("SELECT count(*) FROM cost_artifacts").fetchone()[0]
    if policy is CostMissingPolicy.FAIL:
        with pytest.raises(ContractError, match="missing cost/liquidity"):
            case.engine.estimate(changed.fingerprint, 70)
        assert (
            case.repo._connection.execute("SELECT count(*) FROM cost_artifacts").fetchone()[0]
            == before
        )
        return
    path, totals = case.engine.estimate(changed.fingerprint, 70)
    evaluation = case.engine.evaluate(
        path.fingerprint, tuple(t.fingerprint for t in totals), 70, 70
    )
    if policy is CostMissingPolicy.EXCLUDE_SAMPLE:
        assert evaluation.sample_count == 11 and len(evaluation.exclusions) == 1
        assert evaluation.path_turnover >= evaluation.turnover
        assert sum(t.amount is None for t in totals) == 1
    else:
        assert evaluation.sample_count == 12
        estimates = tuple(
            case.repo.resolve(CostComponentEstimate, i) for t in totals for i in t.component_ids
        )
        fallback = next(c for c in estimates if c.used_fallback)
        assert fallback.rate == 2.0 and fallback.quality is CostQuality.DEGRADED


@pytest.mark.parametrize(
    "quality",
    [CostQuality.STALE, CostQuality.DEGRADED, CostQuality.UNSUPPORTED, CostQuality.INVALID],
)
def test_quality_exclusions(case: CostCase, quality: CostQuality) -> None:
    old = next(
        i
        for i in case.fixture.inputs
        if i.component is CostComponentType.CUSTOM_COST and i.role.value == "model_value"
    )
    bad = replace(
        old,
        quality=quality,
        value=old.value if quality in (CostQuality.STALE, CostQuality.DEGRADED) else None,
        revision=quality.value,
    )
    s = replace_input(
        case,
        replace(case.fixture.scenario, missing_policy=CostMissingPolicy.EXCLUDE_SAMPLE),
        old.fingerprint,
        bad,
        "quality",
    )
    case.engine.declare(s)
    path, totals = case.engine.estimate(s.fingerprint, 70)
    result = case.engine.evaluate(
        path.fingerprint, tuple(t.fingerprint for t in totals), 70, 70
    )
    assert len(result.exclusions) == 1


def test_declared_degraded_acceptance(case: CostCase) -> None:
    old = next(
        i
        for i in case.fixture.inputs
        if i.component is CostComponentType.CUSTOM_COST and i.role.value == "model_value"
    )
    degraded = replace(old, quality=CostQuality.DEGRADED, revision="degraded")
    s = replace_input(
        case,
        replace(case.fixture.scenario, allow_degraded=True),
        old.fingerprint,
        degraded,
        "accept-degraded",
    )
    case.engine.declare(s)
    _, totals = case.engine.estimate(s.fingerprint, 70)
    assert all(t.amount is not None for t in totals)


def test_break_even_independent(case: CostCase) -> None:
    path, totals = case.engine.estimate(case.fixture.scenario.fingerprint, 70)
    result = case.engine.evaluate(
        path.fingerprint, tuple(t.fingerprint for t in totals), 70, 70
    )
    assert result.gross_sum is not None and result.total_cost_sum is not None
    total = case.engine.breakeven(result.fingerprint, 70)
    assert total.threshold == result.gross_sum / result.turnover * 10_000
    for spec in case.fixture.scenario.components:
        diagnostic = case.engine.breakeven(result.fingerprint, 70, spec.fingerprint)
        components = tuple(
            case.repo.resolve(CostComponentEstimate, i) for t in totals for i in t.component_ids
        )
        chosen = tuple(c for c in components if c.component_id == spec.fingerprint)
        others = sum(
            c.amount
            for c in components
            if c.component_id != spec.fingerprint and c.amount is not None
        )
        denominator = sum(
            (c.unit_conversion_factor or 0) * (c.participation or 0)
            if spec.model is CostModel.LINEAR_PARTICIPATION
            else (c.unit_conversion_factor or 0)
            for c in chosen
        )
        assert diagnostic.threshold == pytest.approx((result.gross_sum - others) / denominator)
        assert diagnostic.threshold_unit is spec.unit


def test_zero_gross_zero_turnover_explicit(case: CostCase) -> None:
    s = case.fixture.scenario
    rule = replace(
        s.exposure_rule, mode=ResearchExposureMode.DECLARED_SCALAR_EXPOSURE, scalar_exposure=0.0
    )
    changed = replace(s, scenario_id="zero-exposure", exposure_rule=rule)
    case.engine.declare(changed)
    path, totals = case.engine.estimate(changed.fingerprint, 70)
    result = case.engine.evaluate(
        path.fingerprint, tuple(t.fingerprint for t in totals), 70, 70
    )
    assert result.gross_sum == result.net_sum == result.turnover == 0
    assert (
        result.cost_to_gross_ratio is None
        and result.average_cost_per_turnover_unit is None
        and result.edge_survival_fraction is None
    )
    assert case.engine.breakeven(result.fingerprint, 70).state is CostResultState.UNAVAILABLE


def test_no_new_trade_declared_initial(case: CostCase) -> None:
    s = case.fixture.scenario
    rule = replace(
        s.exposure_rule,
        mode=ResearchExposureMode.DECLARED_SCALAR_EXPOSURE,
        scalar_exposure=0.5,
        initial_policy=InitialExposurePolicy.DECLARED_INITIAL,
        initial_exposure=0.5,
    )
    changed = replace(s, scenario_id="already-held", exposure_rule=rule)
    case.engine.declare(changed)
    path, totals = case.engine.estimate(changed.fingerprint, 70)
    result = case.engine.evaluate(
        path.fingerprint, tuple(t.fingerprint for t in totals), 70, 70
    )
    assert result.turnover == 0 and result.total_cost_sum == 0
    assert result.gross_sum is not None and result.gross_sum > 0
    assert case.engine.breakeven(result.fingerprint, 70).threshold is None


def test_supplied_cost_curve_oracle(case: CostCase) -> None:
    s = case.fixture.scenario
    path, totals = case.engine.estimate(s.fingerprint, 70)
    result = case.engine.evaluate(
        path.fingerprint, tuple(t.fingerprint for t in totals), 70, 70
    )
    slippage = next(c for c in s.components if c.component is CostComponentType.SLIPPAGE)
    grid = CostSensitivitySpec(
        s.fingerprint, slippage.fingerprint, (0.0, 1.0, 5.0, 10.0), (), (1.0,), 40
    )
    case.engine.register_sensitivity(grid)
    curve = case.engine.sensitivity(result.fingerprint, grid.fingerprint, 70)
    assert len(curve.points) == 4 and result.net_sum is not None
    for p in curve.points:
        expected = result.net_sum - (p.rate - 1.0) * result.turnover / 10_000
        assert p.net_sum == pytest.approx(expected, abs=1e-15)
    intensity = replace(grid, rates=(1.0,), turnover_multipliers=(1.0, 2.0))
    case.engine.register_sensitivity(intensity)
    curve = case.engine.sensitivity(result.fingerprint, intensity.fingerprint, 70)
    assert len(curve.points) == 2
    assert all(p.net_sum is not None for p in curve.points)
    changes = tuple(case.repo.resolve(ResearchExposureChange, i) for i in path.change_ids)
    assert result.gross_sum is not None
    for point in curve.points:
        m = point.turnover_multiplier
        expected_cost = math.fsum(
            abs(c.trade_delta) * 0.00045 * m
            + abs(c.trade_delta) ** 2 * 20 * 0.01 * 0.0001 * m**2
            for c in changes
        )
        assert point.net_sum == pytest.approx(result.gross_sum - expected_cost, abs=1e-15)


@pytest.mark.parametrize(
    "model", [CostModel.LINEAR_PARTICIPATION, CostModel.SQRT_PARTICIPATION]
)
def test_participation_curve_oracle(case: CostCase, model: CostModel) -> None:
    s = case.fixture.scenario
    old = next(c for c in s.components if c.component is CostComponentType.MARKET_IMPACT)
    new = replace(old, model=model)
    changed = with_components(s, (new,), "impact-only")
    case.engine.declare(changed)
    path, totals = case.engine.estimate(changed.fingerprint, 70)
    result = case.engine.evaluate(
        path.fingerprint, tuple(t.fingerprint for t in totals), 70, 70
    )
    grid = CostSensitivitySpec(
        changed.fingerprint, new.fingerprint, (20.0,), (0.01, 0.04), (1.0,), 40
    )
    case.engine.register_sensitivity(grid)
    curve = case.engine.sensitivity(result.fingerprint, grid.fingerprint, 70)
    for p in curve.points:
        assert p.participation is not None and result.gross_sum is not None
        impact = (
            p.participation if model is CostModel.LINEAR_PARTICIPATION else p.participation**0.5
        )
        assert p.net_sum == pytest.approx(
            result.gross_sum - result.turnover * 20.0 * impact / 10_000
        )


def test_unavailable_truth_and_minimum(case: CostCase) -> None:
    s = replace(case.fixture.scenario, scenario_id="minimum", minimum_count=13)
    case.engine.declare(s)
    path, totals = case.engine.estimate(s.fingerprint, 60)
    result = case.engine.evaluate(
        path.fingerprint, tuple(t.fingerprint for t in totals), 60, 60
    )
    assert result.state is CostResultState.INSUFFICIENT_DATA and result.exclusions
    assert any(
        case.repo.resolve(CostAwareSampleEvaluation, i).truth_id is None
        for i in result.sample_evaluation_ids
    )


@pytest.mark.parametrize("policy", list(CostMissingPolicy))
def test_absent_volume_obeys_explicit_missing_policy(
    case: CostCase, policy: CostMissingPolicy
) -> None:
    base = case.fixture.scenario
    s = replace(
        base,
        scenario_id="absent-volume-" + policy.value,
        missing_policy=policy,
        liquidity=tuple(replace(a, volume_input_id=None) for a in base.liquidity),
    )
    case.engine.declare(s)
    if policy is CostMissingPolicy.EXCLUDE_SAMPLE:
        path, totals = case.engine.estimate(s.fingerprint, 70)
        assert all(t.amount is None for t in totals)
        assert all(
            any(
                "missing-explicit-available-volume"
                in case.repo.resolve(CostComponentEstimate, i).reason
                for i in t.component_ids
            )
            for t in totals
        )
        assert len(path.change_ids) == len(base.sample_ids)
    else:
        with pytest.raises(ContractError, match="missing cost/liquidity"):
            case.engine.estimate(s.fingerprint, 70)

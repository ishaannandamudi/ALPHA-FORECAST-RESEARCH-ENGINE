"""Native phase integrations, exact PIT cohorts and separately assessed actual horizons."""

import math
from dataclasses import replace

import pytest

from afre.costs import (
    CostInputRole,
    CostModel,
    CostResearchBounds,
    CostScenario,
    CostSensitivitySpec,
)
from afre.costs.artifacts import CostAwareSampleEvaluation, ResearchExposureChange
from afre.costs.schema import CostComponentType, CostResultState
from afre.invariance import EnvironmentMembership, StabilityAnalysisSpec
from afre.orthogonalization import OrthogonalSignalValue
from afre.research_datasets.schema import Partition
from afre.schema import ContractError
from afre.serialization import canonical_json
from examples.costs_fixture import declare_scenario
from examples.costs_workflow import assess, point_scenario, subset_source
from examples.invariance_cohorts import build_cohorts
from examples.invariance_horizons import horizon_analyses
from tests.costs.conftest import CostCase
from tests.costs.helpers import replace_input


@pytest.mark.parametrize(
    "name",
    (
        "point",
        "gaussian",
        "calibrated",
        "event",
        "hard-regime",
        "soft-regime",
        "mixture",
        "nonlinear",
        "sequence",
    ),
)
def test_native_forecast_families(case: CostCase, name: str) -> None:
    ids = case.fixture.upstream.upstream.upstream.ids(name)
    s = subset_source(case.repo, case.fixture.scenario, ids, name)
    source_bytes = tuple(canonical_json(case.repo.get_any(i)) for i in ids)
    _, _, result = assess(case.engine, s)
    assert result.state is CostResultState.AVAILABLE
    assert result.sample_count == len(ids)
    assert source_bytes == tuple(canonical_json(case.repo.get_any(i)) for i in ids)


def test_uncertainty_separate_target_free_attachment(case: CostCase) -> None:
    f = case.fixture.upstream.upstream.upstream
    base = subset_source(case.repo, case.fixture.scenario, f.ids("gaussian"), "without-u")
    attached = replace(base, scenario_id="with-u", uncertainty_ids=f.results("gaussian"))
    case.engine.declare(attached)
    with case.repo.feature_only():
        case.engine.estimate(attached.fingerprint, 70)
    _, totals, a = assess(case.engine, attached)
    _, other, b = assess(case.engine, base)
    assert sorted(t.amount for t in totals if t.amount is not None) == sorted(
        t.amount for t in other if t.amount is not None
    )
    assert (a.gross_sum, a.total_cost_sum, a.net_sum) == (
        b.gross_sum,
        b.total_cost_sum,
        b.net_sum,
    )
    assert all(
        case.repo.get(CostAwareSampleEvaluation, i).uncertainty_ids
        for i in a.sample_evaluation_ids
    )
    wrong = replace(base, scenario_id="wrong-u", uncertainty_ids=f.results("point"))
    case.engine.declare(wrong)
    path, ts = case.engine.estimate(wrong.fingerprint, 70)
    with pytest.raises(ContractError, match="uncertainty attachment"):
        case.engine.evaluate(path.fingerprint, tuple(t.fingerprint for t in ts), 100, 100)


def test_native_residual_unit_and_exact_source(case: CostCase) -> None:
    f = case.fixture.upstream.upstream
    ids = f.residual_ids(Partition.VALIDATION)
    unit = case.repo.get(OrthogonalSignalValue, ids[0]).unit
    s = subset_source(case.repo, case.fixture.scenario, ids, "residual", unit=unit)
    _, _, result = assess(case.engine, s)
    assert result.state is CostResultState.AVAILABLE
    with pytest.raises(ContractError, match="threshold units"):
        case.engine.declare(replace(s, scenario_id="bad-unit", signal_unit="return_fraction"))
    point = assess(case.engine, point_scenario(case.repo, case.fixture))[2]
    assert (
        case.engine.compare(result.fingerprint, point.fingerprint, 100).state
        is CostResultState.INCOMPARABLE
    )


def test_exact_matched_descriptive_comparison(case: CostCase) -> None:
    a = assess(case.engine, case.fixture.scenario)[2]
    b = assess(case.engine, point_scenario(case.repo, case.fixture))[2]
    comparison = case.engine.compare(a.fingerprint, b.fingerprint, 100)
    assert comparison.state is CostResultState.AVAILABLE
    assert comparison.sample_ids == a.included_sample_ids
    assert comparison.net_delta == pytest.approx((b.net_mean or 0) - (a.net_mean or 0))
    changed = replace(
        case.fixture.scenario, scenario_id="different-policy", maximum_input_age_ns=1
    )
    c = assess(case.engine, changed)[2]
    assert (
        case.engine.compare(a.fingerprint, c.fingerprint, 100).state
        is CostResultState.INCOMPARABLE
    )


def test_native_cohorts_independent_weight_oracle(case: CostCase) -> None:
    cohorts = build_cohorts(case.repo, case.fixture.upstream)
    result = assess(case.engine, case.fixture.scenario)[2]
    definitions = (
        *cohorts.environment_set.definitions,
        *case.fixture.upstream.environment_set.definitions,
    )
    memberships = (*cohorts.membership_ids, *case.fixture.upstream.membership_ids)
    requests = tuple(
        (
            d.fingerprint,
            tuple(
                i
                for i in memberships
                if case.repo.get(EnvironmentMembership, i).environment_id == d.fingerprint
            ),
        )
        for d in definitions
    )
    outputs = case.engine.cohorts(result.fingerprint, requests, 100)
    assert len(outputs) == 13
    rows = {
        r.sample_id: r
        for i in result.sample_evaluation_ids
        if (r := case.repo.get(CostAwareSampleEvaluation, i)).state is CostResultState.AVAILABLE
    }
    for c in outputs:
        members = tuple(case.repo.get(EnvironmentMembership, i) for i in c.membership_ids)
        weighted = tuple((rows[m.sample_id], m.weight) for m in members if m.weight > 0)
        den = math.fsum(w for _, w in weighted)
        if c.state is CostResultState.AVAILABLE:
            assert c.net_mean == pytest.approx(
                math.fsum((r.net_contribution or 0) * w for r, w in weighted) / den
            )
            assert c.weighted_turnover == pytest.approx(
                math.fsum(
                    abs(case.repo.get(ResearchExposureChange, r.change_id).trade_delta) * w
                    for r, w in weighted
                )
            )
    case.repo.cost_research_bounds = replace(CostResearchBounds(), environments=1)
    with pytest.raises(ContractError, match="cohort request"):
        case.engine.cohorts(result.fingerprint, requests, 100)
    case.repo.cost_research_bounds = CostResearchBounds()
    with pytest.raises(ContractError, match="grid"):
        case.engine.cohort(result.fingerprint, requests[0][0], requests[0][1][:-1], 100)
    with pytest.raises(ContractError, match="duplicates"):
        case.engine.cohorts(result.fingerprint, (requests[0], requests[0]), 100)


def test_actual_one_hour_one_day_separate(case: CostCase) -> None:
    metrics = horizon_analyses(case.repo)
    results = []
    for m in metrics:
        spec = case.repo.get(StabilityAnalysisSpec, m.spec_id)
        scenario, _ = declare_scenario(case.repo, spec)
        results.append(assess(case.engine, scenario, m.truth_cutoff_ns)[2])
    assert len(results) == 2
    targets = tuple(case.repo.get(CostScenario, r.scenario_id).target for r in results)
    assert {t.horizon.duration_ns for t in targets} == {3600 * 10**9, 86400 * 10**9}
    assert targets[0].fingerprint != targets[1].fingerprint
    assert (
        case.engine.compare(
            results[0].fingerprint, results[1].fingerprint, max(r.available_ns for r in results)
        ).state
        is CostResultState.INCOMPARABLE
    )


def test_provider_embedded_category_mismatch(case: CostCase) -> None:
    old = next(i for i in case.fixture.inputs if i.role is CostInputRole.MODEL_VALUE)
    value = replace(
        old, included_components=(old.component, CostComponentType.SPREAD), revision="embedded"
    )
    s = replace_input(case, case.fixture.scenario, old.fingerprint, value, "mismatch")
    with pytest.raises(ContractError, match="exact input"):
        case.engine.declare(s)
    with pytest.raises(ContractError, match="declare included"):
        replace(old, included_components=())


def test_sqrt_native_and_participation_sensitivity(case: CostCase) -> None:
    from tests.costs.helpers import with_components

    base = case.fixture.scenario
    impact = next(c for c in base.components if c.component is CostComponentType.MARKET_IMPACT)
    changed = replace(impact, model=CostModel.SQRT_PARTICIPATION)
    s = with_components(
        base, tuple(changed if c == impact else c for c in base.components), "sqrt"
    )
    result = assess(case.engine, s)[2]
    grid = CostSensitivitySpec(
        s.fingerprint, changed.fingerprint, (10.0, 20.0), (0.0, 0.01, 0.1), (1.0, 2.0), 40
    )
    case.engine.register_sensitivity(grid)
    curve = case.engine.sensitivity(result.fingerprint, grid.fingerprint, 100)
    assert len(curve.points) == 12
    assert all(p.state is CostResultState.AVAILABLE for p in curve.points)

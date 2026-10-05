"""Independent weighted arithmetic and finite-law oracles, including atom endpoints."""

from dataclasses import replace
from math import erf, exp, fsum, pi, sqrt

import pytest

from afre.mixture import MixtureComponent, MixtureDistribution
from afre.mixture.definitions import FixedGateSpec
from afre.mixture.learned import project_simplex, solve_simplex
from afre.mixture.probabilistic import (
    mixture_cdf,
    mixture_crps,
    mixture_expectation,
    mixture_nll,
    mixture_quantile,
    mixture_scores,
    mixture_threshold,
    mixture_variance,
)
from afre.probabilistic.artifacts import DistributionParameters, QuantileValue
from afre.probabilistic.definitions import ThresholdRequest
from afre.probabilistic.schema import DistributionFamily, DistributionState, ThresholdComparison
from afre.probabilistic.scoring import empirical_crps, gaussian_crps
from afre.schema import ContractError
from examples.mixture_demo import external_binding
from tests.mixture.conftest import Case


def law(case: Case, empirical: bool = False) -> MixtureDistribution:
    experts = case.fixture.learned_spec.expert_set.experts
    bindings = tuple(
        external_binding(case.repo, e, case.sample, float(index))
        for index, e in enumerate(experts)
    )
    distributions = (
        (
            DistributionParameters(
                DistributionFamily.EMPIRICAL_RESIDUAL, 0.0, 1.0, (-1.0, 0.0, 2.0)
            ),
            DistributionParameters(
                DistributionFamily.EMPIRICAL_RESIDUAL,
                1.0,
                0.0,
                (0.0,),
                state=DistributionState.DEGENERATE,
            ),
        )
        if empirical
        else (
            DistributionParameters(DistributionFamily.GAUSSIAN_LOCATION_SCALE, 0.0, 1.0),
            DistributionParameters(DistributionFamily.GAUSSIAN_LOCATION_SCALE, 2.0, 3.0),
        )
    )
    return MixtureDistribution(
        tuple(
            MixtureComponent(e.fingerprint, b, w, d)
            for e, b, w, d in zip(experts, bindings, (0.25, 0.75), distributions, strict=True)
        )
    )


def test_exact_fixed_point_and_contributions(case: Case) -> None:
    spec = case.fixture.learned_spec.expert_set
    values = (1.0, 3.0)
    weights = (0.25, 0.75)
    fixed = FixedGateSpec(spec, tuple(zip(spec.expert_ids, weights, strict=True)))
    case.engine.publish_gate(fixed)
    inputs = tuple(
        (e.fingerprint, external_binding(case.repo, e, case.sample, v))
        for e, v in zip(spec.experts, values, strict=True)
    )
    request = replace(
        case.forecast.request,
        expert_set_id=spec.fingerprint,
        gate_id=fixed.fingerprint,
        expert_inputs=inputs,
    )
    f = case.engine.forecast(request)
    assert f.value == 2.5
    assert tuple(c.contribution for c in f.contributions) == (0.25, 2.25)
    assert case.engine.forecast(replace(request, expert_inputs=tuple(reversed(inputs)))) == f


@pytest.mark.parametrize("x", [-5.0, -1.0, 0.0, 1.0, 5.0])
def test_gaussian_cdf_and_nll(case: Case, x: float) -> None:
    d = law(case)
    expected = 0.25 * (1 + erf(x / sqrt(2))) / 2 + 0.75 * (1 + erf((x - 2) / 3 / sqrt(2))) / 2
    assert mixture_cdf(d, x) == pytest.approx(expected, abs=1e-15)
    pdf = 0.25 * exp(-x * x / 2) / sqrt(2 * pi) + 0.75 * exp(-(((x - 2) / 3) ** 2) / 2) / (
        3 * sqrt(2 * pi)
    )
    from math import log

    assert mixture_nll(d, x) == pytest.approx(-log(pdf), abs=1e-14)


def test_total_variance_includes_between_component_variance(case: Case) -> None:
    d = law(case)
    assert mixture_expectation(d) == 1.5
    assert mixture_variance(d) == 0.25 * (1 + 0**2) + 0.75 * (9 + 2**2) - 1.5**2
    assert mixture_variance(d) != 0.25 * 1 + 0.75 * 9


@pytest.mark.parametrize("comparison", list(ThresholdComparison))
@pytest.mark.parametrize("x", [-1.0, 0.0, 1.0, 2.0])
def test_empirical_exact_threshold_atoms(
    case: Case, comparison: ThresholdComparison, x: float
) -> None:
    d = law(case, True)

    def outcome(v: float) -> bool:
        return (
            v > x
            if comparison is ThresholdComparison.GT
            else v >= x
            if comparison is ThresholdComparison.GE
            else v < x
            if comparison is ThresholdComparison.LT
            else v <= x
        )

    oracle = 0.25 * sum(outcome(v) for v in (-1.0, 0.0, 2.0)) / 3 + 0.75 * float(outcome(1.0))
    assert mixture_threshold(d, ThresholdRequest(x, comparison)) == pytest.approx(
        oracle, abs=1e-15
    )
    assert mixture_cdf(d, x, True) == pytest.approx(
        0.25 * sum(v < x for v in (-1.0, 0.0, 2.0)) / 3 + 0.75 * (x > 1.0)
    )


@pytest.mark.parametrize("truth", [-2.0, 0.0, 1.0, 5.0])
def test_empirical_crps_independent_weighted_atom_oracle(case: Case, truth: float) -> None:
    d = law(case, True)
    atoms = ((-1.0, 0.25 / 3), (0.0, 0.25 / 3), (2.0, 0.25 / 3), (1.0, 0.75))
    oracle = fsum(w * abs(x - truth) for x, w in atoms) - 0.5 * fsum(
        w * z * abs(x - y) for x, w in atoms for y, z in atoms
    )
    assert mixture_crps(d, truth) == pytest.approx(oracle, abs=1e-14)
    assert mixture_nll(d, truth) is None
    assert mixture_scores(d, truth, (ThresholdRequest(0.0, ThresholdComparison.GT),))


def test_single_component_scores_match_afre6(case: Case) -> None:
    for empirical in (False, True):
        c = law(case, empirical).components[0]
        d = MixtureDistribution((replace(c, weight=1.0),))
        old = (
            empirical_crps(c.distribution, 0.4)
            if empirical
            else gaussian_crps(c.distribution, 0.4)
        )
        assert mixture_crps(d, 0.4) == pytest.approx(old, abs=1e-15)


def test_gaussian_empirical_cross_terms_and_bounds(case: Case) -> None:
    gaussian, empirical = law(case).components[0], law(case, True).components[1]
    mixed = MixtureDistribution((gaussian, empirical))
    assert mixture_crps(mixed, 0.1) > 0
    assert mixture_crps(
        MixtureDistribution(tuple(reversed(mixed.components))), 0.1
    ) == mixture_crps(mixed, 0.1)
    with pytest.raises(ContractError, match="work bound"):
        mixture_crps(law(case, True), 0.0, 1)


def test_quantiles_are_explicitly_unsupported(case: Case) -> None:
    d = law(case)
    with pytest.raises(ContractError, match="never average"):
        mixture_quantile(d, 0.5)
    sparse = DistributionParameters(
        DistributionFamily.QUANTILE_SET,
        0.0,
        0.0,
        quantile_values=(QuantileValue(0.5, 0.0),),
        state=DistributionState.DEGENERATE,
    )
    with pytest.raises(ContractError, match="complete laws"):
        replace(d.components[0], distribution=sparse)


def test_simplex_closed_form_interior_and_financial_scaling() -> None:
    for scale in (1.0, 1e-4):
        weights, _, residual, objective = solve_simplex(
            ((1 * scale, 3 * scale), (1 * scale, 3 * scale)), (2.5 * scale, 2.5 * scale)
        )
        assert weights == pytest.approx((0.25, 0.75), abs=1e-9)
        assert residual <= 1e-10 and objective < 1e-18
        assert (
            solve_simplex(
                ((1 * scale, 3 * scale), (1 * scale, 3 * scale)), (2.5 * scale, 2.5 * scale)
            )[0]
            == weights
        )


@pytest.mark.parametrize("response,expected", [(0.0, (1.0, 0.0)), (4.0, (0.0, 1.0))])
def test_simplex_boundary_optima(response: float, expected: tuple[float, ...]) -> None:
    assert solve_simplex(((1.0, 3.0),), (response,))[0] == pytest.approx(expected, abs=1e-9)


def test_simplex_degenerate_ridge_and_failure_semantics() -> None:
    assert solve_simplex(((0.0, 0.0),), (0.0,))[0] == (0.5, 0.5)
    assert solve_simplex(((1.0, 1.0),), (1.0,), ridge=0.2)[0] == (0.5, 0.5)
    assert project_simplex((-10.0, 10.0)) == (0.0, 1.0)
    with pytest.raises(ContractError, match="did not converge"):
        solve_simplex(((1.0, 3.0),), (2.5,), maximum_iterations=1)
    with pytest.raises(ContractError, match="work bound"):
        solve_simplex(((1.0, 3.0),), (2.5,), work_cells=1)


def test_probability_boundary_roundoff_and_extreme_solver_fail_closed(case: Case) -> None:
    d = law(case)
    almost = replace(
        d, components=(replace(d.components[0], weight=0.25 + 5e-13), d.components[1])
    )
    assert mixture_cdf(almost, 1e8) == 1.0
    with pytest.raises(ContractError):
        solve_simplex(((1e308, 0.0), (-1e308, 0.0)), (0.0, 0.0))

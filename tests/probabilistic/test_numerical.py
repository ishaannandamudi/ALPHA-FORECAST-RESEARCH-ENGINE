"""Independent normal references, finite tails, empirical atom semantics and proper scores."""

import math
from dataclasses import replace

import pytest

from afre.probabilistic import (
    DistributionFamily as F,
)
from afre.probabilistic import (
    DistributionParameters,
    DistributionState,
    ScalePolicy,
    ScaleSpec,
    ThresholdRequest,
    cdf,
    conditional_variance,
    density,
    expected_value,
    quantile,
    survival,
    threshold_probability,
)
from afre.probabilistic import (
    ThresholdComparison as C,
)
from afre.probabilistic.distributions import normal_cdf
from afre.probabilistic.quantiles import empirical_quantile, normal_quantile
from afre.probabilistic.scale import estimate_scale, moments
from afre.probabilistic.scoring import (
    brier_score,
    empirical_crps,
    gaussian_crps,
    negative_log_likelihood,
    pinball_loss,
)
from afre.probabilistic.thresholds import event_outcome
from afre.schema import ContractError

NORMAL = DistributionParameters(F.GAUSSIAN_LOCATION_SCALE, 0.0, 1.0)
EMPIRICAL = DistributionParameters(
    F.EMPIRICAL_RESIDUAL, 0.0, math.sqrt(2), (-2.0, -1.0, 0.0, 1.0, 2.0)
)


@pytest.mark.parametrize(
    ("z", "reference"),
    [
        (0.0, 0.5),
        (1.0, 0.8413447460685429),
        (-1.0, 0.15865525393145707),
        (2.0, 0.9772498680518208),
        (3.0, 0.9986501019683699),
        (-8.0, 6.220960574271784e-16),
    ],
)
def test_normal_reference(z: float, reference: float) -> None:
    assert normal_cdf(z) == pytest.approx(reference, rel=1e-14, abs=1e-16)
    assert cdf(NORMAL, z) == normal_cdf(z)
    assert survival(NORMAL, z) + cdf(NORMAL, z) == pytest.approx(1.0, abs=1e-15)


@pytest.mark.parametrize(
    ("q", "reference"),
    [
        (0.5, 0.0),
        (0.1, -1.2815515655446004),
        (0.9, 1.2815515655446004),
        (0.025, -1.959963984540054),
        (0.975, 1.959963984540054),
        (1e-12, -7.034483825301131),
    ],
)
def test_normal_inverse_reference(q: float, reference: float) -> None:
    assert normal_quantile(q) == pytest.approx(reference, abs=3e-15)
    assert cdf(NORMAL, quantile(NORMAL, q)) == pytest.approx(q, abs=1e-15)


@pytest.mark.parametrize("z", [-1e308, -100.0, -9.0, 9.0, 100.0, 1e308])
def test_extreme_tail_stability(z: float) -> None:
    values = [threshold_probability(NORMAL, ThresholdRequest(z, c)) for c in C]
    assert all(math.isfinite(p) and 0 <= p <= 1 for p in values)
    assert cdf(NORMAL, z, True) == cdf(NORMAL, z)
    assert survival(NORMAL, z, True) == survival(NORMAL, z)
    if z == 9.0:
        assert survival(NORMAL, z) > 0 and 1 - cdf(NORMAL, z) == 0
    assert gaussian_crps(NORMAL, z) >= 0


@pytest.mark.parametrize(
    ("comparison", "probability", "outcome"),
    [(C.GT, 0.4, False), (C.GE, 0.6, True), (C.LT, 0.4, False), (C.LE, 0.6, True)],
)
def test_empirical_atoms(comparison: C, probability: float, outcome: bool) -> None:
    request = ThresholdRequest(0.0, comparison)
    assert threshold_probability(EMPIRICAL, request) == probability
    assert event_outcome(0.0, request) is outcome


def test_shifted_atom_rounding_and_degenerate_state() -> None:
    distribution = DistributionParameters(
        F.EMPIRICAL_RESIDUAL, 0.1, 0.0, (0.2,), state=DistributionState.DEGENERATE
    )
    atom = 0.1 + 0.2
    assert cdf(distribution, atom) == 1 and cdf(distribution, atom, True) == 0
    assert survival(distribution, atom) == 0 and survival(distribution, atom, True) == 1
    assert expected_value(distribution) == atom and quantile(distribution, 0.5) == atom
    assert conditional_variance(distribution) == 0
    assert empirical_crps(distribution, atom) == pytest.approx(0.0, abs=1e-16)


@pytest.mark.parametrize(
    ("q", "expected"), [(0.1, -1.6), (0.25, -1.0), (0.5, 0.0), (0.75, 1.0), (0.9, 1.6)]
)
def test_declared_type7_quantiles(q: float, expected: float) -> None:
    assert empirical_quantile(EMPIRICAL.samples, q) == pytest.approx(expected)
    assert quantile(EMPIRICAL, q) == pytest.approx(expected)


def test_population_std_mad_fixed_and_zero() -> None:
    values = (-2.0, -1.0, 0.0, 1.0, 2.0)
    assert moments(values) == (0.0, 0.0, math.sqrt(2), 1.0)
    assert estimate_scale(values, ScaleSpec(ScalePolicy.TRAIN_RESIDUAL_STD), True) == math.sqrt(
        2
    )
    assert (
        estimate_scale(
            values,
            ScaleSpec(ScalePolicy.TRAIN_RESIDUAL_MAD_SCALED, mad_consistency_factor=2.0),
            True,
        )
        == 2
    )
    assert estimate_scale((1.0, 1.0), ScaleSpec(ScalePolicy.FIXED_SCALE, 0.2), True) == 0.2
    assert moments((0.1,) * 9)[2:] == (0.0, 0.0)
    with pytest.raises(ContractError, match="zero"):
        estimate_scale((1.0, 1.0), ScaleSpec(ScalePolicy.TRAIN_RESIDUAL_STD), True)
    assert estimate_scale((1.0, 1.0), ScaleSpec(ScalePolicy.TRAIN_RESIDUAL_STD), False) == 0


def test_known_proper_scores() -> None:
    assert negative_log_likelihood(NORMAL, 0.0) == pytest.approx(0.9189385332046727)
    assert negative_log_likelihood(replace(NORMAL, scale=0.01), 0.0) < 0
    assert gaussian_crps(NORMAL, 0.0) == pytest.approx(0.23369497725510913, abs=1e-15)
    assert gaussian_crps(replace(NORMAL, location=0.1, scale=0.4), 0.0) == pytest.approx(
        0.10339992515976162, abs=1e-15
    )
    assert pinball_loss(0.1, 2.0, 5.0) == pytest.approx(0.3)
    assert pinball_loss(0.1, 5.0, 2.0) == pytest.approx(2.7)
    assert brier_score(0.8, True) == pytest.approx(0.04)
    assert brier_score(0.8, False) == pytest.approx(0.64)
    assert density(NORMAL, 0.0) == pytest.approx(1 / math.sqrt(2 * math.pi))
    assert expected_value(NORMAL) == 0 and conditional_variance(NORMAL) == 1
    assert expected_value(EMPIRICAL) == 0 and conditional_variance(EMPIRICAL) == pytest.approx(
        2
    )


@pytest.mark.parametrize("truth", [-10.0, -1.0, 0.0, 0.7, 10.0])
def test_empirical_crps_independent_pairwise_definition(truth: float) -> None:
    atoms = EMPIRICAL.samples
    n = len(atoms)
    reference = sum(abs(a - truth) for a in atoms) / n - sum(
        abs(a - b) for a in atoms for b in atoms
    ) / (2 * n * n)
    assert empirical_crps(EMPIRICAL, truth) == pytest.approx(reference, abs=2e-15)


def test_cdf_monotonicity_and_complements() -> None:
    for distribution in (EMPIRICAL, NORMAL):
        values = tuple(cdf(distribution, float(i) / 10) for i in range(-100, 101))
        assert values == tuple(sorted(values))
        for x in (-2.0, 0.0, 2.0):
            assert cdf(distribution, x) + survival(distribution, x) == pytest.approx(1)
            assert cdf(distribution, x, True) + survival(
                distribution, x, True
            ) == pytest.approx(1)


@pytest.mark.parametrize("q", [0.0, 1.0, -0.1, float("nan"), float("inf")])
def test_bad_quantile_domains(q: float) -> None:
    for function in (
        normal_quantile,
        lambda v: quantile(EMPIRICAL, v),
        lambda v: pinball_loss(v, 0.0, 1.0),
    ):
        with pytest.raises(ContractError):
            function(q)


def test_unsupported_domains_and_overflow() -> None:
    for fn in (negative_log_likelihood, gaussian_crps, density):
        with pytest.raises(ContractError):
            fn(EMPIRICAL, 0.0)
    with pytest.raises(ContractError):
        empirical_crps(NORMAL, 0.0)
    with pytest.raises(ContractError):
        empirical_quantile((1.0, 0.0), 0.5)
    with pytest.raises(ContractError):
        moments(())
    with pytest.raises(ContractError):
        normal_cdf(float("nan"))
    with pytest.raises(ContractError):
        brier_score(1.1, True)
    with pytest.raises(ContractError):
        negative_log_likelihood(NORMAL, 1e308)

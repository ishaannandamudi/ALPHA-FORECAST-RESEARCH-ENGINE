"""Independent small numerical oracles, finite bounds and explicit undefined states."""

import math
from dataclasses import replace

import pytest

from afre.probabilistic.artifacts import DistributionParameters
from afre.probabilistic.schema import DistributionFamily, DistributionState
from afre.schema import ContractError
from afre.statistical_models.artifacts import DesignMatrix
from afre.uncertainty import IdentifiabilityStatus, UncertaintyType
from afre.uncertainty.covariance import inverse_crossproduct, quadratic_variance
from afre.uncertainty.decomposition import close_variance
from afre.uncertainty.diagnostics import buckets_for, error_for
from afre.uncertainty.evaluation import coverage_for
from afre.uncertainty.moments import entropy, mixture_terms, variance, weighted_spread
from afre.uncertainty.parameter import prediction_design
from afre.uncertainty.sources import source_for
from examples.uncertainty_demo import component
from examples.uncertainty_oracles import ols_covariance, prediction_variance
from tests.uncertainty.conftest import Case


@pytest.mark.parametrize("sigma", [0.001, 0.2, 1.0, 3.5])
def test_gaussian_exact(sigma: float) -> None:
    law = DistributionParameters(DistributionFamily.GAUSSIAN_LOCATION_SCALE, 2.0, sigma)
    assert variance(law) == sigma * sigma


@pytest.mark.parametrize("atoms", [(1.0,), (1.0, 3.0), (-3.0, 0.0, 4.0, 7.0)])
def test_empirical_population_variance(atoms: tuple[float, ...]) -> None:
    law = DistributionParameters(
        DistributionFamily.EMPIRICAL_RESIDUAL,
        0.0,
        1.0,
        samples=atoms,
        state=DistributionState.DEGENERATE
        if min(atoms) == max(atoms)
        else DistributionState.REGULAR,
    )
    mean = sum(atoms) / len(atoms)
    assert variance(law) == pytest.approx(sum((a - mean) ** 2 for a in atoms) / len(atoms))
    assert variance(None) is None


@pytest.mark.parametrize(
    "weights,values",
    [((0.25, 0.75), (1.0, 5.0)), ((0.0, 1.0), (-9.0, 3.0)), ((0.5, 0.5), (0.0, 0.0))],
)
def test_regime_and_expert_spread(
    weights: tuple[float, ...], values: tuple[float, ...]
) -> None:
    mean = sum(w * v for w, v in zip(weights, values, strict=True))
    expected = sum(w * (v - mean) ** 2 for w, v in zip(weights, values, strict=True))
    assert weighted_spread(weights, values) == pytest.approx((mean, expected))
    assert entropy(weights) == pytest.approx(-sum(w * math.log(w) for w in weights if w))


@pytest.mark.parametrize(
    "weights,values",
    [((), ()), ((0.5,), (1.0, 2.0)), ((-1.0, 2.0), (0.0, 1.0)), ((0.5, 0.6), (0.0, 1.0))],
)
def test_invalid_weights(weights: tuple[float, ...], values: tuple[float, ...]) -> None:
    with pytest.raises(ContractError):
        weighted_spread(weights, values)


def test_mixture_independent_identity(case: Case) -> None:
    from afre.mixture import MixtureForecast

    law = case.repo.get(MixtureForecast, case.result("mixture").forecast_id).distribution
    assert law is not None
    templates = law.components
    for weight in (0.25, 0.5, 0.75):
        current = replace(
            law,
            components=(
                replace(
                    templates[0],
                    weight=weight,
                    distribution=DistributionParameters(
                        DistributionFamily.GAUSSIAN_LOCATION_SCALE, 1.0, 2.0
                    ),
                ),
                replace(
                    templates[1],
                    weight=1 - weight,
                    distribution=DistributionParameters(
                        DistributionFamily.GAUSSIAN_LOCATION_SCALE, 5.0, 3.0
                    ),
                ),
            ),
        )
        mean = weight + (1 - weight) * 5
        within = weight * 4 + (1 - weight) * 9
        between = weight * (1 - mean) ** 2 + (1 - weight) * (5 - mean) ** 2
        assert mixture_terms(current) == pytest.approx((within + between, within, between))
        assert variance(current) == pytest.approx(within + between)


@pytest.mark.parametrize(
    "design",
    [
        ((1.0, 0.0), (1.0, 1.0), (1.0, 2.0), (1.0, 3.0)),
        (
            (1.0, -1.0, 2.0),
            (1.0, 2.0, -3.0),
            (1.0, 0.0, 1.0),
            (1.0, 3.0, 0.0),
            (1.0, -2.0, 1.0),
        ),
    ],
)
def test_qr_independent_covariance(design: tuple[tuple[float, ...], ...]) -> None:
    y = tuple(float(i % 3) + 0.1 * i for i in range(len(design)))
    expected, sigma = ols_covariance(design, y)
    inverse, condition = inverse_crossproduct(design, 1e-10, 1e10)
    assert condition >= 1
    actual = tuple(tuple(sigma * v for v in row) for row in inverse)
    assert (
        max(
            abs(a - b)
            for r, s in zip(actual, expected, strict=True)
            for a, b in zip(r, s, strict=True)
        )
        < 1e-12
    )
    x = design[-1]
    assert quadratic_variance(x, actual) == pytest.approx(
        prediction_variance(x, expected), abs=1e-12
    )


@pytest.mark.parametrize(
    "design",
    [
        (),
        ((),),
        ((1.0,), (1.0, 2.0)),
        ((1.0, 1.0), (1.0, 1.0)),
        ((0.0,), (0.0,)),
        ((1.0, 1e-11), (1.0, 1.000001e-11)),
    ],
)
def test_rank_shape_failure(design: tuple[tuple[float, ...], ...]) -> None:
    with pytest.raises(ContractError):
        inverse_crossproduct(design, 1e-10, 1e10)


def test_covariance_condition_and_negative_quadratic() -> None:
    with pytest.raises(ContractError, match="ill-conditioned"):
        inverse_crossproduct(((1.0, 0.0), (1.0, 1.0)), 1e-10, 1.0)
    with pytest.raises(ContractError):
        quadratic_variance((1.0,), ((-1.0,),))
    with pytest.raises(ContractError):
        quadratic_variance((), ())
    assert quadratic_variance((3.0,), ((2.0,),)) == 18.0


@pytest.mark.parametrize("total,parts", [(4.0, (1.0, 3.0)), (0.0, (0.0,)), (5.0, (2.0,))])
def test_partial_closure(total: float, parts: tuple[float, ...]) -> None:
    assert close_variance(total, parts, 1e-10) == total - sum(parts)


@pytest.mark.parametrize(
    "total,parts", [(-1.0, ()), (1.0, (-1.0,)), (1.0, (1.001,)), (1.0, (1.0 + 1e-12,))]
)
def test_negative_residual_never_clamped(total: float, parts: tuple[float, ...]) -> None:
    with pytest.raises(ContractError):
        close_variance(total, parts, 1e-10)


def test_native_covariance_oracle(case: Case) -> None:
    covariance = case.fixture.covariances[0]
    matrix = case.repo.get(DesignMatrix, covariance.matrix_id)
    expected, sigma = ols_covariance(
        tuple((1.0, *r.values) for r in matrix.rows), tuple(r.response for r in matrix.rows)
    )
    assert covariance.degrees_of_freedom == len(matrix.rows) - covariance.design_rank
    assert covariance.residual_variance == pytest.approx(sigma, abs=1e-12)
    assert (
        max(
            abs(a - b)
            for r, s in zip(expected, covariance.covariance, strict=True)
            for a, b in zip(r, s, strict=True)
        )
        < 1e-12
    )
    result = case.result()
    x = prediction_design(case.repo, source_for(case.repo, result.forecast_id), covariance)
    assert component(result, UncertaintyType.PARAMETER).value == pytest.approx(
        prediction_variance(x, expected), abs=1e-12
    )


def test_coverage_buckets_correlations_oracle(case: Case) -> None:
    from afre.uncertainty import UncertaintyEvaluationSpec

    evaluated = case.engine.evaluate(
        case.fixture.results("gaussian"), UncertaintyEvaluationSpec(bucket_count=2), 100, 100
    )
    pairs = tuple(
        replace(p, prediction=0.0, truth=float(i + 1), variance=float(i + 1))
        for i, p in enumerate(evaluated.pairs)
    )
    buckets = buckets_for(pairs, 2, 2)
    assert tuple(b.sample_ids for b in buckets) == tuple(
        tuple(sorted(p.sample_id for p in pairs[i : i + 2])) for i in (0, 2)
    )
    diagnostic = error_for(pairs, buckets, 2)
    assert diagnostic.absolute_pearson.value == pytest.approx(1.0)
    assert diagnostic.absolute_spearman.value == pytest.approx(1.0)
    y = tuple(p.truth**2 for p in pairs)
    xm, ym = 2.5, sum(y) / 4
    expected = sum(
        (p.variance - xm) * (v - ym)
        for p, v in zip(pairs, y, strict=True)
        if p.variance is not None
    ) / math.sqrt(sum((i - xm) ** 2 for i in (1, 2, 3, 4)) * sum((v - ym) ** 2 for v in y))
    assert diagnostic.squared_pearson.value == pytest.approx(expected)
    assert diagnostic.monotonic_bucket_error is True
    constant = tuple(replace(p, variance=1.0) for p in pairs)
    tied = buckets_for(constant, 2, 2)
    assert tuple(p.sample_ids for p in tied) == tuple(
        p.sample_ids for p in buckets_for(tuple(reversed(constant)), 2, 2)
    )
    assert error_for(constant, tied, 2).absolute_pearson.value is None
    assert error_for(pairs[:1], buckets_for(pairs[:1], 3, 2), 2).absolute_pearson.value is None
    assert coverage_for((), 0.8, 2).status is IdentifiabilityStatus.UNAVAILABLE
    assert buckets_for((), 2, 2) == ()
    assert (
        coverage_for(evaluated.pairs[:1], 0.8, 2).status
        is IdentifiabilityStatus.INSUFFICIENT_DATA
    )

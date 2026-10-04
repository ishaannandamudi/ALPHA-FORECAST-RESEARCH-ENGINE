"""Known-coefficient, objective, rank and convergence numerical fixtures."""

import hashlib
import math
from dataclasses import replace

import pytest

from afre.forecast import ForecastOrigin
from afre.ids import InstrumentId
from afre.schema import ContractError
from afre.statistical_models import (
    DesignMatrix,
    InterceptPolicy,
    ModelBounds,
    ModelFamily,
    NonconvergencePolicy,
    TrainingMatrixRow,
)
from afre.statistical_models.elastic import coordinate_descent
from afre.statistical_models.fitting import fit_values
from afre.statistical_models.linear_algebra import dot, finite, householder_qr, total
from tests.statistical_models.conftest import ModelCase


def identity(domain: str, value: int = 0) -> str:
    return f"afre.{domain}:1.0:" + hashlib.sha256(str(value).encode()).hexdigest()


def matrix_for(
    case: ModelCase, x: tuple[tuple[float, ...], ...], y: tuple[float, ...]
) -> DesignMatrix:
    spec = case.spec()
    rows = tuple(
        TrainingMatrixRow(
            identity("r_sample", i),
            ForecastOrigin(
                InstrumentId("numeric", str(i)), 10, 10, "s", "b", identity("universe_manifest")
            ),
            identity("fs_join_result", i),
            (),
            row,
            identity("target_vintage", i),
            value,
            20,
        )
        for i, (row, value) in enumerate(zip(x, y, strict=True))
    )
    columns = tuple(identity("feature_definition", j) for j in range(len(x[0])))
    return DesignMatrix(
        spec.fingerprint,
        case.dataset.fingerprint,
        case.split.fingerprint,
        spec.fold_id,
        spec.target.fingerprint,
        columns,
        rows,
        (),
        (),
        40,
        40,
    )


def test_householder_known_coefficients_and_pivoting() -> None:
    matrix = tuple((1.0, float(i), float((i * 7) % 11)) for i in range(30))
    expected = (3.0, -2.0, 0.5)
    response = tuple(dot(row, expected) for row in matrix)
    result = householder_qr(matrix, response, 1e-12, 1e12)
    assert result.coefficients == pytest.approx(expected, abs=1e-12)
    assert result.rank == 3 and result.condition_proxy >= 1
    reversed_result = householder_qr(
        tuple(reversed(matrix)), tuple(reversed(response)), 1e-12, 1e12
    )
    assert reversed_result.coefficients == pytest.approx(expected, abs=1e-12)


@pytest.mark.parametrize(
    "matrix",
    (
        ((1.0, 2.0), (2.0, 4.0), (3.0, 6.0)),
        ((0.0,), (0.0,)),
        ((1.0, 1.0),),
        ((1.0, 0.0), (0.0, 1e-14)),
    ),
)
def test_rank_deficiency(matrix: tuple[tuple[float, ...], ...]) -> None:
    with pytest.raises(ContractError, match="rank|tall"):
        householder_qr(matrix, (1.0,) * len(matrix), 1e-12, 1e12)


def test_condition_proxy_limit() -> None:
    with pytest.raises(ContractError, match="ill-conditioned"):
        householder_qr(((1.0, 0.0), (0.0, 0.001)), (1.0, 1.0), 1e-12, 10.0)


@pytest.mark.parametrize("value", (math.nan, math.inf, -math.inf))
def test_nonfinite_and_accumulation(value: float) -> None:
    with pytest.raises(ContractError):
        finite(value)
    with pytest.raises(ContractError):
        householder_qr(((value,),), (1.0,), 1e-12, 1e12)
    with pytest.raises(ContractError):
        coordinate_descent(((1.0,),), (value,), 0.1, 0.1, 10, 1e-8, False)


def test_explicit_overflow() -> None:
    with pytest.raises(ContractError, match="overflow"):
        total([1e308, 1e308])
    with pytest.raises(ContractError, match="overflow"):
        dot((1e308,), (1e308,))
    with pytest.raises(ContractError, match="shape"):
        dot((1.0,), ())


def test_ols_ridge_intercept_and_zero_lambda(model_case: ModelCase) -> None:
    c = model_case
    x = tuple((float(i),) for i in (-2, -1, 0, 1, 2))
    y = tuple(3.0 + 2.0 * row[0] for row in x)
    matrix = matrix_for(c, x, y)
    ols = fit_values(c.spec(), matrix, ModelBounds())
    assert ols.intercept == pytest.approx(3.0, abs=1e-12)
    assert ols.coefficients == pytest.approx((2.0,), abs=1e-12)
    ridge_spec = c.spec(ModelFamily.RIDGE_REGRESSION)
    ridge = fit_values(replace(ridge_spec, l2_penalty=10.0), matrix, ModelBounds())
    assert ridge.intercept == pytest.approx(3.0, abs=1e-12)
    assert ridge.coefficients == pytest.approx((1.0,), abs=1e-12)
    zero = fit_values(replace(ridge_spec, l2_penalty=0.0), matrix, ModelBounds())
    assert zero == ols
    penalized = fit_values(
        replace(ridge_spec, l2_penalty=10.0, regularize_intercept=True), matrix, ModelBounds()
    )
    assert penalized.intercept == pytest.approx(1.0, abs=1e-12)
    assert penalized.coefficients == pytest.approx((1.0,), abs=1e-12)
    no_intercept = fit_values(
        replace(c.spec(), intercept=InterceptPolicy.NONE), matrix, ModelBounds()
    )
    assert no_intercept.intercept == 0.0
    assert no_intercept.coefficients == pytest.approx((2.0,), abs=1e-12)


@pytest.mark.parametrize(
    "family,penalty,expected",
    (
        (ModelFamily.UNCONDITIONAL_MEAN, 0.0, 2.0),
        (ModelFamily.UNCONDITIONAL_MEDIAN, 0.0, 1.0),
        (ModelFamily.REFERENCE_VALUE, 0.0, 0.0),
    ),
)
def test_exact_reference_statistics(
    model_case: ModelCase, family: ModelFamily, penalty: float, expected: float
) -> None:
    matrix = matrix_for(model_case, ((0.0,), (1.0,), (2.0,)), (0.0, 1.0, 5.0))
    result = fit_values(model_case.spec(family), matrix, ModelBounds())
    assert result.intercept == expected and result.reference_value == expected
    assert result.coefficients == (0.0,)


def test_lasso_and_elastic_objective_and_sparsity() -> None:
    # Orthogonal columns with squared norms 4; rho=(8,0).
    matrix = ((1.0, 1.0), (1.0, -1.0), (-1.0, 1.0), (-1.0, -1.0))
    y = (2.0, 2.0, -2.0, -2.0)
    lasso = coordinate_descent(matrix, y, 4.0, 0.0, 100, 1e-12, False)
    elastic = coordinate_descent(matrix, y, 4.0, 4.0, 100, 1e-12, False)
    assert lasso.coefficients == (1.5, 0.0)
    assert elastic.coefficients == (0.75, 0.0)
    assert lasso.converged and elastic.converged
    negative = coordinate_descent(matrix, tuple(-v for v in y), 4.0, 0.0, 100, 1e-12, False)
    assert negative.coefficients == (-1.5, 0.0)
    constant = coordinate_descent(((0.0,), (0.0,)), (1.0, 2.0), 1.0, 0.0, 10, 1e-12, False)
    assert constant.coefficients == (0.0,) and constant.converged


def test_nonconvergence_explicit(model_case: ModelCase) -> None:
    c = model_case
    matrix = matrix_for(c, ((1.0,), (2.0,), (3.0,)), (3.0, 5.0, 7.0))
    spec = replace(c.spec(ModelFamily.ELASTIC_NET), max_iterations=1, tolerance=1e-15)
    with pytest.raises(ContractError, match="did not converge"):
        fit_values(spec, matrix, ModelBounds())
    result = fit_values(
        replace(spec, nonconvergence=NonconvergencePolicy.RETURN_NONCONVERGED),
        matrix,
        ModelBounds(),
    )
    assert not result.diagnostics.converged and result.diagnostics.iterations == 1


@pytest.mark.parametrize(
    "bounds",
    (
        ModelBounds(samples=1),
        ModelBounds(features=1, coefficients=1),
        ModelBounds(iterations=1),
        ModelBounds(dense_cells=1),
    ),
)
def test_fit_bounds(model_case: ModelCase, bounds: ModelBounds) -> None:
    matrix = matrix_for(model_case, ((1.0,), (2.0,), (3.0,)), (3.0, 5.0, 7.0))
    with pytest.raises(ContractError, match="bound"):
        fit_values(model_case.spec(), matrix, bounds)

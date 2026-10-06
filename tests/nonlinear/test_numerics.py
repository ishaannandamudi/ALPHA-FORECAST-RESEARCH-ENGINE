"""Independent linear design oracles, exact coefficient/value diagnostics and scaling."""

from dataclasses import replace

import pytest

from afre.nonlinear import (
    InteractionDefinition,
    InteractionMatrix,
    InteractionSet,
    InteractionTrainingRow,
    InteractionTransform,
    NonlinearBounds,
    NonlinearFamily,
    NonlinearModelSpec,
    NonlinearPreprocessing,
    TransformParameters,
)
from afre.nonlinear.definitions import output_unit
from afre.nonlinear.fitting import fit_model
from afre.schema import ContractError
from tests.nonlinear.conftest import Case
from tests.nonlinear.test_transforms import feature


def oracle_matrix(
    spec: NonlinearModelSpec, values: tuple[tuple[float, ...], ...], response: tuple[float, ...]
) -> InteractionMatrix:
    rows = tuple(
        InteractionTrainingRow(
            spec.fingerprint,
            "afre.r_sample:1.0:" + f"{i + 1:064x}",
            "afre.nl_input:1.0:" + f"{i + 1:064x}",
            (),
            x,
            "afre.target_vintage:1.0:" + f"{i + 1:064x}",
            y,
            40,
        )
        for i, (x, y) in enumerate(zip(values, response, strict=True))
    )
    return InteractionMatrix(spec.fingerprint, spec.fold_id, rows, spec.columns, (), 40, 40)


def test_linear_on_product_coefficients(case: Case) -> None:
    x, y = feature("x"), feature("y")
    definition = InteractionDefinition(
        "xy",
        (x, y),
        InteractionTransform.PRODUCT,
        TransformParameters(),
        "xy",
        output_unit(InteractionTransform.PRODUCT, (x, y)),
    )
    spec = NonlinearModelSpec(
        InteractionSet((definition,), case.fixture.specs[0].target),
        NonlinearFamily.LINEAR_ON_INTERACTIONS,
        (),
        case.fixture.specs[0].fold_id,
        40,
        0,
    )
    values = tuple((float(i),) for i in range(1, 7))
    matrix = oracle_matrix(spec, values, tuple(1.0 + 3.0 * r[0] for r in values))
    model = fit_model(spec, matrix, 40, 40, 40, NonlinearBounds())
    assert model.intercept == pytest.approx(1.0, abs=1e-12)
    assert model.coefficients == pytest.approx((3.0,), abs=1e-12)
    assert model.training_squared_error < 1e-25


def test_linear_plus_cross_expected_prediction(case: Case) -> None:
    x, y = feature("x"), feature("y")
    definition = InteractionDefinition(
        "xy",
        (x, y),
        InteractionTransform.PRODUCT,
        TransformParameters(),
        "xy",
        output_unit(InteractionTransform.PRODUCT, (x, y)),
    )
    spec = NonlinearModelSpec(
        InteractionSet((definition,), case.fixture.specs[0].target),
        NonlinearFamily.LINEAR_PLUS_INTERACTIONS,
        (x, y),
        case.fixture.specs[0].fold_id,
        40,
        0,
    )
    values = tuple(
        tuple(
            {x.fingerprint: a, y.fingerprint: b}[f.fingerprint] for f in spec.original_features
        )
        + (a * b,)
        for a, b in ((1.0, 1.0), (1.0, 2.0), (2.0, 1.0), (2.0, 2.0), (3.0, 1.0), (1.0, 3.0))
    )
    truth = tuple(
        1 + 2 * a - 3 * b + 4 * a * b
        for a, b in ((1, 1), (1, 2), (2, 1), (2, 2), (3, 1), (1, 3))
    )
    matrix = oracle_matrix(spec, values, tuple(float(y) for y in truth))
    model = fit_model(spec, matrix, 40, 40, 40, NonlinearBounds())
    expected = tuple(2.0 if f == x else -3.0 for f in spec.original_features) + (4.0,)
    assert model.intercept == pytest.approx(1.0, abs=1e-12)
    assert model.coefficients == pytest.approx(expected, abs=1e-12)
    assert model.intercept + sum(
        b * v for b, v in zip(model.coefficients, values[3], strict=True)
    ) == pytest.approx(15.0)


def test_constant_scaling_rejects_and_fixed_ridge_is_finite(case: Case) -> None:
    source = case.fixture.specs[0]
    values = tuple((1.0,) * len(source.columns) for _ in range(12))
    spec = replace(source, preprocessing=NonlinearPreprocessing.STANDARDIZE)
    matrix = oracle_matrix(spec, values, tuple(float(i) for i in range(12)))
    with pytest.raises(ContractError, match="zero TRAIN scale"):
        fit_model(spec, matrix, 40, 40, 40, NonlinearBounds())
    raw = replace(source, ridge_penalty=1.0)
    model = fit_model(
        raw, replace(matrix, spec_id=raw.fingerprint), 40, 40, 40, NonlinearBounds()
    )
    assert model.intercept == pytest.approx(5.5)
    assert model.coefficients == pytest.approx((0.0,) * len(raw.columns), abs=1e-12)

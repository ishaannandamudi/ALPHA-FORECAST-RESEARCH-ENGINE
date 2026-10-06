"""Independent arithmetic fixtures and explicit invalid/missing/undefined policies."""

import math
from dataclasses import replace

import pytest

from afre.nonlinear import (
    DenominatorPolicy,
    InteractionDefinition,
    InteractionMissingPolicy,
    InteractionTransform,
    KnotPolicy,
    ScalarFeatureDefinition,
    ScalarSourceKind,
    TransformParameters,
)
from afre.nonlinear.definitions import output_unit
from afre.nonlinear.transforms import piecewise, transform_value
from afre.schema import ContractError
from afre.serialization import canonical_json, deserialize


def feature(name: str, unit: str = "1") -> ScalarFeatureDefinition:
    return ScalarFeatureDefinition(
        ScalarSourceKind.EXTERNAL_SIGNAL,
        ("neutral", "1", "1.0", name, "1", "numeric"),
        "value",
        unit,
    )


def definition(
    transform: InteractionTransform,
    params: TransformParameters | None = None,
    missing: InteractionMissingPolicy = InteractionMissingPolicy.FAIL,
) -> InteractionDefinition:
    binary = transform in (
        InteractionTransform.PRODUCT,
        InteractionTransform.RATIO,
        InteractionTransform.DIFFERENCE,
        InteractionTransform.ABS_DIFFERENCE,
    )
    inputs = (feature("x"), feature("y")) if binary else (feature("x"),)
    return InteractionDefinition(
        "test",
        inputs,
        transform,
        params or TransformParameters(),
        "test",
        output_unit(transform, inputs),
        missing,
        7.0 if missing is InteractionMissingPolicy.DECLARED_FALLBACK else None,
    )


@pytest.mark.parametrize(
    ("transform", "values", "expected"),
    [
        (InteractionTransform.IDENTITY, (2.0,), 2.0),
        (InteractionTransform.PRODUCT, (2.0, 3.0), 6.0),
        (InteractionTransform.DIFFERENCE, (2.0, 3.0), -1.0),
        (InteractionTransform.ABS_DIFFERENCE, (2.0, 3.0), 1.0),
        (InteractionTransform.SQUARE, (-2.0,), 4.0),
        (InteractionTransform.CUBE, (-2.0,), -8.0),
        (InteractionTransform.LOG1P_SIGNED, (3.0,), math.log(4)),
        (InteractionTransform.LOG1P_SIGNED, (-3.0,), -math.log(4)),
        (InteractionTransform.LOG1P_SIGNED, (0.0,), 0.0),
    ],
)
def test_arithmetic(
    transform: InteractionTransform, values: tuple[float, ...], expected: float
) -> None:
    assert transform_value(definition(transform), values) == pytest.approx((expected, False))


@pytest.mark.parametrize("policy", list(DenominatorPolicy))
def test_denominator(policy: DenominatorPolicy) -> None:
    d = definition(
        InteractionTransform.RATIO,
        TransformParameters(
            denominator=policy,
            epsilon=0.5 if policy is DenominatorPolicy.EPSILON_FLOOR else None,
        ),
    )
    if policy is DenominatorPolicy.FAIL_ON_ZERO:
        with pytest.raises(ContractError, match="zero"):
            transform_value(d, (2.0, 0.0))
    else:
        assert transform_value(d, (2.0, 0.0)) == (
            (4.0, False) if policy is DenominatorPolicy.EPSILON_FLOOR else (None, False)
        )
    assert transform_value(d, (2.0, -2.0)) == (-1.0, False)
    if policy is DenominatorPolicy.EPSILON_FLOOR:
        assert transform_value(d, (2.0, -0.1)) == (-4.0, False)


@pytest.mark.parametrize("policy", list(InteractionMissingPolicy))
def test_missing(policy: InteractionMissingPolicy) -> None:
    d = definition(InteractionTransform.PRODUCT, missing=policy)
    if policy is InteractionMissingPolicy.FAIL:
        with pytest.raises(ContractError, match="missing"):
            transform_value(d, (None, 3.0))
    else:
        assert transform_value(d, (None, 3.0)) == (
            (7.0, True)
            if policy is InteractionMissingPolicy.DECLARED_FALLBACK
            else (None, False)
        )


@pytest.mark.parametrize(
    ("x", "expected"),
    [(-1.0, 0.0), (0.0, 0.0), (0.5, 1.0), (1.0, 2.0), (2.0, 3.0), (3.0, 4.0), (4.0, 4.0)],
)
def test_piecewise(x: float, expected: float) -> None:
    d = definition(
        InteractionTransform.PIECEWISE_LINEAR,
        TransformParameters(
            knot_policy=KnotPolicy.FIXED, knots=(0.0, 1.0, 3.0), ordinates=(0.0, 2.0, 4.0)
        ),
    )
    assert transform_value(d, (x,)) == (expected, False)


@pytest.mark.parametrize(("x", "expected"), [(-5.0, -1.0), (0.0, 0.0), (5.0, 1.0)])
def test_clipping(x: float, expected: float) -> None:
    d = definition(
        InteractionTransform.CLIPPED_LINEAR,
        TransformParameters(clip_lower=-1.0, clip_upper=1.0),
    )
    assert transform_value(d, (x,)) == (expected, False)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite(value: float) -> None:
    with pytest.raises(ContractError):
        transform_value(definition(InteractionTransform.IDENTITY), (value,))


@pytest.mark.parametrize(
    "transform",
    [InteractionTransform.PRODUCT, InteractionTransform.SQUARE, InteractionTransform.CUBE],
)
def test_overflow(transform: InteractionTransform) -> None:
    with pytest.raises(ContractError, match="overflow|nonfinite"):
        transform_value(
            definition(transform),
            (1e308, 1e308) if transform is InteractionTransform.PRODUCT else (1e308,),
        )


def test_units_and_order() -> None:
    x, y = feature("x", "USD"), feature("y", "shares")
    d = InteractionDefinition(
        "xy",
        (x, y),
        InteractionTransform.PRODUCT,
        TransformParameters(),
        "xy",
        "(USD*shares)" if x.fingerprint < y.fingerprint else "(shares*USD)",
    )
    assert replace(d, inputs=tuple(reversed(d.inputs))) == d
    assert output_unit(InteractionTransform.RATIO, (x, y)) == "(USD/shares)"
    assert output_unit(InteractionTransform.SQUARE, (x,)) == "(USD^2)"
    assert deserialize(canonical_json(d)) == d
    with pytest.raises(ContractError, match="unit"):
        replace(d, unit="1")
    with pytest.raises(ContractError):
        output_unit(InteractionTransform.LOG1P_SIGNED, (x,))
    with pytest.raises(ContractError):
        output_unit(InteractionTransform.DIFFERENCE, (x, y))


def test_parameter_failures() -> None:
    with pytest.raises(ContractError):
        definition(InteractionTransform.RATIO)
    with pytest.raises(ContractError):
        definition(InteractionTransform.IDENTITY, TransformParameters(epsilon=0.1))
    with pytest.raises(ContractError):
        TransformParameters(knots=(1.0, 1.0))
    with pytest.raises(ContractError):
        TransformParameters(quantile_levels=(0.5, 0.1))
    with pytest.raises(ContractError):
        definition(InteractionTransform.CLIPPED_LINEAR)
    with pytest.raises(ContractError):
        definition(InteractionTransform.PIECEWISE_LINEAR)
    with pytest.raises(ContractError):
        piecewise(1.0, (0.0, 0.0), (1.0, 2.0))
    with pytest.raises(ContractError):
        transform_value(definition(InteractionTransform.IDENTITY), (1.0, 2.0))

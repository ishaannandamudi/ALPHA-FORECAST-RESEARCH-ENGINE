"""Finite pure arithmetic; fixed clamp extrapolation and explicit denominator behavior."""

import math

from afre.nonlinear.definitions import InteractionDefinition
from afre.nonlinear.schema import (
    DenominatorPolicy,
    InteractionMissingPolicy,
    InteractionTransform,
)
from afre.schema import ContractError, require
from afre.statistical_models.linear_algebra import finite


def piecewise(value: float, knots: tuple[float, ...], ordinates: tuple[float, ...]) -> float:
    require(
        2 <= len(knots) == len(ordinates)
        and all(a < b for a, b in zip(knots, knots[1:], strict=False)),
        "piecewise knot shape",
    )
    if value <= knots[0]:
        return ordinates[0]
    if value >= knots[-1]:
        return ordinates[-1]
    index = next(i for i in range(len(knots) - 1) if knots[i] <= value <= knots[i + 1])
    fraction = finite((value - knots[index]) / (knots[index + 1] - knots[index]))
    return finite(
        ordinates[index] + finite(fraction * finite(ordinates[index + 1] - ordinates[index]))
    )


def transform_value(
    definition: InteractionDefinition,
    values: tuple[float | None, ...],
    fitted_knots: tuple[float, ...] = (),
) -> tuple[float | None, bool]:
    require(len(values) == len(definition.inputs), "transform input arity")
    if any(v is None for v in values):
        require(
            definition.missing_policy is not InteractionMissingPolicy.FAIL,
            "missing interaction input",
        )
        return (
            definition.fallback_value,
            definition.missing_policy is InteractionMissingPolicy.DECLARED_FALLBACK,
        )
    x = tuple(finite(v) for v in values if v is not None)
    t, p = definition.transform, definition.parameters
    try:
        if t is InteractionTransform.IDENTITY:
            output = x[0]
        elif t is InteractionTransform.PRODUCT:
            output = x[0] * x[1]
        elif t is InteractionTransform.RATIO:
            denominator = x[1]
            if p.denominator is DenominatorPolicy.EPSILON_FLOOR:
                assert p.epsilon is not None
                denominator = math.copysign(max(abs(denominator), p.epsilon), denominator)
            elif denominator == 0:
                require(
                    p.denominator is DenominatorPolicy.MISSING_ON_ZERO,
                    "zero interaction denominator",
                )
                return None, False
            output = x[0] / denominator
        elif t is InteractionTransform.DIFFERENCE:
            output = x[0] - x[1]
        elif t is InteractionTransform.ABS_DIFFERENCE:
            output = abs(x[0] - x[1])
        elif t is InteractionTransform.SQUARE:
            output = x[0] ** 2
        elif t is InteractionTransform.CUBE:
            output = x[0] ** 3
        elif t is InteractionTransform.LOG1P_SIGNED:
            output = math.copysign(math.log1p(abs(x[0])), x[0])
        elif t is InteractionTransform.CLIPPED_LINEAR:
            assert p.clip_lower is not None and p.clip_upper is not None
            output = min(p.clip_upper, max(p.clip_lower, x[0]))
        else:
            output = piecewise(x[0], fitted_knots or p.knots, p.ordinates)
        return finite(output), False
    except (OverflowError, ZeroDivisionError) as error:
        raise ContractError("undefined/overflow nonlinear transform") from error

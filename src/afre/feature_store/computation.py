"""Small static deterministic transformations; no code or model from provider data."""

import math
import statistics
from collections.abc import Callable

from afre.feature_store.dag import Transformation
from afre.feature_store.normalization import NormalizationMethod, NormalizationState
from afre.lineage import Scalar
from afre.schema import require

IMPLEMENTATION_VERSION = "afre-transforms-v1"


def _identity(values: tuple[Scalar, ...]) -> Scalar:
    require(len(values) == 1, "identity requires one value")
    return values[0]


def _numbers(values: tuple[Scalar, ...]) -> tuple[float, ...]:
    require(
        all(type(value) in (int, float) for value in values), "numeric transformation input"
    )
    return tuple(float(value) for value in values)


def _difference(values: tuple[Scalar, ...]) -> float:
    numbers = _numbers(values)
    require(len(numbers) == 2, "difference requires two values")
    return numbers[0] - numbers[1]


def _percent_change(values: tuple[Scalar, ...]) -> float:
    numbers = _numbers(values)
    require(len(numbers) >= 2 and numbers[0] != 0, "return requires history and nonzero entry")
    return numbers[-1] / numbers[0] - 1


def _log_return(values: tuple[Scalar, ...]) -> float:
    numbers = _numbers(values)
    require(
        len(numbers) >= 2 and numbers[0] > 0 and numbers[-1] > 0,
        "log return requires positive endpoint prices",
    )
    return math.log(numbers[-1]) - math.log(numbers[0])


def _mean(values: tuple[Scalar, ...]) -> float:
    require(bool(values), "mean requires observations")
    return statistics.fmean(_numbers(values))


def _stddev(values: tuple[Scalar, ...]) -> float:
    require(len(values) >= 2, "sample standard deviation requires two observations")
    return statistics.stdev(_numbers(values))


TRANSFORMATIONS: dict[Transformation, Callable[[tuple[Scalar, ...]], Scalar]] = {
    Transformation.IDENTITY: _identity,
    Transformation.DIFFERENCE: _difference,
    Transformation.PERCENT_CHANGE: _percent_change,
    Transformation.LOG_RETURN: _log_return,
    Transformation.ROLLING_MEAN: _mean,
    Transformation.ROLLING_STDDEV: _stddev,
}


def transform(
    kind: Transformation, values: tuple[Scalar, ...], state: NormalizationState | None = None
) -> Scalar:
    if kind is Transformation.STANDARDIZE:
        require(
            state is not None and state.spec.method is NormalizationMethod.STANDARDIZE,
            "only supplied standardization state is executable in AFRE-1",
        )
        assert state is not None
        numbers = _numbers(values)
        require(len(numbers) == 1, "normalization requires one value")
        params = {item.name: item.value for item in state.parameters}
        return (numbers[0] - float(params["mean"])) / float(params["stddev"])
    require(state is None, "unexpected normalization state")
    require(kind in TRANSFORMATIONS, "unknown static transformation")
    return TRANSFORMATIONS[kind](values)

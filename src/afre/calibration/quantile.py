"""Empirical Type-7 q-quantile of y minus raw q; no crossing repair."""

from afre.calibration.artifacts import CalibrationObservationSet, QuantileOffset
from afre.calibration.definitions import CalibrationSpec
from afre.probabilistic.artifacts import QuantileValue, validate_quantile_values
from afre.probabilistic.quantiles import empirical_quantile
from afre.schema import require
from afre.statistical_models.linear_algebra import finite


def offset_for(
    spec: CalibrationSpec, observations: CalibrationObservationSet, level: float
) -> QuantileOffset:
    require(level in spec.quantiles.levels, "quantile level not declared")
    residuals = tuple(
        sorted(
            finite(r.truth - next(q.value for q in r.quantiles if q.level == level))
            for r in observations.rows
        )
    )
    return QuantileOffset(
        spec.fingerprint,
        observations.fingerprint,
        level,
        empirical_quantile(residuals, level),
        residuals,
        tuple(r.fingerprint for r in observations.rows),
    )


def adjusted_quantiles(
    raw: tuple[QuantileValue, ...], offsets: tuple[QuantileOffset, ...]
) -> tuple[QuantileValue, ...]:
    values = {q.level: q.value for q in raw}
    require(
        len({o.level for o in offsets}) == len(offsets)
        and all(o.level in values for o in offsets),
        "quantile offset level identity mismatch",
    )
    for offset in offsets:
        values[offset.level] = finite(values[offset.level] + offset.offset)
    result = tuple(QuantileValue(q, v) for q, v in sorted(values.items()))
    validate_quantile_values(result)
    return result

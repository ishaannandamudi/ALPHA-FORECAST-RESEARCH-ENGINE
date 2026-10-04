"""Pinned truth selection after a complete partition/TEST preflight."""

from typing import TYPE_CHECKING

from afre.calibration.artifacts import (
    CalibrationObservation,
    CalibrationObservationSet,
    IntervalValue,
)
from afre.calibration.definitions import CalibrationRequest, CalibrationSpec
from afre.calibration.partitions import eligible_forecasts
from afre.probabilistic.artifacts import ProbabilisticForecast, QuantileValue
from afre.probabilistic.definitions import QuantileInterval
from afre.schema import require
from afre.statistical_models.artifacts import MatrixExclusion
from afre.target_engine.models import TargetVintage
from afre.target_engine.validation import target_known_by_cutoff

if TYPE_CHECKING:
    from afre.calibration.repository import CalibrationRepository


def interval_for(
    values: tuple[QuantileValue, ...], interval: QuantileInterval | None
) -> IntervalValue | None:
    if interval is None:
        return None
    lookup = {q.level: q.value for q in values}
    require(
        interval.lower in lookup and interval.upper in lookup,
        "interval quantile identity mismatch",
    )
    return IntervalValue(
        interval.lower, interval.upper, lookup[interval.lower], lookup[interval.upper]
    )


def observations_for(
    repo: "CalibrationRepository",
    spec: CalibrationSpec,
    requests: tuple[CalibrationRequest, ...],
) -> CalibrationObservationSet:
    require(
        0 < len(requests) <= repo.calibration_bounds.observations
        and len({r.raw_forecast_id for r in requests}) == len(requests),
        "calibration request count/duplicates",
    )
    require(
        len(requests) * (len(spec.events.requests) + len(spec.quantiles.levels) + 1)
        <= repo.calibration_bounds.work_cells,
        "calibration work bound",
    )
    ordered = tuple(sorted(requests, key=lambda r: r.raw_forecast_id))
    forecasts = tuple(repo.resolve(ProbabilisticForecast, r.raw_forecast_id) for r in ordered)
    eligible_forecasts(repo, spec, forecasts)
    rows, exclusions = [], []
    for request, raw in zip(ordered, forecasts, strict=True):
        sample_id = raw.input.sample_id
        assert sample_id is not None
        target = repo.resolve(TargetVintage, request.target_id)
        require(
            target.origin == raw.input.origin and target.definition == spec.target,
            "calibration full truth target/origin mismatch",
        )
        if not target_known_by_cutoff(target, spec.cutoff_ns):
            exclusions.append(
                MatrixExclusion(sample_id, "truth-unavailable-or-unverified-at-cutoff")
            )
            continue
        assert target.value is not None
        rows.append(
            CalibrationObservation(
                raw.fingerprint,
                sample_id,
                target.fingerprint,
                raw.input.origin,
                spec.target.fingerprint,
                target.value,
                target.clocks.final_available_ns,
                raw.available_ns,
                spec.cutoff_ns,
                raw.quantiles,
                raw.threshold_probabilities,
                raw.median_value,
                interval_for(raw.quantiles, spec.interval),
            )
        )
    rows.sort(
        key=lambda r: (r.origin.timestamp_ns, r.origin.instrument.fingerprint, r.sample_id)
    )
    window = spec.partition.rolling_count
    if window is not None:
        exclusions.extend(
            MatrixExclusion(r.sample_id, "outside-explicit-resolved-rolling-window")
            for r in rows[:-window]
        )
        rows = rows[-window:]
    require(len(rows) >= spec.minimum_samples, "insufficient eligible calibration observations")
    result = CalibrationObservationSet(
        spec.fingerprint, ordered, tuple(rows), tuple(exclusions)
    )
    repo.check_calibration_bounds(result)
    return result

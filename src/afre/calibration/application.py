"""Apply frozen state without accessing observations or truth repositories."""

from typing import TYPE_CHECKING

from afre.calibration.artifacts import (
    CalibratedForecast,
    CalibrationFitRun,
    CalibrationState,
    ConformalScoreSet,
    IntervalValue,
    ProbabilityMapping,
    QuantileOffset,
)
from afre.calibration.definitions import CalibrationSpec
from afre.calibration.probability import mapped_probability
from afre.calibration.quantile import adjusted_quantiles
from afre.calibration.samples import interval_for
from afre.calibration.schema import CalibrationMethod
from afre.probabilistic.artifacts import (
    ProbabilisticForecast,
    QuantileValue,
    ThresholdProbability,
)
from afre.schema import require
from afre.statistical_models.linear_algebra import finite

if TYPE_CHECKING:
    from afre.calibration.repository import CalibrationRepository


def outputs_for(
    spec: CalibrationSpec,
    raw_quantiles: tuple[QuantileValue, ...],
    raw_probabilities: tuple[ThresholdProbability, ...],
    center: float,
    mappings: tuple[ProbabilityMapping, ...],
    offsets: tuple[QuantileOffset, ...],
    conformal: ConformalScoreSet | None,
) -> tuple[tuple[QuantileValue, ...], tuple[ThresholdProbability, ...], IntervalValue | None]:
    probability_method = spec.method in (
        CalibrationMethod.ISOTONIC_PROBABILITY,
        CalibrationMethod.BINNED_PROBABILITY,
    )
    require(
        {m.event for m in mappings}
        == (set(spec.events.requests) if probability_method else set())
        and all(m.spec_id == spec.fingerprint and m.method is spec.method for m in mappings),
        "mapping event/spec identity mismatch",
    )
    require(
        {o.level for o in offsets}
        == (
            set(spec.quantiles.levels)
            if spec.method is CalibrationMethod.QUANTILE_OFFSET
            else set()
        )
        and all(o.spec_id == spec.fingerprint for o in offsets),
        "offset quantile/spec identity mismatch",
    )
    require(
        set(spec.events.requests) <= {p.request for p in raw_probabilities}
        and set(spec.quantiles.levels) <= {q.level for q in raw_quantiles},
        "application event/quantile identity mismatch",
    )
    conformal_method = spec.method in (
        CalibrationMethod.CONFORMAL_ABSOLUTE_RESIDUAL,
        CalibrationMethod.ROLLING_CONFORMAL,
    )
    require((conformal is not None) == conformal_method, "conformal state/method mismatch")
    if conformal is not None:
        require(
            conformal.spec_id == spec.fingerprint and conformal.alpha == spec.miscoverage_alpha,
            "conformal spec/alpha mismatch",
        )
    lookup = {m.event: m for m in mappings}
    probabilities = tuple(
        ThresholdProbability(
            p.request, mapped_probability(lookup[p.request], p.request, p.probability)
        )
        if p.request in lookup
        else p
        for p in raw_probabilities
    )
    quantiles = adjusted_quantiles(raw_quantiles, offsets)
    interval = interval_for(quantiles, spec.interval)
    if conformal is not None:
        assert spec.interval is not None
        interval = IntervalValue(
            spec.interval.lower,
            spec.interval.upper,
            finite(center - conformal.q_hat),
            finite(center + conformal.q_hat),
        )
    return quantiles, probabilities, interval


def forecast_for(
    repo: "CalibrationRepository",
    state: CalibrationState,
    raw: ProbabilisticForecast,
    computed_ns: int,
) -> CalibratedForecast:
    spec = repo.resolve(CalibrationSpec, state.inputs.spec_id)
    require(
        state.inputs.raw_model_id == spec.raw_model_id == raw.model_artifact_id
        and state.target_definition_id == spec.target.fingerprint == raw.target_definition_id,
        "calibrated raw model/target mismatch",
    )
    rows = repo._connection.execute(
        "SELECT fingerprint FROM c_fits WHERE state_id=?", (state.fingerprint,)
    ).fetchall()
    require(len(rows) == 1, "application requires completed calibration fit")
    run = repo.resolve(CalibrationFitRun, rows[0][0])
    require(
        run.inputs == state.inputs and run.diagnostics_id == state.diagnostics_id,
        "completed calibration run mismatch",
    )
    cutoff = raw.input.origin.availability_cutoff_ns
    require(
        raw.historical_admissible
        and raw.available_ns <= cutoff
        and state.inputs.available_ns <= cutoff,
        "raw forecast or calibration state unavailable at historical origin",
    )
    require(
        computed_ns
        >= max(raw.input.origin.timestamp_ns, raw.available_ns, state.inputs.available_ns),
        "calibration computation clock precedes inputs",
    )
    mappings = tuple(repo.resolve(ProbabilityMapping, m) for m in state.mapping_ids)
    offsets = tuple(repo.resolve(QuantileOffset, o) for o in state.offset_ids)
    conformal = (
        repo.resolve(ConformalScoreSet, state.conformal_id) if state.conformal_id else None
    )
    quantiles, probabilities, interval = outputs_for(
        spec,
        raw.quantiles,
        raw.threshold_probabilities,
        raw.median_value,
        mappings,
        offsets,
        conformal,
    )
    return CalibratedForecast(
        raw.fingerprint,
        state.fingerprint,
        raw.target_definition_id,
        raw.input,
        quantiles,
        probabilities,
        interval_for(raw.quantiles, spec.interval),
        interval,
        spec.method is CalibrationMethod.IDENTITY,
        state.inputs.available_ns,
        computed_ns,
        computed_ns,
        True,
    )

"""Bounded descriptive windows; detection never refits or selects calibration."""

from typing import TYPE_CHECKING

from afre.calibration.artifacts import (
    CalibratedForecast,
    CalibrationDriftDiagnostics,
    CalibrationDriftWindow,
    CalibrationEvaluation,
    CalibrationState,
)
from afre.calibration.definitions import CalibrationDriftSpec, CalibrationSpec
from afre.calibration.diagnostics import (
    event_diagnostics,
    interval_diagnostic,
    quantile_diagnostics,
)
from afre.calibration.schema import DriftMetric, DriftState
from afre.probabilistic.artifacts import ProbabilisticEvaluation
from afre.schema import require
from afre.statistical_models.linear_algebra import total

if TYPE_CHECKING:
    from afre.calibration.repository import CalibrationRepository


def drift_for(
    repo: "CalibrationRepository", spec: CalibrationDriftSpec, evaluation_ids: tuple[str, ...]
) -> CalibrationDriftDiagnostics:
    require(
        0 < len(evaluation_ids) <= repo.calibration_bounds.diagnostics
        and len(set(evaluation_ids)) == len(evaluation_ids),
        "drift history count/duplicates",
    )
    require(
        spec.window_evaluations <= repo.calibration_bounds.rolling_window, "drift window bound"
    )
    evaluations = tuple(
        sorted(
            (repo.resolve(CalibrationEvaluation, e) for e in evaluation_ids),
            key=lambda e: (e.cutoff_ns, e.fingerprint),
        )
    )
    first = evaluations[0]
    raw_first = repo.resolve(ProbabilisticEvaluation, first.raw_evaluation_id)
    require(
        all(
            e.state_id == first.state_id
            and e.protocol == first.protocol
            and repo.resolve(ProbabilisticEvaluation, e.raw_evaluation_id).scope
            is raw_first.scope
            for e in evaluations
        ),
        "drift history state/protocol/scope mismatch",
    )
    state = repo.resolve(CalibrationState, first.state_id)
    calibration = repo.resolve(CalibrationSpec, state.inputs.spec_id)
    prefix = [0]
    for evaluation in evaluations:
        prefix.append(prefix[-1] + len(evaluation.pairs))
    total_pairs = sum(
        prefix[i + 1] - prefix[max(0, i + 1 - spec.window_evaluations)]
        for i in range(len(evaluations))
    )
    require(
        total_pairs * (len(calibration.events.requests) + len(calibration.quantiles.levels) + 1)
        <= repo.calibration_bounds.work_cells,
        "drift total window work bound",
    )
    windows = []
    for index, evaluation in enumerate(evaluations):
        window = evaluations[max(0, index + 1 - spec.window_evaluations) : index + 1]
        pairs = tuple(p for e in window for p in e.pairs)
        require(
            len(pairs) <= repo.calibration_bounds.observations
            and len(pairs)
            * (len(calibration.events.requests) + len(calibration.quantiles.levels) + 1)
            <= repo.calibration_bounds.work_cells,
            "drift pair/work bound",
        )
        require(
            len({p.sample_id for p in pairs}) == len(pairs),
            "drift window repeats truth samples",
        )
        forecasts = tuple(
            repo.resolve(CalibratedForecast, p.calibrated_forecast_id) for p in pairs
        )
        rows = tuple(
            (p.truth, f.quantiles, f.probabilities, f.calibrated_interval)
            for p, f in zip(pairs, forecasts, strict=True)
        )
        value = None
        if spec.metric in (DriftMetric.BRIER, DriftMetric.ECE):
            events = event_diagnostics(rows, calibration.bins)
            values = [e.brier if spec.metric is DriftMetric.BRIER else e.ece for e in events]
            valid = [v for v in values if v is not None]
            value = total(valid) / len(valid) if valid else None
        elif spec.metric is DriftMetric.MAX_ABS_QUANTILE_GAP:
            gaps = [q.absolute_gap for q in quantile_diagnostics(rows)]
            value = max(g for g in gaps if g is not None) if gaps else None
        else:
            interval = interval_diagnostic(rows)
            value = interval.absolute_gap if interval else None
        status = (
            DriftState.INSUFFICIENT_DATA
            if len(pairs) < spec.minimum_pairs
            else DriftState.UNKNOWN
            if value is None
            else DriftState.DEGRADED
            if value > spec.threshold
            else DriftState.STABLE
        )
        windows.append(
            CalibrationDriftWindow(
                tuple(e.fingerprint for e in window),
                evaluation.cutoff_ns,
                len(pairs),
                value,
                status,
            )
        )
    return CalibrationDriftDiagnostics(
        spec, first.state_id, tuple(e.fingerprint for e in evaluations), tuple(windows)
    )

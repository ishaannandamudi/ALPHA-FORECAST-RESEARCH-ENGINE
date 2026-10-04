"""Independent later truth and exact-sample descriptive raw/calibrated scoring."""

from dataclasses import replace
from typing import TYPE_CHECKING

from afre.calibration.artifacts import (
    CalibratedForecast,
    CalibrationComparison,
    CalibrationDelta,
    CalibrationEvaluation,
    CalibrationScoredPair,
    CalibrationState,
)
from afre.calibration.definitions import CalibrationSpec
from afre.calibration.diagnostics import diagnostics_for
from afre.probabilistic.artifacts import (
    ProbabilisticEvaluation,
    ProbabilisticForecast,
    ProbabilityScore,
)
from afre.probabilistic.schema import ScoreName, ScoreState
from afre.probabilistic.scoring import (
    aggregate_scores,
    brier_score,
    pinball_loss,
    score_forecast,
)
from afre.probabilistic.thresholds import event_outcome
from afre.schema import require
from afre.statistical_models.linear_algebra import finite, total

if TYPE_CHECKING:
    from afre.calibration.repository import CalibrationRepository


def calibrated_scores(
    forecast: CalibratedForecast, raw_scores: tuple[ProbabilityScore, ...], truth: float
) -> tuple[ProbabilityScore, ...]:
    if forecast.full_distribution_preserved:
        return raw_scores
    quantiles = {q.level: q.value for q in forecast.quantiles}
    probabilities = {p.request: p.probability for p in forecast.probabilities}
    scores = []
    for score in raw_scores:
        name = score.name
        value: float | None
        if name is ScoreName.COUNT:
            value = 1.0
        elif name is ScoreName.PINBALL:
            value = (
                pinball_loss(score.level, quantiles[score.level], truth)
                if score.level is not None
                else total([pinball_loss(q, v, truth) for q, v in quantiles.items()])
                / len(quantiles)
            )
        elif name is ScoreName.QUANTILE_FREQUENCY:
            assert score.level is not None
            value = float(truth <= quantiles[score.level])
        elif name is ScoreName.BRIER:
            value = (
                brier_score(
                    probabilities[score.threshold], event_outcome(truth, score.threshold)
                )
                if score.threshold is not None
                else (
                    total(
                        [
                            brier_score(p, event_outcome(truth, event))
                            for event, p in probabilities.items()
                        ]
                    )
                    / len(probabilities)
                    if probabilities
                    else None
                )
            )
        elif name in (ScoreName.INTERVAL_COVERAGE, ScoreName.INTERVAL_WIDTH):
            interval = forecast.calibrated_interval
            require(
                interval is not None
                and (score.level, score.upper_level)
                == (interval.lower_level, interval.upper_level),
                "evaluation interval identity mismatch",
            )
            assert interval is not None
            value = (
                float(interval.lower <= truth <= interval.upper)
                if name is ScoreName.INTERVAL_COVERAGE
                else finite(interval.upper - interval.lower)
            )
        else:
            # A set of adjusted marginals/intervals is not a coherent density/CDF.
            value = None
        scores.append(
            replace(
                score,
                value=value,
                state=ScoreState.AVAILABLE if value is not None else ScoreState.UNSUPPORTED,
            )
        )
    return tuple(scores)


def evaluation_for(
    repo: "CalibrationRepository", forecast_ids: tuple[str, ...], raw: ProbabilisticEvaluation
) -> CalibrationEvaluation:
    require(
        0 < len(forecast_ids) <= repo.calibration_bounds.forecasts
        and len(set(forecast_ids)) == len(forecast_ids),
        "calibration evaluation forecast count/duplicates",
    )
    forecasts = tuple(
        repo.resolve(CalibratedForecast, identity) for identity in sorted(forecast_ids)
    )
    state = repo.resolve(CalibrationState, forecasts[0].state_id)
    spec = repo.resolve(CalibrationSpec, state.inputs.spec_id)
    require(
        all(
            f.state_id == state.fingerprint and f.available_ns <= raw.evaluation_cutoff_ns
            for f in forecasts
        ),
        "evaluation mixes calibration states or unavailable forecasts",
    )
    require(
        set(raw.forecast_ids) == {f.raw_forecast_id for f in forecasts}
        and raw.model_artifact_id == spec.raw_model_id,
        "raw/calibrated evaluation forecast identity mismatch",
    )
    require(
        all(f.input.sample_id not in state.inputs.sample_ids for f in forecasts),
        "independent evaluation cannot reuse calibration fit samples",
    )
    require(
        raw.protocol.intervals == ((spec.interval,) if spec.interval else ()),
        "calibration evaluation interval protocol mismatch",
    )
    lookup = {f.raw_forecast_id: f for f in forecasts}
    pairs = tuple(
        CalibrationScoredPair(
            lookup[p.forecast_id].fingerprint,
            p.forecast_id,
            p.sample_id,
            p.target_id,
            p.origin_ns,
            p.security_id,
            p.truth,
            p.scores,
            calibrated_scores(lookup[p.forecast_id], p.scores, p.truth),
        )
        for p in raw.pairs
    )
    raw_rows, calibrated_rows = [], []
    for p in pairs:
        f = lookup[p.raw_forecast_id]
        original = repo.resolve(ProbabilisticForecast, p.raw_forecast_id)
        raw_rows.append(
            (p.truth, original.quantiles, original.threshold_probabilities, f.raw_interval)
        )
        calibrated_rows.append((p.truth, f.quantiles, f.probabilities, f.calibrated_interval))
    first = forecasts[0]
    original = repo.resolve(ProbabilisticForecast, first.raw_forecast_id)
    template, _ = score_forecast(original, original.median_value, raw.protocol)
    adjusted_template = calibrated_scores(first, template, original.median_value)
    scores = aggregate_scores(tuple(p.calibrated_scores for p in pairs), adjusted_template)
    diagnostics = diagnostics_for(
        tuple(raw_rows), tuple(calibrated_rows), spec.bins, "independent-evaluation"
    )
    return CalibrationEvaluation(
        state.fingerprint,
        raw.fingerprint,
        forecast_ids,
        pairs,
        raw.scores,
        scores,
        diagnostics,
        raw.protocol,
        raw.evaluation_cutoff_ns,
        raw.available_ns,
    )


def comparison_for(
    repo: "CalibrationRepository", raw_id: str, calibrated_id: str
) -> CalibrationComparison:
    raw = repo.resolve(ProbabilisticEvaluation, raw_id)
    calibrated = repo.resolve(CalibrationEvaluation, calibrated_id)
    pinned = repo.resolve(ProbabilisticEvaluation, calibrated.raw_evaluation_id)
    require(
        (
            raw.dataset_id,
            raw.fold_id,
            raw.model_artifact_id,
            raw.target_definition_id,
            raw.scope,
            raw.evaluation_cutoff_ns,
            raw.protocol,
            raw.forecast_ids,
            raw.exclusions,
        )
        == (
            pinned.dataset_id,
            pinned.fold_id,
            pinned.model_artifact_id,
            pinned.target_definition_id,
            pinned.scope,
            pinned.evaluation_cutoff_ns,
            pinned.protocol,
            pinned.forecast_ids,
            pinned.exclusions,
        ),
        "raw/calibrated comparison requires identical sample protocol",
    )
    require(
        tuple((p.forecast_id, p.sample_id, p.target_id, p.truth, p.scores) for p in raw.pairs)
        == tuple(
            (p.raw_forecast_id, p.sample_id, p.target_id, p.truth, p.raw_scores)
            for p in calibrated.pairs
        ),
        "raw/calibrated comparison truth mismatch",
    )
    require(
        tuple(s.key for s in raw.scores) == tuple(s.key for s in calibrated.calibrated_scores),
        "comparison score protocol mismatch",
    )
    deltas = tuple(
        CalibrationDelta(
            a,
            b,
            finite(b.value - a.value) if a.value is not None and b.value is not None else None,
        )
        for a, b in zip(raw.scores, calibrated.calibrated_scores, strict=True)
    )
    before, after = (
        calibrated.diagnostics.raw_interval,
        calibrated.diagnostics.calibrated_interval,
    )
    coverage_delta = (
        finite(after.absolute_gap - before.absolute_gap)
        if before is not None
        and after is not None
        and before.absolute_gap is not None
        and after.absolute_gap is not None
        else None
    )
    width_delta = (
        finite(after.mean_width - before.mean_width)
        if before is not None
        and after is not None
        and before.mean_width is not None
        and after.mean_width is not None
        else None
    )
    return CalibrationComparison(raw_id, calibrated_id, deltas, coverage_delta, width_delta)

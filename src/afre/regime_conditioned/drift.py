"""Descriptive matched-truth window diagnostics; never mutates models or taxonomies."""

from typing import TYPE_CHECKING

from afre.regime_conditioned.artifacts import (
    RegimeConditionedEvaluation,
    RegimeConditionedForecast,
    RegimeConditionedSample,
    RegimeDriftDiagnostic,
)
from afre.schema import require

if TYPE_CHECKING:
    from afre.regime_conditioned.repository import RegimeRepository


def drift_for(
    repo: "RegimeRepository",
    reference_id: str,
    current_id: str,
    cutoff_ns: int,
    minimum_count: int,
) -> RegimeDriftDiagnostic:
    reference = repo.resolve(RegimeConditionedEvaluation, reference_id)
    current = repo.resolve(RegimeConditionedEvaluation, current_id)
    require(
        reference.model_id == current.model_id
        and reference.available_ns <= cutoff_ns
        and current.available_ns <= cutoff_ns,
        "regime drift exact model/known windows",
    )
    windows = []
    for evaluation in (reference, current):
        origins = [
            repo.resolve(RegimeConditionedForecast, p.forecast_id).origin.timestamp_ns
            for p in evaluation.pairs
        ]
        windows.append(origins)
    require(
        not windows[0] or not windows[1] or max(windows[0]) < min(windows[1]),
        "regime drift requires ordered disjoint origin windows",
    )
    enough = min(len(reference.pairs), len(current.pairs)) >= minimum_count
    a, b = reference.soft_diagnostics, current.soft_diagnostics
    require(
        tuple(d.state_id for d in a) == tuple(d.state_id for d in b), "regime drift taxonomy"
    )

    def frequency(evaluation: RegimeConditionedEvaluation) -> float | None:
        observations = [
            repo.resolve(
                RegimeConditionedSample,
                repo.resolve(RegimeConditionedForecast, p.forecast_id).observation_id,
            )
            for p in evaluation.pairs
        ]
        known = [o for o in observations if o.transition_status != "unknown"]
        return (
            sum(o.transition_status == "transition" for o in known) / len(known)
            if known
            else None
        )

    f, g = frequency(reference), frequency(current)
    return RegimeDriftDiagnostic(
        reference_id,
        current_id,
        tuple(
            (y.state_id, y.mean_probability - x.mean_probability)
            for x, y in zip(a, b, strict=True)
        )
        if enough
        else (),
        tuple(
            (
                y.state_id,
                y.weighted_conditioned_mae - x.weighted_conditioned_mae
                if x.weighted_conditioned_mae is not None
                and y.weighted_conditioned_mae is not None
                else None,
            )
            for x, y in zip(a, b, strict=True)
        )
        if enough
        else (),
        g - f if enough and f is not None and g is not None else None,
        cutoff_ns,
        minimum_count,
        "available" if enough else "insufficient-data",
    )

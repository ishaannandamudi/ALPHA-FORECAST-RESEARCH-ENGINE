"""Frozen interval coverage and explicit reliability bins; no recalibration."""

from statistics import fmean
from typing import TYPE_CHECKING, cast

from afre.health.artifacts import HealthObservation
from afre.health.definitions import HealthDiagnosticRequest
from afre.health.probabilities import event_probability, interval_for, proper_score
from afre.health.schema import HealthDiagnostic as D

if TYPE_CHECKING:
    from afre.health.repository import HealthRepository


def calibration_score(
    repo: "HealthRepository",
    request: HealthDiagnosticRequest,
    rows: tuple[tuple[HealthObservation, float, float], ...],
) -> tuple[float | None, tuple[tuple[str, float | None], ...]]:
    kind = request.kind
    if kind in (D.CRPS, D.NLL):
        scores = tuple(proper_score(repo, o.source_id, y, kind is D.NLL) for o, _, y in rows)
        return (
            fmean(v for v in scores if v is not None)
            if all(v is not None for v in scores)
            else None
        ), ()
    if kind in (D.COVERAGE, D.COVERAGE_ERROR):
        intervals = tuple(
            interval_for(repo, o.source_id, request.interval_levels) for o, _, _ in rows
        )
        if any(i is None for i in intervals):
            return None, ()
        coverage = fmean(
            float(i[0] <= row[2] <= i[1])
            for i, row in zip(intervals, rows, strict=True)
            if i is not None
        )
        return (
            abs(coverage - (request.interval_levels[1] - request.interval_levels[0]))
            if kind is D.COVERAGE_ERROR
            else coverage
        ), ()
    probabilities = tuple(
        event_probability(repo, o.source_id, request.threshold) for o, _, _ in rows
    )
    if any(p is None for p in probabilities):
        return None, ()
    details: list[tuple[str, float | None]] = []
    gaps: list[tuple[int, float]] = []
    edges = request.reliability_edges
    for j, (low, high) in enumerate(zip(edges, edges[1:], strict=False)):
        indices = [
            i
            for i, p in enumerate(probabilities)
            if p is not None and low <= p and (p < high or j == len(edges) - 2 and p == high)
        ]
        mean = fmean(cast(float, probabilities[i]) for i in indices) if indices else None
        frequency = (
            fmean(float(rows[i][2] > request.threshold) for i in indices) if indices else None
        )
        gap = abs(mean - frequency) if mean is not None and frequency is not None else None
        details.extend(
            (
                (f"bin:{j}:count", float(len(indices))),
                (f"bin:{j}:mean_probability", mean),
                (f"bin:{j}:frequency", frequency),
                (f"bin:{j}:gap", gap),
            )
        )
        if gap is not None:
            gaps.append((len(indices), gap))
    return (
        max(g for _, g in gaps) if kind is D.MCE else sum(n * g for n, g in gaps) / len(rows)
    ), tuple(details)

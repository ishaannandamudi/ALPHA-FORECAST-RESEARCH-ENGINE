"""Fixed-bin calibration error and coverage, distinct from proper scores/width."""

from afre.calibration.artifacts import (
    CalibrationDiagnostics,
    EventDiagnostic,
    IntervalDiagnostic,
    IntervalValue,
    QuantileDiagnostic,
    ReliabilityBin,
)
from afre.calibration.definitions import CalibrationBinDefinition
from afre.calibration.probability import bin_index
from afre.probabilistic.artifacts import QuantileValue, ThresholdProbability
from afre.probabilistic.scoring import brier_score
from afre.probabilistic.thresholds import event_outcome
from afre.schema import require
from afre.statistical_models.linear_algebra import finite, total

DiagnosticRow = tuple[
    float, tuple[QuantileValue, ...], tuple[ThresholdProbability, ...], IntervalValue | None
]


def event_diagnostics(
    rows: tuple[DiagnosticRow, ...], bins: CalibrationBinDefinition
) -> tuple[EventDiagnostic, ...]:
    if not rows:
        return ()
    events = tuple(p.request for p in rows[0][2])
    require(
        all(tuple(p.request for p in r[2]) == events for r in rows), "diagnostic event mismatch"
    )
    result = []
    for index, event in enumerate(events):
        pairs = tuple((r[2][index].probability, event_outcome(r[0], event)) for r in rows)
        groups: list[list[tuple[float, bool]]] = [[] for _ in bins.edges[1:]]
        for p, y in pairs:
            groups[bin_index(bins.edges, p)].append((p, y))
        reliability = []
        for i, group in enumerate(groups):
            n = len(group)
            mean = total([p for p, _ in group]) / n if n else None
            observed = sum(y for _, y in group) / n if n else None
            gap = abs(observed - mean) if observed is not None and mean is not None else None
            reliability.append(
                ReliabilityBin(bins.edges[i], bins.edges[i + 1], n, mean, observed, gap)
            )
        count = len(pairs)
        result.append(
            EventDiagnostic(
                event,
                count,
                total([brier_score(p, y) for p, y in pairs]) / count,
                sum(y for _, y in pairs) / count,
                total(
                    [
                        b.count / count * b.absolute_gap
                        for b in reliability
                        if b.absolute_gap is not None
                    ]
                ),
                max(b.absolute_gap for b in reliability if b.absolute_gap is not None),
                tuple(reliability),
            )
        )
    return tuple(result)


def quantile_diagnostics(rows: tuple[DiagnosticRow, ...]) -> tuple[QuantileDiagnostic, ...]:
    if not rows:
        return ()
    levels = tuple(q.level for q in rows[0][1])
    require(
        all(tuple(q.level for q in r[1]) == levels for r in rows),
        "diagnostic quantile mismatch",
    )
    count = len(rows)
    result = []
    for i, level in enumerate(levels):
        frequency = sum(r[0] <= r[1][i].value for r in rows) / count
        gap = finite(frequency - level)
        result.append(QuantileDiagnostic(level, count, frequency, gap, abs(gap)))
    return tuple(result)


def interval_diagnostic(rows: tuple[DiagnosticRow, ...]) -> IntervalDiagnostic | None:
    if not rows or rows[0][3] is None:
        require(all(r[3] is None for r in rows), "mixed diagnostic intervals")
        return None
    first = rows[0][3]
    intervals = tuple(r[3] for r in rows)
    require(
        all(
            i is not None
            and (i.lower_level, i.upper_level) == (first.lower_level, first.upper_level)
            for i in intervals
        ),
        "diagnostic interval identity mismatch",
    )
    count = len(rows)
    coverage = (
        sum(
            i is not None and i.lower <= r[0] <= i.upper
            for r, i in zip(rows, intervals, strict=True)
        )
        / count
    )
    nominal = first.upper_level - first.lower_level
    gap = finite(coverage - nominal)
    width = total([finite(i.upper - i.lower) for i in intervals if i is not None]) / count
    return IntervalDiagnostic(nominal, count, coverage, gap, abs(gap), width)


def diagnostics_for(
    raw: tuple[DiagnosticRow, ...],
    calibrated: tuple[DiagnosticRow, ...],
    bins: CalibrationBinDefinition,
    context: str,
) -> CalibrationDiagnostics:
    require(
        len(raw) == len(calibrated)
        and all(a[0] == b[0] for a, b in zip(raw, calibrated, strict=True)),
        "diagnostics require exact truth samples",
    )
    return CalibrationDiagnostics(
        context,
        event_diagnostics(raw, bins),
        event_diagnostics(calibrated, bins),
        quantile_diagnostics(raw),
        quantile_diagnostics(calibrated),
        interval_diagnostic(raw),
        interval_diagnostic(calibrated),
    )

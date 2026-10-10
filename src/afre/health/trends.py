"""Caller-declared window trends only; no boundary search or significance inference."""

from math import fsum
from statistics import fmean
from typing import TYPE_CHECKING

from afre.health.artifacts import HealthDecayTrend, HealthMetric
from afre.health.definitions import HealthSpec
from afre.health.schema import HealthStatus
from afre.schema import require

if TYPE_CHECKING:
    from afre.health.repository import HealthRepository


def trend_for(
    repo: "HealthRepository", identities: tuple[str, ...], available_ns: int
) -> HealthDecayTrend:
    require(
        2 <= len(identities) <= repo.health_bounds.trend_windows
        and len(set(identities)) == len(identities),
        "health trend bounds/duplicates",
    )
    metrics = tuple(repo.resolve(HealthMetric, i) for i in identities)
    specs = tuple(repo.resolve(HealthSpec, m.spec_id) for m in metrics)
    require(
        len(
            {
                (
                    s.reference_id,
                    s.reference_window.fingerprint,
                    m.request_id,
                    m.rule_id,
                    s.intersection,
                    s.pair_key,
                    s.environment_id,
                    s.minimum_count,
                    s.predeclared,
                )
                for s, m in zip(specs, metrics, strict=True)
            }
        )
        == 1,
        "health trend exact reference/metric/rule;no baseline reset",
    )
    ordered = sorted(
        zip(specs, metrics, strict=True),
        key=lambda p: (p[0].current_window.start_ns, p[1].fingerprint),
    )
    x = tuple(s.current_window.start_ns for s, _ in ordered)
    require(
        len(set(x)) == len(x) and available_ns >= max(m.available_ns for _, m in ordered),
        "health trend ordered clocks",
    )
    values = tuple(m.score for _, m in ordered)
    slope = fraction = None
    if all(v is not None for v in values):
        y = tuple(float(v) for v in values if v is not None)
        slope, fraction = slope_and_fraction(x, y)
    return HealthDecayTrend(
        tuple(m.fingerprint for _, m in ordered),
        slope,
        fraction,
        HealthStatus.HEALTHY if slope is not None else HealthStatus.UNAVAILABLE,
        (
            "descriptive-slope-per-UTC-nanosecond/nondecreasing-adjacent-"
            "fraction;not-a-health-probability"
        ),
        available_ns,
    )


def slope_and_fraction(x: tuple[int, ...], y: tuple[float, ...]) -> tuple[float, float]:
    require(len(x) == len(y) >= 2 and len(set(x)) == len(x), "health descriptive trend support")
    relative = tuple(at - x[0] for at in x)
    cx, cy = fmean(relative), fmean(y)
    slope = fsum((a - cx) * (b - cy) for a, b in zip(relative, y, strict=True)) / fsum(
        (a - cx) ** 2 for a in relative
    )
    fraction = sum(b >= a for a, b in zip(y, y[1:], strict=False)) / (len(y) - 1)
    return slope, fraction

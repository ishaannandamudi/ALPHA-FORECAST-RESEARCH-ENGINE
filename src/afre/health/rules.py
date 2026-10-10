"""Explicit thresholds and deterministic descriptive severity; no actions."""

from afre.health.definitions import HealthRule
from afre.health.schema import HealthDirection, HealthStatus


def classify(rule: HealthRule, value: float) -> HealthStatus:
    direction = rule.direction
    if direction is HealthDirection.TWO_SIDED_RANGE:
        assert rule.warning_upper is not None and rule.degraded_upper is not None
        if value < rule.degraded or value > rule.degraded_upper:
            return HealthStatus.DEGRADED
        if value < rule.warning or value > rule.warning_upper:
            return HealthStatus.WARNING
        return HealthStatus.HEALTHY
    if direction is HealthDirection.ABSOLUTE_CHANGE_WORSE:
        value = abs(value)
    if direction is HealthDirection.LOWER_WORSE:
        if value <= rule.degraded:
            return HealthStatus.DEGRADED
        if value <= rule.warning:
            return HealthStatus.WARNING
    else:
        if value >= rule.degraded:
            return HealthStatus.DEGRADED
        if value >= rule.warning:
            return HealthStatus.WARNING
    return HealthStatus.HEALTHY

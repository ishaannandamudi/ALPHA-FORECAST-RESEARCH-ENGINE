"""Deterministic declared windows, without adaptive boundaries or refitting."""

from afre.invariance.definitions import StabilityTimeWindow
from afre.schema import require


def rolling_windows(
    start_ns: int,
    end_ns: int,
    length_ns: int,
    stride_ns: int,
    minimum_count: int = 2,
    maximum_windows: int = 32,
) -> tuple[StabilityTimeWindow, ...]:
    require(
        0 <= start_ns < end_ns
        and length_ns > 0
        and stride_ns > 0
        and 1 <= maximum_windows <= 32,
        "rolling window parameters",
    )
    count = (end_ns - start_ns - length_ns) // stride_ns + 1
    require(0 < count <= maximum_windows, "rolling window count bound")
    return tuple(
        StabilityTimeWindow(
            start_ns + i * stride_ns,
            start_ns + i * stride_ns + length_ns,
            minimum_count=minimum_count,
        )
        for i in range(count)
    )

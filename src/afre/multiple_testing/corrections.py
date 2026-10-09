"""Deterministic FWER/FDR arithmetic with complete declared size and identity ties."""

import math

from afre.multiple_testing.schema import CorrectionMethod
from afre.schema import require


def adjust_pvalues(
    values: tuple[tuple[str, float | None], ...], method: CorrectionMethod
) -> tuple[tuple[str, float, int], ...]:
    require(
        1 <= len(values) <= 2000
        and len({i for i, _ in values}) == len(values)
        and type(method) is CorrectionMethod,
        "correction family bounds/duplicates/method",
    )
    require(
        all(
            type(i) is str
            and bool(i)
            and (p is None or type(p) is float and math.isfinite(p) and 0 <= p <= 1)
            for i, p in values
        ),
        "correction p-value bounds",
    )
    ordered = sorted((1.0 if p is None else p, i) for i, p in values)
    m = len(values)
    outputs: dict[str, tuple[float, int]] = {}
    if method is CorrectionMethod.BONFERRONI:
        for rank, (p, identity) in enumerate(ordered, 1):
            outputs[identity] = (min(1.0, m * p), rank)
    elif method is CorrectionMethod.HOLM:
        last = 0.0
        for rank, (p, identity) in enumerate(ordered, 1):
            last = max(last, min(1.0, (m - rank + 1) * p))
            outputs[identity] = (last, rank)
    else:
        harmonic = (
            math.fsum(1 / i for i in range(1, m + 1))
            if method is CorrectionMethod.BENJAMINI_YEKUTIELI
            else 1.0
        )
        last = 1.0
        for rank in range(m, 0, -1):
            p, identity = ordered[rank - 1]
            last = min(last, harmonic * m * p / rank)
            outputs[identity] = (last, rank)
    return tuple((identity, *outputs[identity]) for identity in sorted(outputs))

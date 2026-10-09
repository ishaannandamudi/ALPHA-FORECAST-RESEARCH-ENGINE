"""Independent exact-rational correction references for bounded offline validation."""

from fractions import Fraction

from afre.multiple_testing import CorrectionMethod as C


def correction_oracle(
    values: tuple[tuple[str, float | None], ...], method: C
) -> dict[str, float]:
    ordered = sorted((1.0 if p is None else p, i) for i, p in values)
    m = len(ordered)
    harmonic = sum((Fraction(1, k) for k in range(1, m + 1)), Fraction())
    result = {}
    for j, (value, identity) in enumerate(ordered):
        if method is C.BONFERRONI:
            answer = Fraction.from_float(value) * m
        elif method is C.HOLM:
            answer = max(
                Fraction.from_float(p) * (m - k) for k, (p, _) in enumerate(ordered[: j + 1])
            )
        else:
            answer = min(
                Fraction.from_float(p) * m / (k + 1)
                for k, (p, _) in enumerate(ordered)
                if k >= j
            )
            if method is C.BENJAMINI_YEKUTIELI:
                answer *= harmonic
        result[identity] = min(1.0, float(answer))
    return result

"""Independent bounded normal-equation oracle for fixture readouts, never used in AFRE."""

import math


def ridge_oracle(
    x: tuple[tuple[float, ...], ...], y: tuple[float, ...], penalty: float
) -> tuple[float, ...]:
    design = tuple((1.0, *r) for r in x)
    p = len(design[0])
    augmented = [
        [
            math.fsum(r[j] * r[k] for r in design) + (penalty if j == k and j else 0.0)
            for k in range(p)
        ]
        + [math.fsum(r[j] * t for r, t in zip(design, y, strict=True))]
        for j in range(p)
    ]
    for i in range(p):
        pivot = max(range(i, p), key=lambda k: abs(augmented[k][i]))
        augmented[i], augmented[pivot] = augmented[pivot], augmented[i]
        divisor = augmented[i][i]
        assert abs(divisor) > 1e-15
        augmented[i] = [v / divisor for v in augmented[i]]
        for j in range(p):
            if j == i:
                continue
            multiple = augmented[j][i]
            augmented[j] = [
                a - multiple * b for a, b in zip(augmented[j], augmented[i], strict=True)
            ]
    return tuple(r[-1] for r in augmented)

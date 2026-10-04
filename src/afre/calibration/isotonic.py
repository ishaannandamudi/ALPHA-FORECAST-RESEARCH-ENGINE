"""Deterministic equal-weight PAV with linear pooling and logarithmic queries."""

from bisect import bisect_left

from afre.calibration.artifacts import IsotonicBlock
from afre.schema import require
from afre.statistical_models.linear_algebra import finite


def pav(pairs: tuple[tuple[float, bool, str], ...]) -> tuple[IsotonicBlock, ...]:
    require(
        bool(pairs) and len({p[2] for p in pairs}) == len(pairs),
        "PAV empty/duplicate observations",
    )
    for p, y, _ in pairs:
        require(0 <= finite(p) <= 1 and type(y) is bool, "PAV probability/outcome domain")
    # Range indexes keep pooling O(n): growing source-ID tuples are built only once.
    stack: list[tuple[float, float, int, int, int, int]] = []
    ordered = sorted(pairs, key=lambda p: (p[0], p[2]))
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][0] == ordered[index][0]:
            end += 1
        successes = sum(ordered[i][1] for i in range(index, end))
        stack.append((ordered[index][0], ordered[index][0], end - index, successes, index, end))
        while len(stack) > 1 and stack[-2][3] * stack[-1][2] > stack[-1][3] * stack[-2][2]:
            right, left = stack.pop(), stack.pop()
            stack.append(
                (left[0], right[1], left[2] + right[2], left[3] + right[3], left[4], right[5])
            )
        index = end
    return tuple(
        IsotonicBlock(
            low,
            high,
            count,
            successes,
            successes / count,
            tuple(sorted(ordered[i][2] for i in range(start, end))),
        )
        for low, high, count, successes, start, end in stack
    )


def isotonic_probability(blocks: tuple[IsotonicBlock, ...], probability: float) -> float:
    require(bool(blocks) and 0 <= finite(probability) <= 1, "isotonic query domain")
    index = bisect_left(blocks, probability, key=lambda b: b.upper)
    if index == len(blocks):
        return blocks[-1].probability
    right = blocks[index]
    if index == 0 or probability >= right.lower:
        return right.probability
    left = blocks[index - 1]
    weight = (probability - left.upper) / (right.lower - left.upper)
    return finite(left.probability + weight * (right.probability - left.probability))

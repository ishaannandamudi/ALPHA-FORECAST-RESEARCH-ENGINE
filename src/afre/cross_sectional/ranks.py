"""Rank 1 is best. Percentile = 1-(rank-1)/(N-1); singleton is 0.5."""

from afre.cross_sectional.schema import RankDirection, RankTiePolicy
from afre.schema import require
from afre.statistical_models.linear_algebra import finite


def rank_values(
    values: tuple[tuple[str, float], ...], direction: RankDirection, ties: RankTiePolicy
) -> tuple[tuple[str, float, float], ...]:
    require(
        len(values) <= 100_000 and len({k for k, _ in values}) == len(values),
        "rank count/duplicate security",
    )
    ordered = sorted(
        values,
        key=lambda item: (
            -finite(item[1]) if direction is RankDirection.HIGHER_BETTER else finite(item[1]),
            item[0],
        ),
    )
    result: list[tuple[str, float, float]] = []
    start, dense, count = 0, 1, len(ordered)
    while start < count:
        end = start + 1
        while end < count and ordered[end][1] == ordered[start][1]:
            end += 1
        rank = float(
            (start + 1 + end) / 2
            if ties is RankTiePolicy.AVERAGE_RANK
            else start + 1
            if ties is RankTiePolicy.MIN_RANK
            else end
            if ties is RankTiePolicy.MAX_RANK
            else dense
        )
        percentile = 1 - (rank - 1) / (count - 1) if count > 1 else 0.5
        result.extend((key, rank, percentile) for key, _ in ordered[start:end])
        start, dense = end, dense + 1
    return tuple(sorted(result))

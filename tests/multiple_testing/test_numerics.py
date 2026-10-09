"""Independent integer/enumeration oracles for signs and declared full-family corrections."""

import itertools
import math
from fractions import Fraction

import pytest

from afre.multiple_testing import CorrectionMethod as C
from afre.multiple_testing import HypothesisDirection as D
from afre.multiple_testing import adjust_pvalues, fair_sign_pvalue
from afre.multiple_testing.schema import TestReuseStatus as Reuse
from afre.multiple_testing.test_reuse import classify_reuse
from afre.schema import ContractError


@pytest.mark.parametrize("n", range(1, 10))
@pytest.mark.parametrize("direction", tuple(D))
def test_exact_sign_independent_enumeration(n: int, direction: D) -> None:
    totals = tuple(sum(bits) for bits in itertools.product((0, 1), repeat=n))
    for k in range(n + 1):
        hits = sum(
            v >= k
            if direction is D.GREATER
            else v <= k
            if direction is D.LESS
            else abs(2 * v - n) >= abs(2 * k - n)
            for v in totals
        )
        assert fair_sign_pvalue(k, n, direction) == float(Fraction(hits, 2**n))


@pytest.mark.parametrize(
    "positive,count,direction,expected",
    [
        (5, 5, D.GREATER, 1 / 32),
        (0, 5, D.LESS, 1 / 32),
        (5, 5, D.TWO_SIDED, 1 / 16),
        (3, 4, D.GREATER, 5 / 16),
        (1, 4, D.TWO_SIDED, 10 / 16),
        (2, 4, D.TWO_SIDED, 1.0),
    ],
)
def test_known_sign_fixtures(positive: int, count: int, direction: D, expected: float) -> None:
    assert fair_sign_pvalue(positive, count, direction) == expected


@pytest.mark.parametrize("k,n", [(0, 0), (-1, 3), (4, 3), (1, 2001), (True, 2)])
def test_invalid_sign_counts(k: int, n: int) -> None:
    with pytest.raises(ContractError):
        fair_sign_pvalue(k, n, D.GREATER)


def test_exact_positive_tail_does_not_round_to_zero() -> None:
    assert fair_sign_pvalue(2000, 2000, D.GREATER) == math.nextafter(0.0, 1.0)


def oracle(values: tuple[tuple[str, float | None], ...], method: C) -> dict[str, float]:
    ordered = sorted((1.0 if v is None else v, i) for i, v in values)
    m = len(ordered)
    harmonic = sum(Fraction(1, k) for k in range(1, m + 1))
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
                Fraction.from_float(p) * m / Fraction(k + 1)
                for k, (p, _) in enumerate(ordered)
                if k >= j
            )
            if method is C.BENJAMINI_YEKUTIELI:
                answer *= harmonic
        result[identity] = min(1.0, float(answer))
    return result


@pytest.mark.parametrize("method", tuple(C))
@pytest.mark.parametrize(
    "values",
    [
        (("c", 0.04), ("b", 0.01), ("a", 0.01), ("d", None)),
        (("a", 0.0), ("b", 1.0)),
        (("z", 0.003),),
        tuple((str(i), float((i * 7) % 13) / 13) for i in range(20)),
    ],
)
def test_corrections_full_denominator_ties_and_order(
    values: tuple[tuple[str, float | None], ...], method: C
) -> None:
    expected = oracle(values, method)
    result = adjust_pvalues(values, method)
    assert result == adjust_pvalues(tuple(reversed(values)), method)
    assert max(abs(p - expected[i]) for i, p, _ in result) <= 2e-16
    by_rank = sorted(result, key=lambda row: row[2])
    assert [r[1] for r in by_rank] == sorted(r[1] for r in by_rank)
    assert [i for i, _, _ in by_rank] == [
        i for _, i in sorted((1.0 if p is None else p, i) for i, p in values)
    ]


@pytest.mark.parametrize("p", [float("nan"), float("inf"), -0.01, 1.01, True, 1])
def test_pvalue_bounds(p: float) -> None:
    with pytest.raises(ContractError):
        adjust_pvalues((("a", p),), C.HOLM)


@pytest.mark.parametrize(
    "values",
    [(), (("a", 0.1), ("a", 0.2)), (("", 0.1),), tuple((str(i), 0.1) for i in range(2001))],
)
def test_family_arithmetic_bounds(values: tuple[tuple[str, float | None], ...]) -> None:
    with pytest.raises(ContractError):
        adjust_pvalues(values, C.HOLM)


@pytest.mark.parametrize(
    "count,expected",
    [
        (0, Reuse.INCOMPATIBLE),
        (1, Reuse.FIRST_USE),
        (2, Reuse.REUSED),
        (3, Reuse.HEAVILY_REUSED),
        (4, Reuse.HEAVILY_REUSED),
    ],
)
def test_reuse_threshold(count: int, expected: Reuse) -> None:
    assert classify_reuse(count, 3) is expected


@pytest.mark.parametrize("count,heavy", [(-1, 3), (2001, 3), (1, 2), (True, 3), (1, 2001)])
def test_reuse_policy_bounds(count: int, heavy: int) -> None:
    with pytest.raises(ContractError):
        classify_reuse(count, heavy)

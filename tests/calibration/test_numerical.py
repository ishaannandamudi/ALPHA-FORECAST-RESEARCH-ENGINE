"""Independent known numeric fixtures; no apparent improvement acceptance logic."""

from dataclasses import replace

import pytest

from afre.calibration import CalibrationBinDefinition, EmptyBinPolicy, QuantileOffset
from afre.calibration.artifacts import IntervalValue
from afre.calibration.conformal import conformal_rank
from afre.calibration.diagnostics import diagnostics_for
from afre.calibration.isotonic import isotonic_probability, pav
from afre.calibration.probability import bin_index, binned
from afre.calibration.quantile import adjusted_quantiles
from afre.probabilistic import (
    QuantileValue,
    ThresholdComparison,
    ThresholdProbability,
    ThresholdRequest,
)
from afre.probabilistic.quantiles import empirical_quantile
from afre.schema import ContractError


def oid(number: int) -> str:
    return f"afre.c_observation:1.0:{number:064x}"


def test_pav_pooling_ties_and_order() -> None:
    pairs = (
        (0.1, False, oid(1)),
        (0.2, True, oid(2)),
        (0.2, False, oid(3)),
        (0.3, False, oid(4)),
        (0.8, True, oid(5)),
    )
    blocks = pav(pairs)
    assert [(b.lower, b.upper, b.count, b.successes, b.probability) for b in blocks] == [
        (0.1, 0.1, 1, 0, 0.0),
        (0.2, 0.3, 3, 1, 1 / 3),
        (0.8, 0.8, 1, 1, 1.0),
    ]
    assert pav(tuple(reversed(pairs))) == blocks
    assert blocks[1].observation_ids == (oid(2), oid(3), oid(4))
    assert isotonic_probability(blocks, 0.0) == 0
    assert isotonic_probability(blocks, 1.0) == 1
    assert isotonic_probability(blocks, 0.25) == 1 / 3
    assert isotonic_probability(blocks, 0.55) == pytest.approx(2 / 3)
    result = [isotonic_probability(blocks, i / 1000) for i in range(1001)]
    assert all(0 <= p <= 1 for p in result)
    assert result == sorted(result)


@pytest.mark.parametrize(
    "pairs",
    [
        (),
        ((-0.1, False, oid(1)),),
        ((1.1, True, oid(1)),),
        ((0.5, True, oid(1)), (0.6, False, oid(1))),
        ((float("nan"), True, oid(1)),),
    ],
)
def test_invalid_pav(pairs: tuple[tuple[float, bool, str], ...]) -> None:
    with pytest.raises(ContractError):
        pav(pairs)


def test_binned_rates_and_empty_policy() -> None:
    definition = CalibrationBinDefinition((0.0, 0.5, 0.75, 1.0))
    pairs = (
        (0.1, True, oid(1)),
        (0.2, False, oid(2)),
        (0.5, True, oid(3)),
        (1.0, False, oid(4)),
    )
    bins = binned(pairs, definition)
    assert tuple(b.calibrated_probability for b in bins) == (0.5, 1.0, 0.0)
    assert binned(tuple(reversed(pairs)), definition) == bins
    assert bin_index(definition.edges, 0.5) == 1
    assert bin_index(definition.edges, 1.0) == 2
    sparse = binned(pairs[:1], definition)
    assert sparse[1].count == 0 and sparse[1].calibrated_probability is None
    assert (
        binned(pairs[:1], replace(definition, minimum_count=2))[0].calibrated_probability
        is None
    )
    with pytest.raises(ContractError, match="insufficient bin"):
        binned(pairs[:1], replace(definition, empty_policy=EmptyBinPolicy.FAIL))


@pytest.mark.parametrize(
    ("n", "alpha", "expected"),
    [(4, 0.4, 3), (9, 0.2, 8), (7, 0.2, 7), (19, 0.05, 19), (99, 0.1, 90)],
)
def test_exact_conformal_rank(n: int, alpha: float, expected: int) -> None:
    assert conformal_rank(n, alpha) == expected


@pytest.mark.parametrize(
    ("n", "alpha"), [(0, 0.2), (2, 0.01), (9, 0.0), (9, 1.0), (9, float("nan"))]
)
def test_conformal_rank_rejects(n: int, alpha: float) -> None:
    with pytest.raises(ContractError):
        conformal_rank(n, alpha)


def test_quantile_offset_non_crossing_and_exact_level() -> None:
    raw = (QuantileValue(0.1, -1.0), QuantileValue(0.5, 0.0), QuantileValue(0.9, 1.0))
    offset = QuantileOffset(
        "afre.c_spec:1.0:" + "0" * 64,
        "afre.c_observations:1.0:" + "0" * 64,
        0.1,
        0.5,
        (0.5,),
        (oid(1),),
    )
    result = adjusted_quantiles(raw, (offset,))
    assert result[0].value == -0.5
    assert result[1:] == raw[1:]
    with pytest.raises(ContractError, match="crossing"):
        adjusted_quantiles(raw, (replace(offset, offset=2.0),))
    with pytest.raises(ContractError, match="level identity"):
        adjusted_quantiles(raw, (replace(offset, level=0.05),))
    with pytest.raises(ContractError, match="level identity"):
        adjusted_quantiles(raw, (offset, offset))
    assert empirical_quantile((1.0, 2.0, 3.0, 4.0), 0.25) == 1.75


def test_exact_reliability_brier_ece_coverage_and_width() -> None:
    event = ThresholdRequest(0.0, ThresholdComparison.GT)
    qs = (QuantileValue(0.1, -1.0), QuantileValue(0.5, 0.0), QuantileValue(0.9, 1.0))
    interval = IntervalValue(0.1, 0.9, -1.0, 1.0)
    rows = tuple(
        (truth, qs, (ThresholdProbability(event, p),), interval)
        for truth, p in ((1.0, 0.2), (-1.0, 0.2), (2.0, 0.8), (-2.0, 0.8))
    )
    calibrated = tuple((r[0], r[1], (ThresholdProbability(event, 0.5),), r[3]) for r in rows)
    diagnostic = diagnostics_for(
        rows, calibrated, CalibrationBinDefinition((0.0, 0.5, 1.0)), "independent-evaluation"
    )
    before, after = diagnostic.raw_events[0], diagnostic.calibrated_events[0]
    assert before.ece == pytest.approx(0.3) and before.mce == pytest.approx(0.3)
    assert before.brier == pytest.approx(0.34) and after.brier == 0.25
    assert after.ece == 0.0
    assert diagnostic.raw_quantiles[1].observed_frequency == 0.5
    assert diagnostic.raw_interval is not None
    assert diagnostic.raw_interval.coverage == 0.5
    assert diagnostic.raw_interval.absolute_gap == pytest.approx(0.3)
    assert diagnostic.raw_interval.mean_width == 2.0
    empty = diagnostics_for((), (), CalibrationBinDefinition(), "independent-evaluation")
    assert empty.raw_events == () and empty.raw_interval is None


def test_exchangeable_conformal_leave_one_out_fixture() -> None:
    scores = tuple(float(i) for i in range(1, 11))
    rank = conformal_rank(9, 0.2)
    covered = 0
    for heldout in scores:
        training = tuple(v for v in scores if v != heldout)
        q_hat = training[rank - 1]
        covered += heldout <= q_hat
    assert covered / 10 == 0.8


def test_PAV_against_exhaustive_monotone_partition_oracle() -> None:
    from itertools import product

    n = 5
    for outcomes in product((False, True), repeat=n):
        pairs = tuple(((i + 1) / 6, y, oid(i + 1)) for i, y in enumerate(outcomes))
        blocks = pav(pairs)
        fitted = [isotonic_probability(blocks, p) for p, _, _ in pairs]
        loss = sum((p - float(y)) ** 2 for p, y in zip(fitted, outcomes, strict=True))
        candidates = []
        for boundaries in product((False, True), repeat=n - 1):
            groups: list[list[bool]] = [[outcomes[0]]]
            for split, y in zip(boundaries, outcomes[1:], strict=True):
                if split:
                    groups.append([])
                groups[-1].append(y)
            rates = [sum(g) / len(g) for g in groups]
            if rates == sorted(rates):
                candidates.append(
                    sum(
                        (rate - float(y)) ** 2
                        for g, rate in zip(groups, rates, strict=True)
                        for y in g
                    )
                )
        assert loss == pytest.approx(min(candidates), abs=1e-14)

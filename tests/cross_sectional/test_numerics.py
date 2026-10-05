"""Independent small-vector reference fixtures, including exact tied conventions."""

import math
from dataclasses import replace

import pytest

from afre.cross_sectional import (
    CrossSectionQuality,
    CrossSectionScoreState,
    NormalizationPolicy,
    PeerTransform,
    RankDirection,
    RankingLayer,
    RankTiePolicy,
    RawScore,
    SmallGroupPolicy,
    rank_values,
)
from afre.cross_sectional.normalization import peer_state
from afre.schema import ContractError
from tests.cross_sectional.conftest import Case


@pytest.mark.parametrize("direction", list(RankDirection))
def test_rank_fixture(direction: RankDirection) -> None:
    result = rank_values(
        (("A", 3.0), ("B", 1.0), ("C", 2.0)), direction, RankTiePolicy.AVERAGE_RANK
    )
    assert (
        result == (("A", 1.0, 1.0), ("B", 3.0, 0.0), ("C", 2.0, 0.5))
        if direction is RankDirection.HIGHER_BETTER
        else result == (("A", 3.0, 0.0), ("B", 1.0, 1.0), ("C", 2.0, 0.5))
    )


@pytest.mark.parametrize(
    "ties,expected",
    [
        (RankTiePolicy.AVERAGE_RANK, (1.5, 1.5, 3.0)),
        (RankTiePolicy.MIN_RANK, (1.0, 1.0, 3.0)),
        (RankTiePolicy.MAX_RANK, (2.0, 2.0, 3.0)),
        (RankTiePolicy.DENSE_RANK, (1.0, 1.0, 2.0)),
    ],
)
def test_ties(ties: RankTiePolicy, expected: tuple[float, ...]) -> None:
    values = (("A", 2.0), ("B", 2.0), ("C", 1.0))
    result = rank_values(values, RankDirection.HIGHER_BETTER, ties)
    assert tuple(r for _, r, _ in result) == expected
    assert result == rank_values(tuple(reversed(values)), RankDirection.HIGHER_BETTER, ties)


def test_empty_singleton_duplicates_nonfinite() -> None:
    assert rank_values((), RankDirection.HIGHER_BETTER, RankTiePolicy.AVERAGE_RANK) == ()
    assert rank_values((("A", 1.0),), RankDirection.HIGHER_BETTER, RankTiePolicy.MIN_RANK) == (
        ("A", 1.0, 0.5),
    )
    for values in ((("A", 1.0), ("A", 2.0)), (("A", float("inf")),)):
        with pytest.raises(ContractError):
            rank_values(values, RankDirection.HIGHER_BETTER, RankTiePolicy.MIN_RANK)


@pytest.mark.parametrize("transform", list(PeerTransform))
@pytest.mark.parametrize("direction", list(RankDirection))
def test_peer_normalization(
    case: Case, transform: PeerTransform, direction: RankDirection
) -> None:
    f = case.fixture
    spec = replace(
        f.spec,
        normalization=NormalizationPolicy(transform),
        direction=direction,
        ranking_layer=RankingLayer.NORMALIZED,
    )
    ranking = case.engine.build_ranking(spec, f.sources, f.group_refs)
    included = sorted(
        (e for e in ranking.entries if e.raw is not None), key=lambda e: e.raw or 0
    )
    if transform is PeerTransform.ZSCORE:
        assert [e.normalized for e in included] == pytest.approx(
            [-math.sqrt(1.5), 0.0, math.sqrt(1.5)]
        )
    elif transform is PeerTransform.MEDIAN_MAD:
        assert [e.normalized for e in included] == [-1.0, 0.0, 1.0]
    elif transform is PeerTransform.PERCENTILE:
        assert [e.normalized for e in included] == (
            [0.0, 0.5, 1.0] if direction is RankDirection.HIGHER_BETTER else [1.0, 0.5, 0.0]
        )
    else:
        assert [e.normalized for e in included] == [1.0, 2.0, 3.0]


def test_sample_std_and_explicit_mad_scale(case: Case) -> None:
    for policy, expected in (
        (NormalizationPolicy(PeerTransform.ZSCORE, sample_denominator=True), [-1.0, 0.0, 1.0]),
        (NormalizationPolicy(PeerTransform.MEDIAN_MAD, mad_scale=2.0), [-0.5, 0.0, 0.5]),
    ):
        rank = case.engine.build_ranking(
            replace(case.fixture.spec, normalization=policy),
            case.fixture.sources,
            case.fixture.group_refs,
        )
        rows = sorted((e for e in rank.entries if e.raw is not None), key=lambda e: e.raw or 0)
        assert [e.normalized for e in rows] == pytest.approx(expected)


@pytest.mark.parametrize("policy", list(SmallGroupPolicy))
def test_group_demean_and_small_group(case: Case, policy: SmallGroupPolicy) -> None:
    f = case.fixture
    assert f.spec.group is not None
    spec = replace(
        f.spec,
        group=replace(f.spec.group, small_group=policy),
        ranking_layer=RankingLayer.GROUP_NEUTRAL,
    )
    if policy is SmallGroupPolicy.FAIL:
        with pytest.raises(ContractError, match="small group"):
            case.engine.build_ranking(spec, f.sources, f.group_refs)
    else:
        rank = case.engine.build_ranking(spec, f.sources, f.group_refs)
        assert sorted(e.group_neutral for e in rank.entries if e.group_neutral is not None) == (
            [-1.0, 1.0, 2.0] if policy is SmallGroupPolicy.LEAVE_RAW else [-1.0, 1.0]
        )


@pytest.mark.parametrize("values", [(1.0, 1.0, 1.0), (1.0, 1.0, 10.0)])
def test_zero_scale_explicit(case: Case, values: tuple[float, ...]) -> None:
    f = case.fixture
    from afre.cross_sectional.artifacts import CrossSectionObservation

    observations = tuple(
        case.repo.get(CrossSectionObservation, e.observation_id) for e in f.ranking.entries[:3]
    )
    raw = tuple(
        RawScore(o.fingerprint, o.security, v, CrossSectionScoreState.AVAILABLE, 60, "fixture")
        for o, v in zip(observations, values, strict=True)
    )
    state = peer_state(
        replace(f.spec, normalization=NormalizationPolicy(PeerTransform.MEDIAN_MAD)), raw, 60
    )
    assert state.quality is CrossSectionQuality.CONSTANT
    assert all(v == 0 for _, v in state.values)


def test_future_peer_computation(case: Case) -> None:
    from afre.cross_sectional.artifacts import CrossSectionObservation

    o = case.repo.get(CrossSectionObservation, case.fixture.ranking.entries[0].observation_id)
    raw = RawScore(
        o.fingerprint, o.security, 3.0, CrossSectionScoreState.AVAILABLE, 61, "future"
    )
    with pytest.raises(ContractError, match="future peer"):
        peer_state(case.fixture.spec, (raw,), 60)


def test_positive_negative_and_constant_truth_ic() -> None:
    from afre.statistical_models.metrics import correlation
    from afre.statistical_models.schema import MetricState

    assert correlation((3.0, 1.0, 2.0), (6.0, 2.0, 4.0)).value == pytest.approx(1.0)
    assert correlation((3.0, 1.0, 2.0), (-6.0, -2.0, -4.0)).value == pytest.approx(-1.0)
    constant = correlation((3.0, 1.0, 2.0), (1.0, 1.0, 1.0))
    assert constant.value is None and constant.state is MetricState.CONSTANT_TARGET

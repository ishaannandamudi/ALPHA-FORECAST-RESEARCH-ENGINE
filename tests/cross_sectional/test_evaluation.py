"""Independent IC, tied-rank, bucket, stability and sealed TEST fixtures."""

from dataclasses import replace
from statistics import correlation as oracle_correlation

import pytest

from afre.cross_sectional import (
    CrossSectionRanking,
    CrossSectionTruth,
    RankingLayer,
    RankTiePolicy,
    StabilityMembership,
    TruthPolicy,
)
from afre.research_datasets.samples import ResearchSample
from afre.schema import ContractError
from afre.statistical_models.schema import MetricState
from examples.cross_sectional_demo import external, spec_for
from tests.cross_sectional.conftest import Case


def test_ic_top_bottom_buckets_group_oracle(case: Case) -> None:
    f = case.fixture
    result = case.engine.evaluate(f.ranking.fingerprint, f.targets, 100, 100, bucket_count=3)
    truth = case.repo.get(CrossSectionTruth, result.truth_id)
    y = {r.security.fingerprint: r.value for r in truth.rows if r.value is not None}
    included = [e for e in f.ranking.entries if e.rank is not None]
    assert result.pearson.sample_count == result.rank_ic.sample_count == 3
    assert result.pearson.value == pytest.approx(
        oracle_correlation(
            [e.raw for e in included if e.raw is not None],
            [y[e.security.fingerprint] for e in included],
        )
    )
    assert result.rank_ic.value == pytest.approx(-1.0)
    best = min(included, key=lambda e: e.rank or 0).security.fingerprint
    worst = max(included, key=lambda e: e.rank or 0).security.fingerprint
    assert result.top_ids == (best,) and result.bottom_ids == (worst,)
    assert result.top_mean == y[best] and result.bottom_mean == y[worst]
    assert result.spread == pytest.approx(y[best] - y[worst])
    assert all(len(b.securities) == 1 for b in result.buckets)
    assert result.monotone_fraction == 0.0
    assert result.group_ic.sample_count == 2 and result.group_ic.value == pytest.approx(-1.0)
    assert len(result.group_securities) == 2 and len(result.excluded) == 1
    assert (
        case.engine.evaluate(f.ranking.fingerprint, f.targets, 100, 100, bucket_count=3)
        == result
    )


@pytest.mark.parametrize("tie", list(RankTiePolicy))
def test_rank_ic_declared_ties(case: Case, tie: RankTiePolicy) -> None:
    f = case.fixture
    sources = []
    ordered = sorted(
        (e for e in f.ranking.entries if e.rank is not None), key=lambda e: e.raw or 0
    )
    for entry, value in zip(ordered, (1.0, 3.0, 3.0), strict=True):
        sources.append(
            (
                entry.security.fingerprint,
                case.engine.publish_external(external(entry.security, 60, value)),
            )
        )
    ranking = case.engine.build_ranking(replace(f.spec, ties=tie), tuple(sources), f.group_refs)
    result = case.engine.evaluate(ranking.fingerprint, f.targets, 100, 100)
    # Truth strictly descends as the sorted original score increases.
    xr = {
        RankTiePolicy.AVERAGE_RANK: [3.0, 1.5, 1.5],
        RankTiePolicy.MIN_RANK: [3.0, 1.0, 1.0],
        RankTiePolicy.MAX_RANK: [3.0, 2.0, 2.0],
        RankTiePolicy.DENSE_RANK: [2.0, 1.0, 1.0],
    }[tie]
    assert result.rank_ic.value == pytest.approx(oracle_correlation(xr, [1.0, 2.0, 3.0]))


def test_degenerate_ic_insufficient_diagnostics(case: Case) -> None:
    f = case.fixture
    sources = tuple(
        (e.security.fingerprint, case.engine.publish_external(external(e.security, 60, 1.0)))
        for e in f.ranking.entries
    )
    rank = case.engine.build_ranking(f.spec, sources, f.group_refs)
    result = case.engine.evaluate(
        rank.fingerprint, f.targets, 100, 100, top_k=3, bucket_count=10
    )
    assert (
        result.pearson.value is None and result.pearson.state is MetricState.CONSTANT_PREDICTION
    )
    assert result.rank_ic.value is None
    assert result.top_mean is None and result.spread is None and result.buckets == ()


def test_truth_unavailable_declared_intersection(case: Case) -> None:
    f = case.fixture
    with pytest.raises(ContractError, match="complete truth"):
        case.engine.evaluate(f.ranking.fingerprint, f.targets, 64, 64)
    result = case.engine.evaluate(
        f.ranking.fingerprint, f.targets, 64, 64, policy=TruthPolicy.AVAILABLE_INTERSECTION
    )
    assert result.pearson.sample_count == 0 and result.pearson.value is None
    assert len(result.excluded) == 4
    truth = case.repo.get(CrossSectionTruth, result.truth_id)
    assert all(r.value is None for r in truth.rows)


@pytest.mark.parametrize(
    "kind", ["missing-grid", "duplicate", "wrong-origin", "wrong-target", "before-ranking"]
)
def test_truth_rejects_invalid_evidence(case: Case, kind: str) -> None:
    f = case.fixture
    targets, cutoff = f.targets, 100
    if kind == "missing-grid":
        targets = targets[:-1]
    elif kind == "duplicate":
        targets += (targets[0],)
    elif kind in ("wrong-origin", "wrong-target"):
        p = f.upstream.tests[0][0] if kind == "wrong-origin" else f.upstream.deployment[1][0]
        sample = case.repo.get(ResearchSample, p.input.sample_id or "")
        targets = tuple(
            (s, sample.target_id if s == sample.security.fingerprint else i) for s, i in targets
        )
    else:
        cutoff = 59
    with pytest.raises(ContractError):
        case.engine.evaluate(f.ranking.fingerprint, targets, cutoff, cutoff)


def second_ranking(
    case: Case,
) -> tuple[CrossSectionRanking, tuple[tuple[str, str | None], ...]]:
    f = case.fixture
    spec = replace(spec_for(case.repo, f.upstream.tests[0]), group=f.spec.group)
    sources, targets = [], []
    for i, p in enumerate(
        sorted(f.upstream.tests[0], key=lambda p: p.input.origin.instrument.fingerprint)
    ):
        sample = case.repo.get(ResearchSample, p.input.sample_id or "")
        sources.append(
            (
                sample.security.fingerprint,
                case.engine.publish_external(external(sample.security, 80, float(i + 1))),
            )
        )
        targets.append((sample.security.fingerprint, sample.target_id))
    return case.engine.build_ranking(spec, tuple(sources), f.group_refs), tuple(targets)


def test_stability_intersection_counts_oracles(case: Case) -> None:
    second, _ = second_ranking(case)
    previous = case.fixture.ranking
    result = case.engine.stability(previous.fingerprint, second.fingerprint)
    assert len(result.intersection_ids) == 3 and len(result.added_ids) == 1
    assert result.removed_ids == () and result.membership_turnover == 0.25
    assert result.top_overlap_count == 0 and result.top_overlap_fraction == 0.0
    assert result.spearman.value == pytest.approx(-0.5)
    assert result.mean_rank_displacement is not None
    with pytest.raises(ContractError, match="same ranked"):
        case.engine.stability(
            previous.fingerprint, second.fingerprint, policy=StabilityMembership.SAME_MEMBERS
        )
    with pytest.raises(ContractError, match="stability origins"):
        case.engine.stability(second.fingerprint, previous.fingerprint)


def test_ic_series_summary_and_duplicate_origin(case: Case) -> None:
    second, targets = second_ranking(case)
    f = case.fixture
    first = case.engine.evaluate(f.ranking.fingerprint, f.targets, 100, 100)
    later = case.engine.evaluate(second.fingerprint, targets, 100, 100)
    for rank_ic in (False, True):
        result = case.engine.aggregate_ic((later.fingerprint, first.fingerprint), rank_ic)
        values = (
            [first.rank_ic.value, later.rank_ic.value]
            if rank_ic
            else [first.pearson.value, later.pearson.value]
        )
        assert all(v is not None for v in values)
        assert result.mean == pytest.approx(sum(v for v in values if v is not None) / 2)
        assert result.defined_count == result.total_count == 2
        assert result.positive_fraction == sum(v > 0 for v in values if v is not None) / 2
        assert (
            case.engine.aggregate_ic((first.fingerprint, later.fingerprint), rank_ic) == result
        )
    another = case.engine.evaluate(f.ranking.fingerprint, f.targets, 100, 100, bucket_count=3)
    with pytest.raises(ContractError, match="duplicate"):
        case.engine.aggregate_ic((first.fingerprint, another.fingerprint))


def test_native_test_boundary_and_reuse(case: Case) -> None:
    f = case.fixture
    forecasts = f.upstream.tests[0]
    sources = tuple(
        (
            case.repo.get(ResearchSample, p.input.sample_id or "").security.fingerprint,
            p.point_forecast_id,
        )
        for p in forecasts
    )
    ranking = case.engine.build_ranking(spec_for(case.repo, forecasts, False), sources)
    targets = tuple(
        (
            case.repo.get(ResearchSample, p.input.sample_id or "").security.fingerprint,
            case.repo.get(ResearchSample, p.input.sample_id or "").target_id,
        )
        for p in forecasts
    )
    with pytest.raises(ContractError, match="explicit TEST"):
        case.engine.evaluate(ranking.fingerprint, targets, 100, 100)
    result = case.engine.evaluate(
        ranking.fingerprint, targets, 100, 100, test_evaluation_identity="cross-section-test"
    )
    truth = case.repo.get(CrossSectionTruth, result.truth_id)
    assert len(truth.test_evaluation_ids) == 1
    assert (
        case.engine.evaluate(
            ranking.fingerprint,
            targets,
            100,
            100,
            test_evaluation_identity="cross-section-test",
        )
        == result
    )
    with pytest.raises(ContractError, match="identity reuse"):
        case.engine.evaluate(
            ranking.fingerprint,
            targets,
            101,
            101,
            test_evaluation_identity="cross-section-test",
        )
    another = case.engine.evaluate(
        ranking.fingerprint, targets, 100, 100, test_evaluation_identity="second-test-access"
    )
    assert another.fingerprint != result.fingerprint


def test_group_neutral_evaluation(case: Case) -> None:
    f = case.fixture
    rank = case.engine.build_ranking(
        replace(f.spec, ranking_layer=RankingLayer.GROUP_NEUTRAL), f.sources, f.group_refs
    )
    result = case.engine.evaluate(rank.fingerprint, f.targets, 100, 100)
    assert result.group_ic.value == pytest.approx(-1.0)
    assert result.group_ic.sample_count == 2

"""Same-origin, eligibility, peer clocks, explicit exclusions and source semantics."""

from dataclasses import replace

import pytest

from afre.cross_sectional import (
    CrossSectionObservation,
    CrossSectionQuality,
    CrossSectionScoreState,
    MissingScorePolicy,
    NormalizationPolicy,
    RankingLayer,
    ScoreSource,
    ScoreSpec,
    SmallGroupPolicy,
)
from afre.cross_sectional.scoring import score_for
from afre.probabilistic.artifacts import ProbabilisticForecast
from afre.research_datasets.samples import ResearchSample
from afre.schema import ContractError
from afre.serialization import canonical_json
from afre.target_engine.models import TargetVintage
from afre.universe.identity import StableSecurityId
from examples.cross_sectional_demo import external, group, spec_for
from tests.cross_sectional.conftest import Case


def test_missing_late_coverage(case: Case) -> None:
    rank = case.fixture.ranking
    assert rank.eligible_count == 4 and rank.ranked_count == 3 and rank.coverage == 0.75
    excluded = [e for e in rank.entries if e.rank is None]
    assert len(excluded) == 1 and excluded[0].state is CrossSectionScoreState.FUTURE
    assert excluded[0].raw is None and "not-received" in excluded[0].reason
    assert rank.available_ns == 60


@pytest.mark.parametrize("policy", list(MissingScorePolicy))
def test_missing_policy(case: Case, policy: MissingScorePolicy) -> None:
    f = case.fixture
    spec = replace(f.spec, missing=policy)
    if policy is MissingScorePolicy.FAIL_ON_MISSING:
        with pytest.raises(ContractError, match="missing score"):
            case.engine.build_ranking(spec, f.sources[:-1], f.group_refs)
    else:
        rank = case.engine.build_ranking(spec, f.sources[:-1], f.group_refs)
        assert len(rank.entries) == 4 and rank.ranked_count < 4


def test_future_signal_cannot_affect_normalization(case: Case) -> None:
    f = case.fixture
    late = next(e for e in f.ranking.entries if e.state is CrossSectionScoreState.FUTURE)
    changed = case.engine.publish_external(external(late.security, 60, 1e100, 62))
    sources = tuple((s, changed if s == late.security.fingerprint else i) for s, i in f.sources)
    rank = case.engine.build_ranking(f.spec, sources, f.group_refs)
    assert tuple((e.raw, e.normalized, e.rank, e.percentile) for e in rank.entries) == tuple(
        (e.raw, e.normalized, e.rank, e.percentile) for e in f.ranking.entries
    )
    assert rank.fingerprint != f.ranking.fingerprint


def test_insertion_order_idempotence(case: Case) -> None:
    f = case.fixture
    assert (
        case.engine.build_ranking(
            f.spec, tuple(reversed(f.sources)), tuple(reversed(f.group_refs))
        )
        == f.ranking
    )
    assert canonical_json(
        case.repo.get(type(f.ranking), f.ranking.fingerprint)
    ) == canonical_json(f.ranking)


@pytest.mark.parametrize(
    "kind", ["duplicate-source", "duplicate-group", "ineligible", "late-compute"]
)
def test_invalid_build(case: Case, kind: str) -> None:
    f = case.fixture
    sources, groups, at = f.sources, f.group_refs, 60
    if kind == "duplicate-source":
        sources += (sources[0],)
    elif kind == "duplicate-group":
        groups += (groups[0],)
    elif kind == "ineligible":
        sources += (
            (StableSecurityId("synthetic-security", "0003").fingerprint, sources[0][1]),
        )
    else:
        at = 61
    with pytest.raises(ContractError):
        case.engine.build_ranking(f.spec, sources, groups, at)


def test_excess_missingness_and_minimum_count(case: Case) -> None:
    f = case.fixture
    rank = case.engine.build_ranking(
        replace(f.spec, maximum_missing_fraction=0.1), f.sources, f.group_refs
    )
    assert rank.ranked_count == 0 and rank.quality is CrossSectionQuality.EXCESSIVE_MISSINGNESS
    rank = case.engine.build_ranking(
        replace(f.spec, normalization=NormalizationPolicy(minimum_count=5)),
        f.sources,
        f.group_refs,
    )
    assert rank.ranked_count == 0 and rank.quality is CrossSectionQuality.TOO_SMALL
    rank = case.engine.build_ranking(f.spec, (), f.group_refs)
    assert rank.quality is CrossSectionQuality.UNAVAILABLE


@pytest.mark.parametrize("kind", ["origin", "target", "model"])
def test_native_mixed_sources(case: Case, kind: str) -> None:
    f = case.fixture
    ps = f.upstream.tests[0] if kind == "origin" else f.upstream.deployment[1]
    replacement = ps[0]
    sample = case.repo.get(ResearchSample, replacement.input.sample_id or "")
    if kind == "model":
        spec = replace(
            f.native_spec,
            score=ScoreSpec(
                ScoreSource.POINT_PREDICTION,
                model_id=f.upstream.spec.bindings[1].point_model_id,
            ),
        )
        p = f.upstream.deployment[0][0]
        sample = case.repo.get(ResearchSample, p.input.sample_id or "")
        replacement = p
    else:
        spec = f.native_spec
    with pytest.raises(ContractError):
        case.engine.build_ranking(
            spec, ((sample.security.fingerprint, replacement.point_forecast_id),)
        )


@pytest.mark.parametrize("calibrated", [False, True])
@pytest.mark.parametrize(
    "source",
    [
        ScoreSource.POINT_EXPECTATION,
        ScoreSource.MEDIAN,
        ScoreSource.QUANTILE,
        ScoreSource.THRESHOLD_PROBABILITY,
    ],
)
def test_probabilistic_sources(case: Case, calibrated: bool, source: ScoreSource) -> None:
    f = case.fixture
    binding = f.upstream.spec.bindings[0]
    first = f.upstream.deployment[0][0]
    score = ScoreSpec(
        source,
        binding.calibration_state_id if calibrated else binding.probability_model_id,
        calibrated,
        quantile=0.5 if source is ScoreSource.QUANTILE else None,
        event=first.threshold_probabilities[0].request
        if source is ScoreSource.THRESHOLD_PROBABILITY
        else None,
    )
    spec = replace(f.native_spec, score=score)
    sources = []
    for bundle in f.upstream.bundles:
        entry = bundle.entries[0]
        sample = next(p for p in f.upstream.deployment[0] if p.input.origin == bundle.origin)
        security = case.repo.get(ResearchSample, sample.input.sample_id or "").security
        identity = entry.calibrated_forecast_id if calibrated else entry.probability_forecast_id
        assert identity is not None
        sources.append((security.fingerprint, identity))
    ranking = case.engine.build_ranking(spec, tuple(sources))
    assert ranking.ranked_count == 4


def test_target_free_native_and_external(case: Case, monkeypatch: pytest.MonkeyPatch) -> None:
    original = case.repo.get

    def forbidden(cls: type[TargetVintage], identity: str) -> TargetVintage:
        assert cls is not TargetVintage, "ranking read truth"
        return original(cls, identity)

    monkeypatch.setattr(case.repo, "get", forbidden)
    f = case.fixture
    assert case.engine.build_ranking(f.spec, f.sources, f.group_refs) == f.ranking
    sources = tuple(
        (
            case.repo.get(ResearchSample, p.input.sample_id or "").security.fingerprint,
            p.point_forecast_id,
        )
        for p in f.upstream.deployment[0]
    )
    assert case.engine.build_ranking(f.native_spec, sources).ranked_count == 4


def test_full_origin_context(case: Case) -> None:
    f = case.fixture
    o = case.repo.get(CrossSectionObservation, f.ranking.entries[0].observation_id)
    changed = replace(o, origin=replace(o.origin, build_context="different-build"))
    with pytest.raises(ContractError, match="mixed"):
        score_for(case.repo, f.spec, changed)


@pytest.mark.parametrize("kind", ["future", "taxonomy", "security", "validity"])
def test_group_pit_failure(case: Case, kind: str) -> None:
    f = case.fixture
    first = f.ranking.entries[0]
    g = group(first.security, "later", 90 if kind == "future" else 0)
    if kind == "taxonomy":
        g = replace(g, taxonomy="different-taxonomy")
    elif kind == "security":
        g = replace(g, security=f.ranking.entries[1].security)
    elif kind == "validity":
        from afre.time import TimeRange

        g = replace(g, validity=TimeRange(61, 100))
    identity = case.engine.publish_group(g)
    refs = tuple(
        (s, identity if s == first.security.fingerprint else i) for s, i in f.group_refs
    )
    with pytest.raises(ContractError, match="PIT|duplicate group"):
        case.engine.build_ranking(f.spec, f.sources, refs)


def test_later_group_reclassification_frozen(case: Case) -> None:
    f = case.fixture
    for entry in f.ranking.entries:
        case.engine.publish_group(group(entry.security, "current-sector", 90))
    assert case.engine.build_ranking(f.spec, f.sources, f.group_refs) == f.ranking
    assert case.engine.audit_lineage(f.ranking.fingerprint).root_id == f.ranking.fingerprint


def test_historical_delisted_and_new_constituents(case: Case) -> None:
    f = case.fixture
    early = tuple(
        case.repo.get(ProbabilisticForecast, r[0])
        for r in case.repo._connection.execute(
            "SELECT fingerprint FROM p_forecasts WHERE artifact_id=? AND origin_ns=40",
            (f.upstream.spec.bindings[0].probability_model_id,),
        )
    )
    ranking = case.engine.build_ranking(
        spec_for(case.repo, early, False),
        tuple(
            (
                case.repo.get(ResearchSample, p.input.sample_id or "").security.fingerprint,
                p.point_forecast_id,
            )
            for p in early
        ),
    )
    securities = {e.security.value for e in ranking.entries}
    assert "0003" in securities and "0004" not in securities
    assert "0003" not in {e.security.value for e in f.ranking.entries}


def test_missing_group_states(case: Case) -> None:
    f = case.fixture
    assert f.spec.group is not None
    spec = replace(
        f.spec,
        ranking_layer=RankingLayer.GROUP_NEUTRAL,
        group=replace(f.spec.group, small_group=SmallGroupPolicy.MARK_UNAVAILABLE),
    )
    rank = case.engine.build_ranking(spec, f.sources, ())
    assert rank.ranked_count == 0
    assert spec.group is not None
    with pytest.raises(ContractError, match="missing group"):
        case.engine.build_ranking(
            replace(spec, group=replace(spec.group, small_group=SmallGroupPolicy.FAIL)),
            f.sources,
        )

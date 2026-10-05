"""Offline same-origin rankings, causal synthetic providers and later diagnostics."""

from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory

from afre.cross_sectional import (
    CrossSectionEngine,
    CrossSectionIdentity,
    CrossSectionRanking,
    CrossSectionRepository,
    CrossSectionSpec,
    ExternalSignal,
    GroupMembership,
    GroupPolicy,
    GroupType,
    NormalizationPolicy,
    PeerTransform,
    RankingLayer,
    ScoreSource,
    ScoreSpec,
    SignalQuality,
    SmallGroupPolicy,
)
from afre.feature_store.models import SourceReference
from afre.hashing import bytes_digest
from afre.lineage import ProvenanceRef
from afre.probabilistic.artifacts import ProbabilisticForecast
from afre.research_datasets.samples import ResearchSample
from afre.serialization import canonical_json
from afre.statistical_models.artifacts import PointForecast
from afre.time import TimeRange
from afre.universe.identity import StableSecurityId
from afre.universe.models import UniverseSnapshot
from examples.feature_store_demo import clocks
from examples.multihorizon_demo import MultiHorizonFixture, build_fixture


def provider_source(
    provider: str = "synthetic-specialist", version: str = "1"
) -> SourceReference:
    return SourceReference(
        ProvenanceRef(
            provider, "offline-signal-evidence", version, bytes_digest(b"synthetic-evidence")
        ),
        ProvenanceRef(
            provider, "offline-data", version, bytes_digest(b"synthetic-data")
        ).fingerprint,
    )


def external(
    security: StableSecurityId, at: int, value: float, received: int | None = None
) -> ExternalSignal:
    return ExternalSignal(
        "synthetic-specialist",
        "1",
        "1.0",
        security,
        "microstructure.specialist_prediction",
        "1",
        "relative-target-score-v1",
        at,
        clocks(at if received is None else received),
        value,
        "dimensionless",
        SignalQuality.VALID,
        provider_source(),
    )


def group(security: StableSecurityId, group_id: str, received: int = 0) -> GroupMembership:
    return GroupMembership(
        security,
        GroupType.SECTOR,
        group_id,
        "synthetic-classifier",
        "synthetic-taxonomy",
        "1",
        TimeRange(0, 1000),
        clocks(received),
        provider_source("synthetic-classifier"),
    )


@dataclass(frozen=True)
class CrossSectionFixture:
    upstream: MultiHorizonFixture
    spec: CrossSectionSpec
    native_spec: CrossSectionSpec
    sources: tuple[tuple[str, str], ...]
    group_refs: tuple[tuple[str, str], ...]
    targets: tuple[tuple[str, str | None], ...]
    ranking: CrossSectionRanking


def spec_for(
    repo: CrossSectionRepository,
    forecasts: tuple[ProbabilisticForecast, ...],
    external_score: bool = True,
) -> CrossSectionSpec:
    first = min(forecasts, key=lambda p: p.input.origin.instrument.fingerprint)
    sample = repo.get(ResearchSample, first.input.sample_id or "")
    snapshot = repo.get(UniverseSnapshot, sample.snapshot_id)
    target = repo.get_any(first.target_definition_id)
    from afre.target_engine.definitions import TargetDefinition

    assert isinstance(target, TargetDefinition)
    identity = CrossSectionIdentity(
        first.input.origin,
        snapshot.fingerprint,
        target,
        snapshot.definition.eligibility.fingerprint,
    )
    score = (
        ScoreSpec(
            ScoreSource.EXTERNAL_SIGNAL,
            provider_name="synthetic-specialist",
            provider_version="1",
            provider_schema="1.0",
            signal_name="microstructure.specialist_prediction",
            signal_version="1",
            signal_semantics="relative-target-score-v1",
            unit="dimensionless",
        )
        if external_score
        else ScoreSpec(
            ScoreSource.POINT_PREDICTION,
            model_id=repo.get(PointForecast, first.point_forecast_id).model_artifact_id,
        )
    )
    return CrossSectionSpec(identity, score)


def cross_fixture(repo: CrossSectionRepository, reverse: bool = False) -> CrossSectionFixture:
    upstream = build_fixture(repo, reverse=reverse)
    forecasts = upstream.deployment[0]
    spec = replace(
        spec_for(repo, forecasts),
        group=GroupPolicy(
            GroupType.SECTOR,
            "synthetic-classifier",
            "synthetic-taxonomy",
            "1",
            small_group=SmallGroupPolicy.LEAVE_RAW,
        ),
    )
    engine = CrossSectionEngine(repo)
    sources, groups, targets = [], [], []
    ordered = sorted(forecasts, key=lambda p: p.input.origin.instrument.fingerprint)
    for i, p in tuple(reversed(tuple(enumerate(ordered)))) if reverse else enumerate(ordered):
        sample = repo.get(ResearchSample, p.input.sample_id or "")
        signal = external(sample.security, 60, float((3, 1, 2, 4)[i]), 61 if i == 3 else 60)
        g = group(sample.security, "sector-a" if i < 2 else "sector-b")
        sources.append((sample.security.fingerprint, engine.publish_external(signal)))
        groups.append((sample.security.fingerprint, engine.publish_group(g)))
        targets.append((sample.security.fingerprint, sample.target_id))
    ranking = engine.build_ranking(spec, tuple(sources), tuple(groups))
    return CrossSectionFixture(
        upstream,
        spec,
        spec_for(repo, forecasts, False),
        tuple(sources),
        tuple(groups),
        tuple(targets),
        ranking,
    )


def main() -> None:
    with TemporaryDirectory() as folder:
        path = Path(folder) / "cross-section.sqlite"
        with CrossSectionRepository(path) as repo:
            f = cross_fixture(repo)
            engine = CrossSectionEngine(repo)
            native = engine.build_ranking(
                f.native_spec,
                tuple(
                    (
                        repo.get(ResearchSample, p.input.sample_id or "").security.fingerprint,
                        p.point_forecast_id,
                    )
                    for p in f.upstream.deployment[0]
                ),
            )
            for transform in (PeerTransform.ZSCORE, PeerTransform.PERCENTILE):
                engine.build_ranking(
                    replace(
                        f.spec,
                        normalization=NormalizationPolicy(transform),
                        ranking_layer=RankingLayer.NORMALIZED,
                    ),
                    f.sources,
                    f.group_refs,
                )
            neutral = engine.build_ranking(
                replace(f.spec, ranking_layer=RankingLayer.GROUP_NEUTRAL),
                f.sources,
                f.group_refs,
            )
            evaluation = engine.evaluate(f.ranking.fingerprint, f.targets, 100, 100)
            neutral_eval = engine.evaluate(neutral.fingerprint, f.targets, 100, 100)
            second_spec = replace(spec_for(repo, f.upstream.tests[0]), group=f.spec.group)
            second_sources = []
            second_targets = []
            for i, p in enumerate(
                sorted(f.upstream.tests[0], key=lambda p: p.input.origin.instrument.fingerprint)
            ):
                sample = repo.get(ResearchSample, p.input.sample_id or "")
                s = external(sample.security, 80, float(i + 1))
                second_sources.append((sample.security.fingerprint, engine.publish_external(s)))
                second_targets.append((sample.security.fingerprint, sample.target_id))
            second = engine.build_ranking(second_spec, tuple(second_sources), f.group_refs)
            second_eval = engine.evaluate(second.fingerprint, tuple(second_targets), 100, 100)
            stability = engine.stability(f.ranking.fingerprint, second.fingerprint)
            series = engine.aggregate_ic((evaluation.fingerprint, second_eval.fingerprint))
            old = canonical_json(f.ranking)
            # A current classification cannot affect the pinned historical groups.
            for entry in f.ranking.entries:
                engine.publish_group(group(entry.security, "current-reclassified", 90))
            assert engine.build_ranking(f.spec, f.sources, f.group_refs) == f.ranking
            correction = engine.publish_external(
                external(f.ranking.entries[0].security, 60, 9.0)
            )
            corrected_sources = tuple(
                (s, correction if s == f.ranking.entries[0].security.fingerprint else i)
                for s, i in f.sources
            )
            rebuilt = engine.build_ranking(f.spec, corrected_sources, f.group_refs)
            assert rebuilt.fingerprint != f.ranking.fingerprint
            assert canonical_json(repo.get(CrossSectionRanking, f.ranking.fingerprint)) == old
            # Earlier origin includes the later delisted security.
            early = tuple(
                repo.get(ProbabilisticForecast, r[0])
                for r in repo._connection.execute(
                    "SELECT fingerprint FROM p_forecasts WHERE artifact_id=? AND origin_ns=40",
                    (f.upstream.spec.bindings[0].probability_model_id,),
                )
            )
            historical = engine.build_ranking(
                spec_for(repo, early, False),
                tuple(
                    (
                        repo.get(ResearchSample, p.input.sample_id or "").security.fingerprint,
                        p.point_forecast_id,
                    )
                    for p in early
                ),
            )
            assert {e.security for e in historical.entries} != {
                e.security for e in native.entries
            }
            audit = engine.audit_lineage(evaluation.fingerprint)
            print(
                {
                    "ranked": f.ranking.ranked_count,
                    "eligible": f.ranking.eligible_count,
                    "IC": evaluation.pearson.value,
                    "rank_IC": evaluation.rank_ic.value,
                    "descriptive_spread": evaluation.spread,
                    "group_IC": neutral_eval.group_ic.value,
                    "stability": stability.spearman.value,
                    "IC_origins": series.total_count,
                    "audit_nodes": len(audit.evidence_ids),
                }
            )
            repo.audit()

        with CrossSectionRepository(path) as repo:
            assert canonical_json(repo.get(CrossSectionRanking, f.ranking.fingerprint)) == old
            repo.audit()


def second_fixture(
    repo: CrossSectionRepository, f: CrossSectionFixture
) -> tuple[CrossSectionRanking, tuple[tuple[str, str | None], ...]]:
    """A second independent origin for demo/profile comparisons."""
    engine = CrossSectionEngine(repo)
    spec = replace(spec_for(repo, f.upstream.tests[0]), group=f.spec.group)
    sources, targets = [], []
    for i, p in enumerate(
        sorted(f.upstream.tests[0], key=lambda p: p.input.origin.instrument.fingerprint)
    ):
        sample = repo.get(ResearchSample, p.input.sample_id or "")
        sources.append(
            (
                sample.security.fingerprint,
                engine.publish_external(external(sample.security, 80, float(i + 1))),
            )
        )
        targets.append((sample.security.fingerprint, sample.target_id))
    return engine.build_ranking(spec, tuple(sources), f.group_refs), tuple(targets)


if __name__ == "__main__":
    main()

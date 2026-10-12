"""Separate real reader/writer connections append all native layers under a frozen read."""

from dataclasses import replace

from afre.challenger import ChallengeEngine, ChallengeRun, EvaluationEvidence
from afre.event_conditioned.artifacts import EventConditionedForecast
from afre.event_conditioned.events import EventReference
from afre.feature_store import FeatureVintage
from afre.health import HealthEngine, ModelHealthSnapshot
from afre.regime_conditioned.artifacts import RegimeConditionedForecast
from afre.regime_conditioned.regimes import RegimeSnapshot
from afre.selection import SelectionEngine
from afre.service import (
    AFREService,
    ServiceContextKind,
    ServiceRepository,
    ServiceStatus,
    SnapshotPublication,
    SnapshotPublisher,
    canonical_json,
)
from afre.statistical_models import PointForecast
from afre.target_engine import TargetEngine
from afre.target_engine.market_data import TargetBar, TargetSourceBuild
from afre.target_engine.models import TargetDatasetManifest
from examples.feature_store_demo import clocks, definition, source_vintage
from examples.release_workflows import selection_from_native
from tests.service.conftest import ServiceCase


def test_reader_isolation_across_native_appends(service_case: ServiceCase) -> None:
    c = service_case
    space = selection_from_native(c.repo, c.fixture.ids("point"))
    SelectionEngine(c.repo).select(space, 100, 100)
    original = c.publisher.publish(
        SnapshotPublication(c.fixture.ids("point")[0], "frozen-read", 120)
    )
    before = canonical_json(c.service.get_snapshot(original.snapshot_id))
    native_point = c.repo.get(PointForecast, original.publication.source_id)
    event_request = c.fixture.context_cases[1][1][0]
    event_forecast = c.repo.get(EventConditionedForecast, event_request.artifact_id)
    event_ids = event_forecast.event_ids
    event = c.repo.get(EventReference, event_ids[0])
    regime_forecast = c.repo.get(RegimeConditionedForecast, c.fixture.context_cases[2][0])
    assert regime_forecast.regime_snapshot_id is not None
    regime = c.repo.get(RegimeSnapshot, regime_forecast.regime_snapshot_id)
    health_id = next(
        r.artifact_id
        for r in c.fixture.context_cases[0][1]
        if r.kind is ServiceContextKind.HEALTH
    )
    health = c.repo.get(ModelHealthSnapshot, health_id)
    challenge = c.repo.get(ChallengeRun, c.fixture.context_cases[4][1][0].artifact_id)
    evidence = c.repo.get(EvaluationEvidence, challenge.evidence_id)
    row = c.repo._connection.execute(
        "SELECT fingerprint FROM target_artifacts "
        "WHERE type_name='TargetDatasetManifest' ORDER BY fingerprint LIMIT 1"
    ).fetchone()
    target_dataset = c.repo.get(TargetDatasetManifest, row[0])
    source_build = c.repo.get(TargetSourceBuild, target_dataset.source_build_id)
    bar = next(
        c.repo.get(TargetBar, i)
        for i in source_build.bar_ids
        if c.repo.get(TargetBar, i).close is not None
    )
    feature = definition("market.concurrent_release")
    tables = (
        "fs_vintages",
        "target_artifacts",
        "m_artifacts",
        "ec_artifacts",
        "rc_artifacts",
        "mt_artifacts",
        "hlt_artifacts",
        "ch_artifacts",
        "svc_artifacts",
    )

    def counts(repo: ServiceRepository) -> tuple[int, ...]:
        return tuple(
            repo._connection.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in tables
        )

    with ServiceRepository(c.path) as writer:
        with c.repo.read_snapshot():
            frozen_counts = counts(c.repo)
            with writer.transaction():
                writer.put(feature)
                vintage = source_vintage(feature, 10, 10)
                writer.put(vintage)
                writer.put(
                    replace(
                        native_point,
                        computed_ns=native_point.computed_ns + 1,
                        available_ns=native_point.available_ns + 1,
                    )
                )
                writer.put(replace(event, revision="concurrent-revision"))
                writer.put(replace(regime, revision="concurrent-revision"))
                corrected_bar = replace(
                    bar,
                    close=bar.close * 1.01 if bar.close else None,
                    predecessor_id=bar.fingerprint,
                    clocks=clocks(source_build.known_as_of_ns + 1),
                )
                writer.put(corrected_bar)
            target = TargetEngine(writer)
            new_build = target.freeze_source(
                source_build.source,
                source_build.calendar,
                source_build.known_as_of_ns + 1,
                source_build.action_stream,
                source_build.benchmark_ids,
            )
            target.build_dataset(
                "concurrent-label-revision",
                target_dataset.origins,
                target_dataset.targets,
                new_build.fingerprint,
                target_dataset.universe,
                clocks(source_build.known_as_of_ns + 1),
            )
            SelectionEngine(writer).select(
                replace(space, search_key="concurrent-search"), 100, 100
            )
            HealthEngine(writer).evaluate(health.spec_id, 121)
            challenge_engine = ChallengeEngine(writer)
            new_evidence = challenge_engine.evidence(replace(evidence, available_ns=121))
            challenge_engine.evaluate(new_evidence.fingerprint)
            publisher = SnapshotPublisher(writer)
            new_snapshot = publisher.publish(
                replace(original.publication, publication_version="concurrent")
            )
            publisher.catalog(
                "concurrent-catalog", (original.snapshot_id, new_snapshot.snapshot_id), 120
            )
            assert all(a > b for a, b in zip(counts(writer), frozen_counts, strict=True))
            assert counts(c.repo) == frozen_counts
            assert canonical_json(c.service.get_snapshot(original.snapshot_id)) == before
            assert (
                c.service.get_snapshot(new_snapshot.snapshot_id).status
                is ServiceStatus.NOT_FOUND
            )
        assert counts(c.repo) == counts(writer)
        assert isinstance(writer.get(FeatureVintage, vintage.fingerprint), FeatureVintage)
        assert AFREService(c.repo).get_snapshot(new_snapshot.snapshot_id).value == new_snapshot
    assert canonical_json(c.service.get_snapshot(original.snapshot_id)) == before

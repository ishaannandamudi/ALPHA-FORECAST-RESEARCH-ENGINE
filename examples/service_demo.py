"""Asserted offline service publication/replay with native context and actual horizons."""

import json
import os
import subprocess
from collections.abc import Callable
from dataclasses import replace
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import TypeVar

from afre.challenger import ChallengeEngine, ChallengeRun, EvaluationEvidence
from afre.fusion import FusedForecast, FusionArtifact, FusionEngine, FusionSpec
from afre.health import HealthEngine, ModelHealthSnapshot
from afre.service import (
    AFREService,
    ForecastSnapshot,
    MultiHorizonSnapshot,
    RegistryPage,
    RegistryQuery,
    ServiceLawComponent,
    ServiceProbabilityLaw,
    ServiceRepository,
    ServiceStatus,
    SnapshotBundleStatus,
    SnapshotPublication,
    SnapshotPublisher,
    SnapshotQuery,
    canonical_json,
)
from afre.service import (
    ServiceContextKind as K,
)
from afre.statistical_models.artifacts import PointForecast
from afre.target_engine.models import TargetVintage
from examples.service_fixture import ServiceFixture, build_fixture

T = TypeVar("T")


def selector(catalog_id: str, snapshot: ForecastSnapshot) -> SnapshotQuery:
    return SnapshotQuery(
        catalog_id,
        snapshot.producer_id,
        snapshot.target.fingerprint,
        snapshot.target.horizon.fingerprint,
        snapshot.origin,
        snapshot.universe_id,
        snapshot.publication.published_ns,
    )


def exercise(
    directory: Path, repo: ServiceRepository, fixture: ServiceFixture
) -> tuple[tuple[str, ...], dict[str, float]]:
    messages: list[str] = []
    timings: dict[str, float] = {}
    publisher, service = SnapshotPublisher(repo), AFREService(repo)

    def step(message: str) -> None:
        messages.append(f"{len(messages) + 1:02d}. {message}")

    def timed(name: str, action: Callable[[], T]) -> T:
        started = perf_counter()
        result = action()
        timings[name] = perf_counter() - started
        return result

    snapshots = []
    for name in (
        "point",
        "gaussian",
        "empirical",
        "calibrated",
        "mixture",
        "event",
        "hard-regime",
        "nonlinear",
        "sequence",
    ):
        source = fixture.ids(name)[0]
        snapshot = timed(
            name + "_snapshot_build",
            partial(publisher.publish, SnapshotPublication(source, "v1", 120)),
        )
        snapshots.append(snapshot)
        assert snapshot.output.point is not None and snapshot.output.artifact_id == source
        step(name + " native output preserved in an immutable snapshot")
        assert service.get_snapshot(snapshot.fingerprint).value == snapshot
        step(name + " exact public retrieval replays native semantics")
        assert publisher.publish(snapshot.publication) == snapshot
        step(name + " exact republish is idempotent")
    point, gaussian, empirical, calibrated, mixture = snapshots[:5]
    assert point.output.probability is None
    step("Point output remains a scalar target/horizon value")
    assert (
        gaussian.output.probability is not None
        and gaussian.output.probability.kind == "GAUSSIAN"
    )
    step("Gaussian location/scale remain exact")
    assert (
        empirical.output.probability is not None
        and empirical.output.probability.kind == "EMPIRICAL"
    )
    step("Empirical law exposes bounded actual atoms")
    assert (
        mixture.output.probability is not None and mixture.output.probability.kind == "MIXTURE"
    )
    step("Finite Gaussian/empirical mixture is not collapsed")
    assert calibrated.output.calibration.state == "CALIBRATED"
    step("Calibration method, artifact, version and cutoff are pinned without refitting")
    versions = service.get_version_info()
    assert versions.status is ServiceStatus.AVAILABLE
    assert getattr(versions.value, "engine", None) == "1.0.0"
    step("Engine and public API versions are explicit")
    assert (
        getattr(versions.value, "store", None) == "1.24"
        and getattr(versions.value, "sqlite_user_version", None) == 25
    )
    step("Store and SQLite schema versions are explicit")
    assert getattr(versions.value, "runtime_dependencies", None) == ()
    step("Runtime dependency declaration remains empty")
    assert service.get_capability_catalog() == versions
    step("Capability catalog advertises the implemented contract families")
    assert (
        service.get_snapshot(point.fingerprint, ("TRADING",)).status
        is ServiceStatus.UNAVAILABLE
    )
    step("Unsupported requested capability is explicit")
    assert (
        service.get_snapshot("afre.svc_snapshot:1.0:" + "0" * 64).status
        is ServiceStatus.NOT_FOUND
    )
    step("Missing identity returns a stable sanitized public error")
    with repo.request():
        try:
            identity = repo._connection.execute(
                "SELECT fingerprint FROM target_artifacts "
                "WHERE type_name='TargetVintage' LIMIT 1"
            ).fetchone()[0]
            repo.get(TargetVintage, identity)
        except ValueError:
            step("Mandatory target-free guard rejects outcome truth before caches")
        else:
            raise AssertionError("TargetVintage must be unavailable to the service")
    native_point = repo.get(PointForecast, point.publication.source_id)
    late = replace(
        native_point,
        computed_ns=native_point.available_ns + 1,
        available_ns=native_point.available_ns + 1,
    )
    with repo.transaction():
        repo.put(late)
    try:
        publisher.publish(SnapshotPublication(late.fingerprint, "late", 120))
    except ValueError:
        step("Source arriving after the origin cutoff is rejected")
    else:
        raise AssertionError("Late source must be rejected")
    quantile = publisher.publish(SnapshotPublication(fixture.ids("quantile")[0], "q", 120))
    assert quantile.output.probability is not None
    assert quantile.output.probability.kind == "QUANTILES" and not quantile.output.thresholds
    assert service.get_snapshot(quantile.fingerprint, ("QUANTILE_ONLY",)).value == quantile
    step("Native quantile-only snapshot advertises sparse quantiles without a full CDF")
    context_snapshots = []
    new_context: ModelHealthSnapshot | ChallengeRun
    for source, requests in fixture.context_cases:
        full = timed(
            "context_assembly",
            partial(publisher.publish, SnapshotPublication(source, "context", 120, requests)),
        )
        assert (
            publisher.publish(replace(full.publication, contexts=tuple(reversed(requests))))
            == full
        )
        core = publisher.publish(SnapshotPublication(source, "context-core", 120))
        assert full.output == core.output and full.fingerprint != core.fingerprint
        context_snapshots.append(full)
        for context in full.contexts:
            assert context.artifact_id in {r.artifact_id for r in requests}
            step(context.kind.value + " exact native context is pinned")
            if context.kind is K.HEALTH:
                assert (
                    service.get_health_metadata(full.fingerprint, context.artifact_id).value
                    == context
                )
                assert context.action == "NONE_DESCRIPTIVE_ONLY"
                step("Health remains descriptive and uses an exact pinned ID")
            if context.kind is K.CHALLENGE:
                assert (
                    service.get_challenge_metadata(full.fingerprint, context.artifact_id).value
                    == context
                )
                assert context.action == "MANUAL_ONLY"
                step("Champion/challenger remains MANUAL_ONLY with no active-model switch")
        assert full.final_available_ns <= full.origin.availability_cutoff_ns
        step("Optional metadata preserves source output identity and causal forecast clocks")
    all_snapshots = (*snapshots, *context_snapshots)
    catalog = timed(
        "artifact_registration",
        lambda: publisher.catalog("frozen", tuple(s.fingerprint for s in all_snapshots), 120),
    )
    q = selector(catalog.fingerprint, point)
    assert service.get_snapshot_for_origin(q).value == point
    step("Exact origin selector pins catalog/producer/target/horizon/universe/as-of")
    page = timed(
        "registry_listing",
        lambda: service.list_registry_entries(RegistryQuery(catalog.fingerprint)),
    )
    assert isinstance(page.value, RegistryPage)
    assert (
        tuple(e.fingerprint for e in page.value.entries)
        == catalog.entry_ids[: len(page.value.entries)]
    )
    listed = [e.fingerprint for e in page.value.entries]
    cursor = page.value.next_cursor
    while cursor is not None:
        continuation = service.list_registry_entries(RegistryQuery(catalog.fingerprint), cursor)
        assert isinstance(continuation.value, RegistryPage)
        listed.extend(e.fingerprint for e in continuation.value.entries)
        cursor = continuation.value.next_cursor
    assert tuple(listed) == catalog.entry_ids
    step("Registry ordering is canonical rather than incidental storage order")
    entry = timed(
        "registry_lookup", lambda: service.get_registry_entry(point.registry_entry_ids[0])
    )
    assert entry.status is ServiceStatus.AVAILABLE
    step("Registry entry lookup pins exact artifact/model metadata")
    assert (
        service.get_registry_entry_for_artifact(
            RegistryQuery(
                catalog.fingerprint,
                artifact_id=point.publication.source_id,
                producer_id=point.producer_id,
            )
        ).status
        is ServiceStatus.AVAILABLE
    )
    step("Registry artifact lookup uses frozen explicit catalog semantics")
    query = RegistryQuery(catalog.fingerprint, page_size=1)
    first = service.list_registry_entries(query)
    assert isinstance(first.value, RegistryPage) and first.value.next_cursor is not None
    next_page = service.list_registry_entries(query, first.value.next_cursor)
    assert (
        isinstance(next_page.value, RegistryPage)
        and next_page.value.entries[0] != first.value.entries[0]
    )
    step("Pagination cursor pins the full query and last key in a frozen catalog")
    horizons = tuple(
        publisher.publish(SnapshotPublication(i, "actual", 10**16)) for _, i in fixture.horizons
    )
    assert {s.target.horizon.duration_ns for s in horizons} == {3600000000000, 86400000000000}
    step("Actual 1h and 1d targets retain independent outputs")
    hc = publisher.catalog("hour-day", tuple(s.fingerprint for s in horizons), 10**16)
    queries = tuple(selector(hc.fingerprint, s) for s in horizons)
    bundle = timed("multi_horizon_bundle", lambda: service.get_multi_horizon_snapshot(queries))
    assert (
        isinstance(bundle.value, MultiHorizonSnapshot)
        and bundle.value.status is SnapshotBundleStatus.COMPLETE
    )
    assert bundle == service.get_multi_horizon_snapshot(tuple(reversed(queries)))
    step("Complete horizon bundle has canonical ordering and no pooling")
    partial_catalog = publisher.catalog("partial", (horizons[0].fingerprint,), 10**16)
    pr = service.get_multi_horizon_snapshot(
        tuple(replace(q, catalog_id=partial_catalog.fingerprint) for q in queries)
    )
    assert (
        isinstance(pr.value, MultiHorizonSnapshot)
        and pr.value.status is SnapshotBundleStatus.PARTIAL
    )
    step("Missing horizon produces explicit PARTIAL status")
    audit = timed("audit", lambda: publisher.audit(point.fingerprint))
    assert service.get_audit(audit.fingerprint).value == audit and not audit.outcomes_read
    step("Public audit pins identity, registry, versions, lineage and manual boundaries")
    assert len(audit.snapshot.lineage.node_ids) <= repo.service_bounds.lineage_nodes
    step("Forecast lineage is bounded and excludes outcome expansion")
    corrected = publisher.publish(replace(point.publication, publication_version="correction"))
    assert (
        corrected.fingerprint != point.fingerprint
        and service.get_snapshot(point.fingerprint).value == point
    )
    step("Publication correction appends a new identity while old reads remain unchanged")
    fusion_snapshot = context_snapshots[3]
    raw = repo.get(FusedForecast, fusion_snapshot.publication.source_id)
    model = repo.get(FusionArtifact, raw.artifact_id)
    spec = repo.get(FusionSpec, model.spec_id)
    weights = tuple(
        (i, 0.6 if index == 0 else 0.4) for index, (i, _) in enumerate(spec.weights)
    )
    fusion = FusionEngine(repo)
    new_model = fusion.fit(
        replace(spec, name="explicit-corrected-source", weights=weights),
        model.fit_cutoff_ns,
        model.computed_ns,
        model.available_ns,
    )
    new_source = fusion.apply(
        new_model.fingerprint, raw.sample_id, raw.observation_ids, raw.computed_ns
    )
    new_snapshot = publisher.publish(
        SnapshotPublication(new_source.fingerprint, "source-correction", 120)
    )
    assert new_snapshot.fingerprint != fusion_snapshot.fingerprint
    assert service.get_snapshot(fusion_snapshot.fingerprint).value == fusion_snapshot
    step("Native source revision creates a new snapshot without changing the old law")
    for full in (context_snapshots[0], context_snapshots[4]):
        context = next(c for c in full.contexts if c.kind in (K.HEALTH, K.CHALLENGE))
        if context.kind is K.HEALTH:
            old = repo.get(ModelHealthSnapshot, context.artifact_id)
            new_context = HealthEngine(repo).evaluate(old.spec_id, 121)
        else:
            old_run = repo.get(ChallengeRun, context.artifact_id)
            evidence = repo.get(EvaluationEvidence, old_run.evidence_id)
            engine = ChallengeEngine(repo)
            newer = engine.evidence(replace(evidence, available_ns=121))
            new_context = engine.evaluate(newer.fingerprint)
        requests = tuple(
            replace(r, artifact_id=new_context.fingerprint) if r.kind is context.kind else r
            for r in full.publication.contexts
        )
        updated = publisher.publish(
            replace(full.publication, contexts=requests, published_ns=121)
        )
        assert updated.fingerprint != full.fingerprint and updated.output == full.output
        assert service.get_snapshot(full.fingerprint).value == full
        step(context.kind.value + " correction creates a new context-bearing identity")
    law = ServiceProbabilityLaw(
        "MIXTURE",
        "independent-known-law",
        (
            ServiceLawComponent("gaussian", 0.25, "GAUSSIAN", 0.0, 1.0),
            ServiceLawComponent("empirical", 0.75, "EMPIRICAL", 0.0, 0.0, (0.0, 1.0)),
        ),
    )
    assert (
        law.threshold_probability(0.0, "GT") == 0.5
        and law.threshold_probability(0.0, "GE") == 0.875
    )
    assert (
        law.threshold_probability(0.0, "LT") == 0.125
        and law.threshold_probability(0.0, "LE") == 0.5
    )
    timings["max_numerical_error"] = 0.0
    step("Independent law oracle preserves GT/GE/LT/LE atom ties exactly")
    sparse = ServiceProbabilityLaw(
        "QUANTILES",
        "known-sparse",
        (
            ServiceLawComponent(
                "q", 1.0, "QUANTILES", 0.0, 0.0, quantiles=((0.1, -1.0), (0.5, 0.0), (0.9, 1.0))
            ),
        ),
    )
    assert sparse.kind == "QUANTILES"
    try:
        sparse.threshold_probability(0.0, "GT")
    except ValueError:
        step("Quantile-only output rejects unsupported full-law probability queries")
    else:
        raise AssertionError("Sparse quantiles cannot establish a CDF")
    replay_path = directory / "restart.sqlite"

    def persist() -> None:
        with ServiceRepository(replay_path) as copy:
            repo._connection.backup(copy._connection)

    timed("persistence", persist)
    started = perf_counter()
    with ServiceRepository(replay_path) as copy:
        timings["restart"] = perf_counter() - started
        replay = AFREService(copy)
        assert replay.get_snapshot(point.fingerprint) == service.get_snapshot(point.fingerprint)
        step("Persist/restart returns identical snapshot/service bytes")
        assert replay.list_registry_entries(RegistryQuery(catalog.fingerprint)) == page
        step("Persist/restart returns identical registry bytes")
    timings["storage_bytes"] = float(replay_path.stat().st_size)
    timed("service_replay", lambda: service.get_snapshot(point.fingerprint))
    expected = canonical_json(service.get_snapshot(point.fingerprint))
    code = (
        "from afre.service import canonical_json,deserialize; import sys; "
        "print(canonical_json(deserialize(sys.stdin.read())))"
    )
    for seed in ("0", "1", "42", "random"):
        result = subprocess.run(
            [str(Path(".venv311/bin/python").resolve()), "-c", code],
            input=expected,
            text=True,
            capture_output=True,
            check=True,
            env=dict(os.environ, PYTHONHASHSEED=seed),
        )
        assert result.stdout.strip() == expected
    step("Hash seeds 0/1/42/random preserve public semantic bytes")
    with ServiceRepository(directory / "service.sqlite") as writer:
        with repo.read_snapshot():
            before = service.get_snapshot(point.fingerprint)
            added = SnapshotPublisher(writer).publish(
                replace(point.publication, publication_version="concurrent")
            )
            assert service.get_snapshot(point.fingerprint) == before
            assert service.get_snapshot(added.fingerprint).status is ServiceStatus.NOT_FOUND
        assert service.get_snapshot(added.fingerprint).value == added
        step("Open frozen read remains unchanged during concurrent publication")
    assert (
        publisher.catalog("frozen", tuple(s.fingerprint for s in reversed(all_snapshots)), 120)
        == catalog
    )
    step(
        "Reversed registry entries, context, horizons, sources and requests "
        "retain canonical identity"
    )
    assert len(messages) >= 45
    return tuple(messages), timings


def demo(directory: Path) -> tuple[tuple[str, ...], dict[str, float]]:
    with ServiceRepository(directory / "service.sqlite") as repo:
        fixture = build_fixture(repo)
        return exercise(directory, repo, fixture)


def main() -> None:
    with TemporaryDirectory(prefix="afre-service-") as work:
        steps, timings = demo(Path(work))
        print("\n".join(steps))
        print(json.dumps(timings, sort_keys=True))
        print(f"PASS: {len(steps)} asserted offline publication/retrieval checks")


if __name__ == "__main__":
    main()

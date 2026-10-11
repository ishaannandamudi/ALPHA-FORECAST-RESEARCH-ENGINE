"""Frozen catalogs, bounded keyset cursors and independent actual hour/day snapshots."""

from dataclasses import replace

from afre.service import (
    MultiHorizonSnapshot,
    RegistryCursor,
    RegistryPage,
    RegistryQuery,
    ServiceStatus,
    SnapshotPublication,
    SnapshotQuery,
    canonical_json,
)
from afre.service import (
    SnapshotBundleStatus as B,
)
from tests.service.conftest import ServiceCase


def query_for(catalog: str, snapshot: object) -> SnapshotQuery:
    from afre.service import ForecastSnapshot

    assert isinstance(snapshot, ForecastSnapshot)
    return SnapshotQuery(
        catalog,
        snapshot.producer_id,
        snapshot.target.fingerprint,
        snapshot.target.horizon.fingerprint,
        snapshot.origin,
        snapshot.universe_id,
        snapshot.publication.published_ns,
    )


def test_actual_horizons(service_case: ServiceCase) -> None:
    c = service_case
    snapshots = tuple(
        c.publisher.publish(SnapshotPublication(i, "hour-day", 10**16))
        for _, i in c.fixture.horizons
    )
    assert {s.target.horizon.duration_ns for s in snapshots} == {3600000000000, 86400000000000}
    # Native origins agree across independent target/horizon datasets.
    catalog = c.publisher.catalog("horizons", tuple(s.fingerprint for s in snapshots), 10**16)
    queries = tuple(query_for(catalog.fingerprint, s) for s in snapshots)
    reply = c.service.get_multi_horizon_snapshot(queries)
    assert isinstance(reply.value, MultiHorizonSnapshot)
    assert reply.value.status is B.COMPLETE
    assert canonical_json(reply) == canonical_json(
        c.service.get_multi_horizon_snapshot(tuple(reversed(queries)))
    )
    partial = c.publisher.catalog("partial", (snapshots[0].fingerprint,), 10**16)
    partial_queries = tuple(replace(q, catalog_id=partial.fingerprint) for q in queries)
    bundle = c.service.get_multi_horizon_snapshot(partial_queries)
    assert isinstance(bundle.value, MultiHorizonSnapshot) and bundle.value.status is B.PARTIAL
    empty = c.publisher.catalog("empty", (), 10**16)
    unavailable = c.service.get_multi_horizon_snapshot(
        tuple(replace(q, catalog_id=empty.fingerprint) for q in queries)
    )
    assert (
        isinstance(unavailable.value, MultiHorizonSnapshot)
        and unavailable.value.status is B.UNAVAILABLE
    )
    assert c.service.get_multi_horizon_snapshot(()).status is ServiceStatus.INVALID_REQUEST
    assert (
        c.service.get_multi_horizon_snapshot((queries[0], queries[0])).status
        is ServiceStatus.INVALID_REQUEST
    )
    assert (
        c.service.get_multi_horizon_snapshot(
            (queries[0], replace(queries[1], as_of_ns=10**16 - 1))
        ).status
        is ServiceStatus.INCOMPATIBLE
    )


def test_keyset_and_registry_filters(service_case: ServiceCase) -> None:
    c = service_case
    s = c.publisher.publish(SnapshotPublication(c.fixture.ids("gaussian")[0], "v1", 120))
    catalog = c.publisher.catalog("registry", (s.fingerprint,), 120)
    query = RegistryQuery(catalog.fingerprint, page_size=1)
    identities: list[str] = []
    cursor = None
    while True:
        reply = c.service.list_registry_entries(query, cursor)
        assert isinstance(reply.value, RegistryPage)
        identities.extend(e.fingerprint for e in reply.value.entries)
        cursor = reply.value.next_cursor
        if cursor is None:
            break
    assert tuple(identities) == catalog.entry_ids
    wrong = RegistryCursor(replace(query, page_size=2).fingerprint, identities[0])
    assert c.service.list_registry_entries(query, wrong).status is ServiceStatus.INVALID_REQUEST
    assert (
        c.service.list_registry_entries(replace(query, api_version="2")).status
        is ServiceStatus.VERSION_MISMATCH
    )
    for field in ("producer_id", "target_id", "horizon_id"):
        expected = (
            getattr(s, field)
            if field == "producer_id"
            else (
                s.target.fingerprint if field == "target_id" else s.target.horizon.fingerprint
            )
        )
        reply = c.service.list_registry_entries(
            replace(query, page_size=100, **{field: expected})
        )
        assert isinstance(reply.value, RegistryPage) and reply.value.entries
    assert (
        c.service.get_registry_entry_for_artifact(query).status is ServiceStatus.INVALID_REQUEST
    )
    assert (
        c.service.get_registry_entry_for_artifact(
            replace(query, artifact_id=s.target.fingerprint)
        ).status
        is ServiceStatus.NOT_FOUND
    )
    assert (
        c.service.get_registry_entry(s.registry_entry_ids[0]).status is ServiceStatus.AVAILABLE
    )

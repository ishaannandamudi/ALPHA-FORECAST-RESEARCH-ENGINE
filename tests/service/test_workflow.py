"""Real native forecast values, immutable publication and deterministic public reads."""

from dataclasses import replace

import pytest

from afre.service import (
    ForecastSnapshot,
    RegistryPage,
    RegistryQuery,
    ServiceStatus,
    SnapshotPublication,
    SnapshotQuery,
    canonical_json,
    deserialize,
)
from tests.service.conftest import ServiceCase


@pytest.mark.parametrize(
    "family",
    [
        "point",
        "gaussian",
        "empirical",
        "calibrated",
        "event",
        "hard-regime",
        "mixture",
        "nonlinear",
        "sequence",
        "quantile",
    ],
)
def test_native_publication(service_case: ServiceCase, family: str) -> None:
    c = service_case
    identity = c.fixture.ids(family)[0]
    snapshot = c.publisher.publish(SnapshotPublication(identity, "initial", 120))
    assert c.publisher.publish(snapshot.publication) == snapshot
    reply = c.service.get_snapshot(snapshot.snapshot_id)
    assert reply.status is ServiceStatus.AVAILABLE and reply.value == snapshot
    assert deserialize(canonical_json(reply)) == reply
    assert snapshot.final_available_ns <= snapshot.origin.availability_cutoff_ns
    assert snapshot.publication.published_ns == 120
    assert snapshot.output.point is not None
    assert snapshot.output.artifact_id == identity
    assert snapshot.etag == snapshot.snapshot_id
    catalog = c.publisher.catalog("frozen", (snapshot.snapshot_id,), 120)
    query = SnapshotQuery(
        catalog.fingerprint,
        snapshot.producer_id,
        snapshot.target.fingerprint,
        snapshot.target.horizon.fingerprint,
        snapshot.origin,
        snapshot.universe_id,
        120,
    )
    assert c.service.get_snapshot_for_origin(query).value == snapshot
    page = c.service.list_registry_entries(RegistryQuery(catalog.fingerprint))
    assert isinstance(page.value, RegistryPage)
    assert set(snapshot.registry_entry_ids).issubset(e.fingerprint for e in page.value.entries)
    assert (
        c.service.get_registry_entry_for_artifact(
            RegistryQuery(catalog.fingerprint, artifact_id=identity)
        ).status
        is ServiceStatus.AVAILABLE
    )
    audit = c.publisher.audit(snapshot.snapshot_id)
    assert c.service.get_audit(audit.fingerprint).value == audit
    assert not audit.outcomes_read
    assert c.service.get_version_info().status is ServiceStatus.AVAILABLE
    assert (
        c.service.get_snapshot(snapshot.snapshot_id, ("TRADING",)).status
        is ServiceStatus.UNAVAILABLE
    )
    corrected = c.publisher.publish(
        replace(snapshot.publication, publication_version="corrected")
    )
    assert corrected.snapshot_id != snapshot.snapshot_id
    assert corrected.output == snapshot.output
    assert c.service.get_snapshot(snapshot.snapshot_id).value == snapshot


def test_missing_and_ambiguous_selector(service_case: ServiceCase) -> None:
    c = service_case
    s = c.publisher.publish(SnapshotPublication(c.fixture.ids("point")[0], "one", 120))
    second = c.publisher.publish(replace(s.publication, publication_version="two"))
    catalog = c.publisher.catalog("both", (s.fingerprint, second.fingerprint), 120)
    q = SnapshotQuery(
        catalog.fingerprint,
        s.producer_id,
        s.target.fingerprint,
        s.target.horizon.fingerprint,
        s.origin,
        s.universe_id,
        120,
    )
    assert c.service.get_snapshot_for_origin(q).status is ServiceStatus.INCOMPATIBLE
    assert (
        c.service.get_snapshot_for_origin(replace(q, as_of_ns=119)).status
        is ServiceStatus.NOT_FOUND
    )
    assert (
        c.service.get_snapshot_for_origin(replace(q, as_of_ns=121)).status
        is ServiceStatus.INCOMPATIBLE
    )
    assert (
        c.service.get_snapshot_for_origin(replace(q, api_version="2")).status
        is ServiceStatus.VERSION_MISMATCH
    )
    absent = "afre.svc_snapshot:1.0:" + "0" * 64
    assert c.service.get_snapshot(absent).status is ServiceStatus.NOT_FOUND
    assert (
        c.service.get_health_metadata(s.fingerprint, absent).status is ServiceStatus.UNAVAILABLE
    )
    assert (
        c.service.get_challenge_metadata(s.fingerprint, absent).status
        is ServiceStatus.UNAVAILABLE
    )
    assert isinstance(c.service.get_snapshot(s.fingerprint).value, ForecastSnapshot)

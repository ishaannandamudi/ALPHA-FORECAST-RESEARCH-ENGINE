"""Consumer uses supported public AFRE imports; setup is supplied by the test harness."""

from dataclasses import replace

import pytest

from afre.features import DataQuality
from afre.service import (
    ForecastSnapshot,
    MultiHorizonSnapshot,
    RegistryPage,
    RegistryQuery,
    ServiceContextKind,
    ServiceStatus,
    SnapshotPublication,
    SnapshotQuery,
    StableSecurityId,
    VersionInfo,
    canonical_json,
    deserialize,
)
from examples.downstream_client import (
    NeutralObservation,
    adapt_observation,
    compare_correction,
    consume,
)
from examples.feature_store_demo import SOURCE, definition
from tests.service.conftest import ServiceCase


def test_public_consumer_contract(service_case: ServiceCase) -> None:
    c = service_case
    versions = c.service.get_version_info()
    assert isinstance(versions.value, VersionInfo)
    assert versions.value.engine == "1.0.0" and versions.value.api == "1.0"
    assert versions == c.service.get_capability_catalog()
    assert all(value == "1.0" for _, value in versions.value.schemas)
    assert not {"EXECUTION", "PROMOTION", "TRAINING"}.intersection(versions.value.capabilities)
    snapshots = tuple(
        c.publisher.publish(SnapshotPublication(c.fixture.ids(family)[0], "client", 120))
        for family in ("point", "gaussian", "mixture", "calibrated")
    )
    for snapshot in snapshots:
        assert consume(c.service, snapshot.snapshot_id) == snapshot
        assert deserialize(canonical_json(snapshot)) == snapshot
    assert snapshots[0].output.probability is None
    assert snapshots[2].output.probability is not None
    assert snapshots[2].output.probability.kind == "MIXTURE"
    assert snapshots[3].output.calibration.state == "CALIBRATED"
    original = snapshots[0]
    corrected = c.publisher.publish(
        replace(original.publication, publication_version="corrected")
    )
    assert compare_correction(c.service, original.snapshot_id, corrected.snapshot_id) == (
        original,
        corrected,
    )
    catalog = c.publisher.catalog("client", tuple(s.snapshot_id for s in snapshots), 120)
    query = RegistryQuery(catalog.fingerprint, page_size=1)
    seen: list[str] = []
    cursor = None
    while True:
        page = c.service.list_registry_entries(query, cursor)
        assert isinstance(page.value, RegistryPage)
        seen.extend(e.fingerprint for e in page.value.entries)
        cursor = page.value.next_cursor
        if cursor is None:
            break
    assert tuple(seen) == catalog.entry_ids
    for identity, requests in c.fixture.context_cases:
        snapshot = c.publisher.publish(
            SnapshotPublication(identity, "client-context", 120, requests)
        )
        assert consume(c.service, snapshot.snapshot_id) == snapshot
        for context in snapshot.contexts:
            if context.kind is ServiceContextKind.CHALLENGE:
                assert context.action == "MANUAL_ONLY"
            if context.kind is ServiceContextKind.HEALTH:
                assert context.action == "NONE_DESCRIPTIVE_ONLY"
    horizons = tuple(
        c.publisher.publish(SnapshotPublication(i, "client-horizon", 10**16))
        for _, i in c.fixture.horizons
    )
    hc = c.publisher.catalog("client-horizons", tuple(s.snapshot_id for s in horizons), 10**16)
    queries = tuple(
        SnapshotQuery(
            hc.fingerprint,
            s.producer_id,
            s.target.fingerprint,
            s.target.horizon.fingerprint,
            s.origin,
            s.universe_id,
            10**16,
        )
        for s in horizons
    )
    bundle = c.service.get_multi_horizon_snapshot(queries)
    assert isinstance(bundle.value, MultiHorizonSnapshot)
    assert {s.target.horizon.duration_ns for s in bundle.value.snapshots} == {
        3600000000000,
        86400000000000,
    }
    assert all(isinstance(s, ForecastSnapshot) for s in bundle.value.snapshots)
    assert c.service.get_snapshot("invalid").status is ServiceStatus.INVALID_REQUEST
    with pytest.raises(ValueError, match="unavailable"):
        consume(c.service, "afre.svc_snapshot:1.0:" + "0" * 64)


def test_provider_neutral_six_clocks() -> None:
    at = 1760004000000000000  # Explicit UTC epoch ns; synthetic 10:00 example.
    security = StableSecurityId("issuer-neutral-security", "0001")
    feature = definition("market.client", unit="currency")
    observed = NeutralObservation(
        security,
        at,
        100.0,
        "currency",
        DataQuality.VERIFIED,
        at,
        at,
        at + 120000000000,
        at + 121000000000,
        at + 122000000000,
        at + 122000000000,
    )
    vintage = adapt_observation(observed, feature, SOURCE)
    assert vintage.entity == security.instrument
    assert vintage.clocks.final_available_ns > at + 60000000000
    assert vintage.clocks.upstream_publication_ns == at
    assert vintage.clocks.afre_received_ns == at + 120000000000
    with pytest.raises(ValueError):
        adapt_observation(replace(observed, final_available_utc_ns=at), feature, SOURCE)
    with pytest.raises(ValueError, match="unit"):
        adapt_observation(replace(observed, unit="ratio"), feature, SOURCE)
    with pytest.raises(ValueError):
        adapt_observation(replace(observed, ingested_utc_ns=at), feature, SOURCE)

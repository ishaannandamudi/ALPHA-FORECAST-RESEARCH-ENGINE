"""Public request typing, exact capability semantics and scoped replay reuse."""

from dataclasses import replace
from typing import Any, cast

import pytest

from afre.probabilistic.artifacts import ProbabilisticForecast
from afre.schema import ContractError
from afre.service import (
    RegistryQuery,
    ServiceStatus,
    SnapshotPublication,
    SnapshotQuery,
    canonical_json,
)
from afre.service.lineage import lineage_for
from afre.service.native import native_source
from afre.service.registry import registration_for
from tests.service.conftest import ServiceCase


def test_invalid_requests_and_response_versions(service_case: ServiceCase) -> None:
    c = service_case
    for identity in (cast(Any, None), "bad", "afre.target_definition:1.0:" + "0" * 64):
        reply = c.service.get_snapshot(identity)
        assert reply.status is ServiceStatus.INVALID_REQUEST
        assert (reply.engine_version, reply.store_version, reply.sqlite_user_version) == (
            "1.0.0",
            "1.24",
            25,
        )
        assert reply.api_version == reply.snapshot_schema == reply.registry_schema == "1.0"
    assert (
        c.service.get_registry_entry_for_artifact(cast(Any, None)).status
        is ServiceStatus.INVALID_REQUEST
    )
    assert c.service.get_health_metadata("bad", "bad").status is ServiceStatus.INVALID_REQUEST
    s = c.publisher.publish(SnapshotPublication(c.fixture.ids("point")[0], "one", 120))
    assert (
        c.service.get_snapshot(s.fingerprint, cast(Any, None)).status
        is ServiceStatus.INVALID_REQUEST
    )
    assert (
        c.service.get_snapshot(s.fingerprint, ("CALIBRATION",)).status
        is ServiceStatus.UNAVAILABLE
    )
    catalog = c.publisher.catalog("request", (s.fingerprint,), 120)
    query = RegistryQuery(
        catalog.fingerprint, artifact_id=s.publication.source_id, api_version="2"
    )
    assert (
        c.service.get_registry_entry_for_artifact(query).status
        is ServiceStatus.VERSION_MISMATCH
    )
    origin = SnapshotQuery(
        catalog.fingerprint,
        s.producer_id,
        s.target.fingerprint,
        s.target.horizon.fingerprint,
        s.origin,
        s.universe_id,
        120,
        api_version="2",
    )
    assert (
        c.service.get_multi_horizon_snapshot((origin,)).status is ServiceStatus.VERSION_MISMATCH
    )


def test_scoped_reuse_and_unrelated_registration(service_case: ServiceCase) -> None:
    c = service_case
    root = c.fixture.ids("gaussian")[0]
    outside = native_source(c.repo, root)
    assert not c.repo._service_sources
    with c.repo.request():
        source = native_source(c.repo, root)
        assert source == outside and native_source(c.repo, root) is source
        graph = lineage_for(c.repo, root, (source.producer_id,))
        assert lineage_for(c.repo, root, (source.producer_id,)) is graph
        with c.repo.request():
            assert native_source(c.repo, root) is source
        assert c.repo._service_sources
        candidates = tuple(i for i in c.fixture.ids("nonlinear") if i not in graph.node_ids)
        assert candidates
        with pytest.raises(ContractError, match="contributing"):
            registration_for(
                c.repo,
                candidates[0],
                source.producer_id,
                source.target.fingerprint,
                source.target.horizon.fingerprint,
                root,
            )
        with pytest.raises(ContractError, match="category"):
            registration_for(
                c.repo,
                source.target.fingerprint,
                source.producer_id,
                source.target.fingerprint,
                source.target.horizon.fingerprint,
                root,
            )
    assert not c.repo._service_sources and not c.repo._service_graphs
    assert lineage_for(c.repo, root, (source.producer_id,)) == graph


def test_ambiguous_artifact_and_frozen_pages(service_case: ServiceCase) -> None:
    c = service_case
    gaussian_id = c.fixture.ids("gaussian")[0]
    point_id = c.repo.get(ProbabilisticForecast, gaussian_id).point_forecast_id
    point = c.publisher.publish(SnapshotPublication(point_id, "point", 120))
    gaussian = c.publisher.publish(SnapshotPublication(gaussian_id, "gaussian", 120))
    catalog = c.publisher.catalog("two", (point.fingerprint, gaussian.fingerprint), 120)
    query = RegistryQuery(catalog.fingerprint, artifact_id=point_id)
    assert c.service.get_registry_entry_for_artifact(query).status is ServiceStatus.INCOMPATIBLE
    assert (
        c.service.get_registry_entry_for_artifact(
            replace(query, producer_id=point.producer_id)
        ).status
        is ServiceStatus.AVAILABLE
    )
    before = canonical_json(c.service.list_registry_entries(RegistryQuery(catalog.fingerprint)))
    with c.repo.request():
        assert c.repo.get_any(point.fingerprint) == point
    assert (
        canonical_json(c.service.list_registry_entries(RegistryQuery(catalog.fingerprint)))
        == before
    )

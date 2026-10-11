"""Truth guards before cache, late sources, bounds and safe public error envelopes."""

import sqlite3
from collections.abc import Callable
from dataclasses import replace
from typing import Any, cast
from unittest.mock import patch

import pytest

from afre.schema import ContractError
from afre.service import (
    ServiceBounds,
    ServiceStatus,
    SnapshotPublication,
    SnapshotQuery,
    canonical_json,
    deserialize,
)
from afre.service.context_builder import project
from afre.service.facade import Payload
from afre.service.registry_entries import RegistryEntry
from afre.statistical_models.artifacts import PointForecast
from afre.target_engine.market_data import TargetBar
from afre.target_engine.models import TargetVintage
from tests.service.conftest import ServiceCase


def test_truth_and_outcomes_before_cache(service_case: ServiceCase) -> None:
    c = service_case
    target_id = c.repo._connection.execute(
        "SELECT fingerprint FROM target_artifacts WHERE type_name='TargetVintage' LIMIT 1"
    ).fetchone()[0]
    target = c.repo.get(TargetVintage, target_id)
    with c.repo.request():
        assert c.repo._validation_cache is not None
        c.repo._validation_cache[target_id] = target
        reads: tuple[Callable[[], object], ...] = (
            lambda: c.repo.get(TargetVintage, target_id),
            lambda: c.repo.resolve(TargetVintage, target_id),
            lambda: c.repo.get_any(target_id),
        )
        for read in reads:
            with pytest.raises(ContractError, match="before cache"):
                read()
        bar_id = c.repo._connection.execute(
            "SELECT fingerprint FROM target_artifacts WHERE type_name='TargetBar' LIMIT 1"
        ).fetchone()[0]
        with pytest.raises(ContractError, match="later outcomes"):
            c.repo.get(TargetBar, bar_id)
    assert c.repo._service_request_depth == 0 and c.repo._feature_only_depth == 0


@pytest.mark.parametrize(
    "field",
    [
        "contexts",
        "atoms",
        "components",
        "lineage_nodes",
        "lineage_depth",
        "lineage_bytes",
        "payload_bytes",
        "registry_entries",
        "page_size",
        "snapshot_bytes",
        "artifacts",
    ],
)
def test_configured_bounds(service_case: ServiceCase, field: str) -> None:
    c = service_case
    source, requests = c.fixture.context_cases[0]
    if field == "atoms":
        source, requests = c.fixture.ids("empirical")[0], ()
    elif field == "components":
        source, requests = c.fixture.context_cases[3]
    s = c.publisher.publish(SnapshotPublication(source, "base", 120, requests))
    catalog = c.publisher.catalog("bounds", (s.fingerprint,), 120)
    c.repo.service_bounds = replace(ServiceBounds(), **{field: 1})
    if field in ("registry_entries", "page_size"):
        from afre.service import RegistryQuery

        result = c.service.list_registry_entries(RegistryQuery(catalog.fingerprint))
    elif field == "artifacts":
        with pytest.raises(ContractError, match="bound"):
            c.publisher.publish(replace(s.publication, publication_version="another"))
        return
    else:
        result = c.service.get_snapshot(s.fingerprint)
    assert result.status in (ServiceStatus.BOUNDS_EXCEEDED, ServiceStatus.CORRUPT_ARTIFACT)


def test_public_failure_sanitization(service_case: ServiceCase) -> None:
    c = service_case
    for status in ServiceStatus:
        if status is ServiceStatus.AVAILABLE:
            continue

        def fail(status: ServiceStatus = status) -> Payload:
            raise ContractError(status.value + ": secret internal table/path detail")

        result = c.service._reply(fail)
        assert result.status is status and result.value is None
        assert "secret" not in canonical_json(result)
    for error in (
        sqlite3.DatabaseError("private.db"),
        AttributeError("internal"),
        TypeError("internal"),
    ):
        with patch.object(c.repo, "_validate_layout", side_effect=error):
            result = c.service.get_version_info()
            assert result.status is ServiceStatus.CORRUPT_ARTIFACT
            assert "internal" not in canonical_json(result)
    result = c.service.get_snapshot_for_origin(cast(Any, None))
    assert result.status is ServiceStatus.INVALID_REQUEST
    assert c.service.get_capability_catalog().status is ServiceStatus.AVAILABLE
    assert deserialize(canonical_json(result)) == result
    with pytest.raises(ContractError, match="root"):
        from afre.ids import InstrumentId
        from afre.serialization import canonical_json as native_json

        deserialize(native_json(InstrumentId("neutral", "instrument")))


def test_late_and_registry_forgery(service_case: ServiceCase) -> None:
    c = service_case
    source = c.fixture.ids("point")[0]
    point = c.repo.get(PointForecast, source)
    at = point.available_ns
    late = replace(point, computed_ns=at + 1, available_ns=at + 1)
    with c.repo.transaction():
        c.repo.put(late)
    with pytest.raises(ContractError, match="origin|causal|late"):
        c.publisher.publish(SnapshotPublication(late.fingerprint, "late", 120))
    s = c.publisher.publish(SnapshotPublication(source, "valid", 120))
    entry = c.repo.get(RegistryEntry, s.registry_entry_ids[0])
    forged = replace(entry, producer_id=s.target.fingerprint)
    with pytest.raises(ContractError, match="producer"), c.repo.transaction():
        c.repo.put(forged)
    q = SnapshotQuery(
        "afre.svc_catalog:1.0:" + "a" * 64,
        s.producer_id,
        s.target.fingerprint,
        s.target.horizon.fingerprint,
        s.origin,
        s.universe_id,
        120,
    )
    assert c.service.get_snapshot_for_origin(q).status is ServiceStatus.NOT_FOUND


def test_bounds_and_projection_contracts() -> None:
    for value in (0, -1, 101):
        with pytest.raises(ContractError):
            ServiceBounds(page_size=value)
    with pytest.raises(ContractError, match="scalar"):
        project({"untrusted": "not executable"})
    with pytest.raises(ContractError, match="bound"):
        project((1, 2), maximum=1)
    with pytest.raises(ContractError):
        ServiceBounds(payload_bytes=True)

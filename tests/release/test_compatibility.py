"""Exact previous-release bytes and native semantic replay across engine upgrades."""

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from afre.schema import ContractError
from afre.service import (
    AFREService,
    ForecastSnapshot,
    ServiceRepository,
    SnapshotAudit,
    SnapshotPublication,
    VersionInfo,
    canonical_json,
    deserialize,
)
from afre.service.audit import audit_for
from afre.service.registry import registration_for
from afre.service.versions import version_info
from tests.service.conftest import ServiceCase


@pytest.mark.parametrize("name", ["snapshot", "audit", "versions", "reply"])
def test_committed_025_bytes(name: str) -> None:
    payload = (Path(__file__).parent / "fixtures" / (name + "-0.25.0.json")).read_text().strip()
    assert canonical_json(deserialize(payload)) == payload


def test_native_old_snapshot_replay(service_case: ServiceCase, tmp_path: Path) -> None:
    c = service_case
    current = c.publisher.publish(
        SnapshotPublication(c.fixture.ids("point")[0], "upgrade", 120)
    )
    historical = replace(current, engine_version="0.25.0")
    with c.repo.transaction(), c.repo.request():
        c.repo.put(historical)
        entry = registration_for(
            c.repo,
            historical.fingerprint,
            historical.producer_id,
            historical.target.fingerprint,
            historical.target.horizon.fingerprint,
            historical.publication.source_id,
        )
        c.repo.put(entry)
        audit = audit_for(historical, entry)
        c.repo.put(audit)
    assert current.engine_version == "1.0.0" and historical.fingerprint != current.fingerprint
    frozen = canonical_json(historical)
    frozen_audit = canonical_json(audit)
    assert c.service.get_snapshot(historical.fingerprint).value == historical
    assert c.service.get_audit(audit.fingerprint).value == audit
    assert c.publisher.audit(historical.fingerprint) == audit
    assert c.publisher.publish(current.publication) == current
    copy_path = tmp_path / "upgraded.sqlite"
    with ServiceRepository(copy_path) as copy:
        c.repo._connection.backup(copy._connection)
    with ServiceRepository(copy_path) as copy:
        provider = AFREService(copy)
        saved_snapshot = provider.get_snapshot(historical.fingerprint).value
        saved_audit = provider.get_audit(audit.fingerprint).value
        assert isinstance(saved_snapshot, ForecastSnapshot) and isinstance(
            saved_audit, SnapshotAudit
        )
        assert canonical_json(saved_snapshot) == frozen
        assert canonical_json(saved_audit) == frozen_audit
        assert isinstance(provider.get_version_info().value, VersionInfo)
    assert audit.versions.engine == "0.25.0"


@pytest.mark.parametrize("engine", ["0.24.0", "0.26.0", "1.0.1", "2.0.0", ""])
def test_unknown_engine_rejected(engine: str) -> None:
    with pytest.raises(ContractError, match="unsupported|empty text"):
        version_info(engine)


@pytest.mark.parametrize(
    "change",
    [
        {"api": "2.0"},
        {"store": "1.25"},
        {"sqlite_user_version": 26},
        {"capabilities": ("EXECUTION",)},
        {"schemas": ()},
        {"runtime_dependencies": ("provider-sdk",)},
        {"python_minimum": "3.10"},
    ],
)
def test_historical_catalog_stays_closed(change: dict[str, Any]) -> None:
    # Dataclass replacement is deliberately adversarial; exact catalog validation is required.
    with pytest.raises(ContractError, match="catalog"):
        replace(version_info("0.25.0"), **change)


def test_audit_cannot_relabel_engine() -> None:
    payload = (Path(__file__).parent / "fixtures/audit-0.25.0.json").read_text().strip()
    audit = deserialize(payload)
    assert isinstance(audit, SnapshotAudit) and isinstance(audit.snapshot, ForecastSnapshot)
    with pytest.raises(ContractError, match="corruption"):
        replace(audit, versions=version_info())

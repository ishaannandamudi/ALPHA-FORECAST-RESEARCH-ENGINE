"""Additive migration, immutable projections and semantic replay reject corrupt evidence."""

import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from afre.fusion import FusionRepository
from afre.fusion.schema import FusionBounds
from afre.health import (
    HealthBounds,
    HealthDiagnostic,
    HealthMetric,
    HealthRepository,
    HealthRule,
)
from afre.health.lineage import HealthAudit
from afre.health.storage import health_schema
from afre.schema import Artifact, ContractError
from examples.health_fixture import health_spec
from tests.health.conftest import HealthCase


def test_migration_preserves_ddl_metadata_rows(tmp_path: Path) -> None:
    path = tmp_path / "prior.sqlite"
    with FusionRepository(path) as r:
        with r.transaction():
            r.put(FusionBounds())
        ddl = dict(
            r._connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        )
        metadata = dict(r._connection.execute("SELECT * FROM metadata"))
        rows = tuple(r._connection.execute("SELECT * FROM fus_artifacts"))
    with HealthRepository(path) as r:
        current = dict(
            r._connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        )
        assert all(current[n] == s for n, s in ddl.items())
        assert dict(r._connection.execute("SELECT * FROM metadata")).items() >= metadata.items()
        assert tuple(r._connection.execute("SELECT * FROM fus_artifacts")) == rows
        assert r._connection.execute("PRAGMA user_version").fetchone()[0] == 23


def test_migration_rollback_future(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import afre.health.repository as module

    path = tmp_path / "rollback.sqlite"
    with FusionRepository(path):
        pass
    monkeypatch.setattr(module, "health_schema", lambda: (*health_schema(), "INVALID SQL"))
    with pytest.raises(sqlite3.OperationalError):
        HealthRepository(path)
    with FusionRepository(path) as r:
        assert r._connection.execute("PRAGMA user_version").fetchone()[0] == 22
        assert not r._connection.execute(
            "SELECT name FROM sqlite_master WHERE name LIKE 'hlt_%'"
        ).fetchall()
        r._connection.execute("PRAGMA user_version=24")
    with pytest.raises(ContractError, match="future"):
        HealthRepository(path)


def prepared(c: HealthCase) -> tuple[Artifact, ...]:
    s, rules = health_spec(c.repo, c.fixture, (HealthDiagnostic.PREDICTION_MEAN,))
    c.engine.declare(s, rules)
    result = c.engine.evaluate(s.fingerprint, 120)
    metric = c.repo.resolve(HealthMetric, result.metric_ids[0])
    audit = c.engine.audit(result.fingerprint)
    return s, rules[0], metric, result, audit


@pytest.mark.parametrize("index", range(5))
def test_corrupted_payload(health_case: HealthCase, index: int) -> None:
    c = health_case
    value = prepared(c)[index]
    row = c.repo._connection.execute(
        "SELECT payload FROM hlt_artifacts WHERE fingerprint=?", (value.fingerprint,)
    ).fetchone()
    wire = json.loads(row[0])
    wire["artifact"]["fields"][next(iter(wire["artifact"]["fields"]))] = "tampered"
    c.repo._connection.execute("DROP TRIGGER immutable_hlt_artifacts_update")
    c.repo._connection.execute(
        "UPDATE hlt_artifacts SET payload=? WHERE fingerprint=?",
        (json.dumps(wire), value.fingerprint),
    )
    with pytest.raises(ContractError):
        c.repo.get_any(value.fingerprint)


@pytest.mark.parametrize("index", (0, 2, 3, 4))
def test_valid_hash_semantic_forgery(health_case: HealthCase, index: int) -> None:
    from afre.health import HealthSpec, ModelHealthSnapshot

    c = health_case
    value = prepared(c)[index]
    forged: Artifact
    if isinstance(value, HealthSpec):
        forged = replace(value, target_id=c.fixture.reference.horizon_id)
    elif isinstance(value, HealthMetric):
        forged = replace(value, current_value=99.0)
    elif isinstance(value, ModelHealthSnapshot):
        forged = replace(value, reason="invented-health-probability")
    else:
        assert isinstance(value, HealthAudit)
        forged = replace(value, serialized_bytes=value.serialized_bytes + 1)
    with c.repo.transaction(), pytest.raises(ContractError):
        c.repo.put(forged)


@pytest.mark.parametrize("table", ("hlt_artifacts", "hlt_records", "hlt_links"))
@pytest.mark.parametrize("operation", ("UPDATE", "DELETE"))
def test_sql_immutable(health_case: HealthCase, table: str, operation: str) -> None:
    prepared(health_case)
    query = (
        f"UPDATE {table} SET fingerprint=fingerprint"
        if operation == "UPDATE"
        else f"DELETE FROM {table}"
    )
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        health_case.repo._connection.execute(query)


@pytest.mark.parametrize(
    "bound",
    (
        "features",
        "metrics",
        "samples",
        "payload_bytes",
        "lineage_nodes",
        "lineage_bytes",
        "lineage_depth",
        "snapshot_bytes",
    ),
)
def test_configured_bounds(health_case: HealthCase, bound: str) -> None:
    c = health_case
    values = prepared(c)
    c.repo.health_bounds = replace(HealthBounds(), **{bound: 1})
    with pytest.raises(ContractError, match="bound"):
        if bound.startswith("lineage"):
            c.engine.audit(values[3].fingerprint)
        elif bound == "snapshot_bytes":
            with c.repo.read_snapshot():
                pass
        elif bound == "metrics":
            s, r = health_spec(
                c.repo,
                c.fixture,
                (HealthDiagnostic.PREDICTION_STD, HealthDiagnostic.PREDICTION_MEAN),
            )
            c.engine.declare(s, r)
        elif bound == "samples":
            c.repo.get_any(values[0].fingerprint)
        else:
            c.repo.get_any(c.fixture.observation_ids[0])


def test_no_default_threshold_and_rule_revision(health_case: HealthCase) -> None:
    c = health_case
    s, rules = health_spec(c.repo, c.fixture, (HealthDiagnostic.PREDICTION_MEAN,))
    original = prepared(c)[3]
    changed = replace(rules[0], warning=3.0, degraded=4.0)
    new = replace(s, rule_bindings=((s.requests[0].fingerprint, changed.fingerprint),))
    c.engine.declare(new, (changed,))
    result = c.engine.evaluate(new.fingerprint, 120)
    assert original.fingerprint != result.fingerprint
    assert c.repo.get_any(original.fingerprint) == original
    with pytest.raises(TypeError):
        HealthRule(label="missing", kind=HealthDiagnostic.PREDICTION_MEAN)  # type: ignore[call-arg]

"""Transactional migration, immutable data, replay forgery and relational integrity."""

import shutil
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from afre.invariance import (
    EnvironmentMembership,
    EnvironmentState,
    InvarianceRepository,
    StabilityMetricName,
)
from afre.invariance import repository as repository_module
from afre.invariance.lineage import invariance_edges
from afre.invariance.storage import invariance_index, invariance_schema
from afre.orthogonalization import OrthogonalizationRepository, SignalObservation
from afre.research_datasets.schema import Partition
from afre.schema import Artifact, ContractError
from afre.serialization import canonical_json
from tests.invariance.conftest import Base, Case
from tests.statistical_models.test_repository import database_snapshot


@pytest.mark.parametrize("kind", ("membership", "metric"))
def test_valid_hash_stored_forgery_replays_on_read(case: Case, kind: str) -> None:
    if kind == "membership":
        original = case.repo.get(EnvironmentMembership, case.fixture.membership_ids[0])
        included = original.weight == 0.0
        forged: Artifact = replace(
            original,
            weight=float(included),
            state=EnvironmentState.INCLUDED if included else EnvironmentState.EXCLUDED,
        )
    else:
        metric = next(
            m
            for m in case.engine.evaluate(
                case.fixture.spec.fingerprint, case.fixture.membership_ids, 100, 100
            )
            if m.name is StabilityMetricName.MAE
        )
        assert metric.value is not None
        forged = replace(metric, value=metric.value + 1.0)
    # Bypass publication to simulate a consistent on-disk semantic forgery.
    c = case.repo._connection
    c.execute(
        "INSERT INTO inv_artifacts VALUES (?,?,?,?)",
        (forged.fingerprint, type(forged).__name__, "1.0", canonical_json(forged)),
    )
    c.execute(
        "INSERT INTO inv_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        invariance_index(forged),
    )
    c.executemany(
        "INSERT INTO inv_links VALUES (?,?)",
        tuple((forged.fingerprint, i) for i in sorted(set(invariance_edges(forged)))),
    )
    assert case.repo.get(type(forged), forged.fingerprint) == forged
    with pytest.raises(ContractError, match="semantic replay"):
        case.repo.get_any(forged.fingerprint)
    if isinstance(forged, EnvironmentMembership):
        with pytest.raises(ContractError, match="semantic replay"):
            case.engine.metadata(forged.fingerprint, forged.origin)


def legacy_copy(base: Base, path: Path) -> None:
    shutil.copyfile(base.path, path)
    with sqlite3.connect(path) as c:
        for (name,) in c.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' "
            "AND name LIKE 'immutable_inv_%'"
        ).fetchall():
            c.execute(f"DROP TRIGGER {name}")
        for table in ("inv_artifacts", "inv_records", "inv_links"):
            c.execute(f"DROP TABLE {table}")
        trigger = c.execute(
            "SELECT sql FROM sqlite_master WHERE name='immutable_metadata_delete'"
        ).fetchone()[0]
        c.execute("DROP TRIGGER immutable_metadata_delete")
        c.execute("DELETE FROM metadata WHERE key LIKE 'invariance_%'")
        c.execute(trigger)
        c.execute("PRAGMA user_version=17")


def test_migration_preserves_every_prior_row_and_DDL(base: Base, tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite"
    legacy_copy(base, path)
    before = database_snapshot(path)
    with OrthogonalizationRepository(path) as r:
        ddl = dict(
            r._connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        )
    with InvarianceRepository(path) as r:
        assert r._connection.execute("PRAGMA user_version").fetchone()[0] == 18
        after_ddl = dict(
            r._connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        )
    after = database_snapshot(path)
    assert all(after[k] == v for k, v in before.items() if k != "metadata")
    assert all(after_ddl[k] == v for k, v in ddl.items())
    assert set(before["metadata"]) <= set(after["metadata"])
    with pytest.raises(ContractError):
        OrthogonalizationRepository(path)


def test_migration_rollback_and_future_rejection(
    base: Base, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "rollback.sqlite"
    legacy_copy(base, path)
    before = database_snapshot(path)
    monkeypatch.setattr(
        repository_module,
        "invariance_schema",
        lambda: (*invariance_schema()[:2], "invalid SQL"),
    )
    with pytest.raises(sqlite3.OperationalError):
        InvarianceRepository(path)
    assert database_snapshot(path) == before
    with sqlite3.connect(path) as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == 17
        c.execute("PRAGMA user_version=19")
    with pytest.raises(ContractError, match="future"):
        InvarianceRepository(path)


@pytest.mark.parametrize("table", ("inv_artifacts", "inv_records", "inv_links"))
@pytest.mark.parametrize("verb", ("UPDATE", "DELETE"))
def test_immutability(case: Case, table: str, verb: str) -> None:
    statement = (
        f"UPDATE {table} SET fingerprint=fingerprint"
        if verb == "UPDATE"
        else f"DELETE FROM {table}"
    )
    with pytest.raises(sqlite3.IntegrityError):
        case.repo._connection.execute(statement)


@pytest.mark.parametrize(
    "kind",
    ("membership", "metric", "comparison", "shift", "audit", "model", "trend", "definition"),
)
def test_semantic_forgery_rejected(case: Case, kind: str) -> None:
    f = case.fixture
    ms = case.engine.evaluate(f.spec.fingerprint, f.membership_ids, 100, 100)
    mae = tuple(m for m in ms if m.name is StabilityMetricName.MAE)
    value: Artifact
    if kind == "membership":
        m = next(
            case.repo.get(EnvironmentMembership, i)
            for i in f.membership_ids
            if case.repo.get(EnvironmentMembership, i).weight == 1
        )
        value = replace(m, reason="forged-source-reason")
    elif kind == "metric":
        value = replace(mae[0], value=99.0)
    elif kind == "comparison":
        c = case.engine.compare(mae[0].fingerprint, mae[1].fingerprint, 100)
        value = replace(c, delta=99.0)
    elif kind == "shift":
        ref = f.upstream.spec.candidate.fingerprint
        ids = tuple(
            i
            for row in f.upstream.partition(Partition.VALIDATION)
            for i in row.observation_ids
            if case.repo.get(SignalObservation, i).reference_id == ref
        )
        shift = case.engine.shift(
            f.spec.fingerprint,
            ref,
            (
                f.environment_set.definitions[0].fingerprint,
                f.environment_set.definitions[1].fingerprint,
            ),
            f.membership_ids,
            ids,
            100,
            100,
        )
        value = replace(shift, mean_shift=99.0)
    elif kind == "audit":
        value = replace(case.engine.audit(mae[0].fingerprint), declarations=("forged proof",))
    elif kind == "model":
        model = f.upstream.upstream.covariances[0].model_id
        diagnostic = case.engine.models(
            f.spec.fingerprint,
            tuple((d.fingerprint, model) for d in f.environment_set.definitions),
            100,
            100,
        )
        value = replace(diagnostic, summaries=())
    elif kind == "trend":
        value = replace(
            case.engine.trend(tuple(m.fingerprint for m in mae), 100), slope_per_nanosecond=99.0
        )
    else:
        d = f.environment_set.definitions[0]
        value = replace(d, target=replace(d.target, name="target.forged_target"))
    with pytest.raises((ContractError, KeyError)), case.repo.transaction():
        case.repo.put(value)


@pytest.mark.parametrize(
    "kind", ("payload", "family", "schema", "record", "link", "DDL", "metadata")
)
def test_tampering_fail_closed(case: Case, kind: str) -> None:
    fp = case.fixture.spec.fingerprint
    c = case.repo._connection
    if kind in ("payload", "family", "schema"):
        c.execute("DROP TRIGGER immutable_inv_artifacts_update")
        column, value = (
            ("payload", "{}")
            if kind == "payload"
            else ("type_name", "Unknown")
            if kind == "family"
            else ("schema_version", "9.0")
        )
        c.execute(f"UPDATE inv_artifacts SET {column}=? WHERE fingerprint=?", (value, fp))
        with pytest.raises(ContractError):
            case.repo.get_any(fp)
    elif kind == "record":
        c.execute("DROP TRIGGER immutable_inv_records_update")
        c.execute("UPDATE inv_records SET target_id='tampered' WHERE fingerprint=?", (fp,))
        with pytest.raises(ContractError, match="index"):
            case.repo.get_any(fp)
    elif kind == "link":
        c.execute("DROP TRIGGER immutable_inv_links_delete")
        c.execute("DELETE FROM inv_links WHERE fingerprint=?", (fp,))
        with pytest.raises(ContractError, match="index"):
            case.repo.get_any(fp)
    elif kind == "DDL":
        c.execute("DROP INDEX inv_environment_idx")
        with pytest.raises(ContractError, match="corruption"):
            case.repo._validate_layout()
    else:
        c.execute("DROP TRIGGER immutable_metadata_update")
        c.execute("UPDATE metadata SET value='tampered' WHERE key='invariance_schema'")
        with pytest.raises(ContractError, match="corruption"):
            case.repo._validate_layout()


def test_idempotence_restart_and_audit(case: Case) -> None:
    f = case.fixture
    metrics = case.engine.evaluate(f.spec.fingerprint, f.membership_ids, 100, 100)
    before = tuple(canonical_json(v) for v in metrics)
    count = case.repo._connection.execute("SELECT count(*) FROM inv_artifacts").fetchone()[0]
    case.engine._publish(metrics)
    assert (
        case.repo._connection.execute("SELECT count(*) FROM inv_artifacts").fetchone()[0]
        == count
    )
    path = case.repo._connection.execute("PRAGMA database_list").fetchone()[2]
    with InvarianceRepository(path) as reopened:
        assert before == tuple(canonical_json(reopened.get_any(m.fingerprint)) for m in metrics)
        assert reopened.audit() > count
    audit = case.engine.audit(metrics[0].fingerprint)
    assert f.spec.fingerprint in audit.node_ids and f.spec.fold_id in audit.node_ids
    assert f.environment_set.fingerprint in audit.node_ids

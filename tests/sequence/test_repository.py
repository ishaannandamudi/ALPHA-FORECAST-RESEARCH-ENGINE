"""Additive migration, immutable registry and semantic/relational corruption."""

import shutil
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from afre.nonlinear import NonlinearRepository
from afre.schema import Artifact, ContractError
from afre.sequence import (
    SequenceForecast,
    SequenceRepository,
    SequenceSnapshot,
    SequenceTransformArtifact,
)
from afre.sequence import repository as repository_module
from afre.sequence.storage import sequence_schema
from afre.serialization import canonical_json
from tests.sequence.conftest import Base, Case
from tests.statistical_models.test_repository import database_snapshot


def legacy_copy(base: Base, path: Path) -> None:
    shutil.copyfile(base.path, path)
    # Remove only additive AFRE-14 objects to recover the exact already-built AFRE-13 layout.
    with sqlite3.connect(path) as c:
        triggers = c.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='trigger'"
        ).fetchall()
        for name, _ in triggers:
            c.execute(f"DROP TRIGGER {name}")
        for (name,) in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'sq_%'"
        ).fetchall():
            c.execute(f"DROP TABLE {name}")
        c.execute("DELETE FROM metadata WHERE key LIKE 'sequence_%'")
        for name, sql in triggers:
            if "sq_" not in name:
                c.execute(sql)
        c.execute("PRAGMA user_version=14")


def test_migration_preserves_prior_layout(base: Base, tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite"
    legacy_copy(base, path)
    before = database_snapshot(path)
    with NonlinearRepository(path) as old:
        ddl = dict(
            old._connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        )
    with SequenceRepository(path) as repo:
        assert repo._connection.execute("PRAGMA user_version").fetchone()[0] == 15
        assert repo.audit() > 0
        afterddl = dict(
            repo._connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        )
    after = database_snapshot(path)
    assert all(after[t] == rows for t, rows in before.items() if t != "metadata")
    assert all(afterddl[k] == v for k, v in ddl.items())
    with pytest.raises(ContractError, match="future"):
        NonlinearRepository(path)


def test_rollback_and_future(
    base: Base, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "rollback.sqlite"
    legacy_copy(base, path)
    before = database_snapshot(path)
    monkeypatch.setattr(
        repository_module,
        "sequence_schema",
        lambda: (*sequence_schema()[:2], "invalid migration SQL"),
    )
    with pytest.raises(sqlite3.OperationalError):
        SequenceRepository(path)
    assert database_snapshot(path) == before
    with sqlite3.connect(path) as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == 14
        c.execute("PRAGMA user_version=16")
    with pytest.raises(ContractError, match="future"):
        SequenceRepository(path)


@pytest.mark.parametrize("table", ["sq_artifacts", "sq_records", "sq_links"])
@pytest.mark.parametrize("verb", ["UPDATE", "DELETE"])
def test_immutable(case: Case, table: str, verb: str) -> None:
    statement = (
        f"UPDATE {table} SET fingerprint=fingerprint"
        if verb == "UPDATE"
        else f"DELETE FROM {table}"
    )
    with pytest.raises(sqlite3.IntegrityError):
        case.repo._connection.execute(statement)


@pytest.mark.parametrize(
    "kind",
    [
        "snapshot",
        "mask",
        "order",
        "transform",
        "model",
        "forecast",
        "evaluation",
        "observation",
        "contribution",
    ],
)
def test_semantic_forgery_atomic(case: Case, kind: str) -> None:
    f = case.forecast
    snap = case.repo.get(SequenceSnapshot, f.snapshot_id)
    value: Artifact
    if kind == "snapshot":
        value = replace(snap, exclusions=())
    elif kind == "mask":
        # Forge a sourced mask into a padded cell while keeping value/mask agreement.
        values = ((0.0, *snap.values[0][1:]), *snap.values[1:])
        mask = ((True, *snap.mask[0][1:]), *snap.mask[1:])
        value = replace(snap, values=values, mask=mask)
    elif kind == "order":
        value = replace(snap, observation_ids=tuple(reversed(snap.observation_ids)))
    elif kind == "transform":
        old = case.repo.get(SequenceTransformArtifact, case.fixture.models[0].transform_id)
        value = replace(old, centers=tuple(v + 1 for v in old.centers))
    elif kind == "model":
        value = replace(case.fixture.models[0], intercept=100.0)
    elif kind == "forecast":
        value = replace(f, value=f.value + 1)
    elif kind == "evaluation":
        value = replace(case.engine.evaluate(case.fixture.forecasts[0], 100, 100), metrics=())
    elif kind == "observation":
        observation = case.observe(45, 2.0)
        value = replace(observation, available_ns=44)
    else:
        value = replace(f.contributions[0], contribution=100.0)
    before = case.repo._connection.execute("SELECT count(*) FROM sq_artifacts").fetchone()[0]
    with pytest.raises((ContractError, KeyError)), case.repo.transaction():
        case.repo.put(value)
    assert (
        case.repo._connection.execute("SELECT count(*) FROM sq_artifacts").fetchone()[0]
        == before
    )


@pytest.mark.parametrize("kind", ["family", "schema", "hash", "index", "links", "orphan"])
def test_sql_corruption_fails_closed(case: Case, kind: str) -> None:
    c = case.repo._connection
    for (name,) in c.execute(
        "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name LIKE 'sq_%'"
    ).fetchall():
        c.execute(f"DROP TRIGGER {name}")
    identity = case.forecast.fingerprint
    if kind == "family":
        c.execute(
            "UPDATE sq_artifacts SET type_name='SequenceModelArtifact' WHERE fingerprint=?",
            (identity,),
        )
    elif kind == "schema":
        c.execute(
            "UPDATE sq_artifacts SET schema_version='9.0' WHERE fingerprint=?", (identity,)
        )
    elif kind == "hash":
        c.execute(
            "UPDATE sq_artifacts SET payload=? WHERE fingerprint=?",
            (canonical_json(replace(case.forecast, value=100.0)), identity),
        )
    elif kind == "index":
        c.execute("UPDATE sq_records SET available_ns=123 WHERE fingerprint=?", (identity,))
    elif kind == "links":
        c.execute("DELETE FROM sq_links WHERE fingerprint=?", (identity,))
    else:
        c.execute("DELETE FROM sq_artifacts WHERE fingerprint=?", (identity,))
    with pytest.raises(ContractError):
        case.repo.audit()


def test_idempotence_missing_lookup(case: Case) -> None:
    f = case.forecast
    with case.repo.transaction():
        assert case.repo.put(f) == f.fingerprint
    assert case.repo.get_any(f.fingerprint) == f
    with pytest.raises(KeyError):
        case.repo.get(SequenceForecast, "afre.sq_forecast:1.0:" + "f" * 64)
    with pytest.raises(ContractError):
        case.repo.put(f)
    assert case.engine.audit_lineage(f.fingerprint).node_ids

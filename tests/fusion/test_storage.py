"""Additive migration, immutable bytes and hash/semantic corruption rejection."""

import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from afre.fusion import FusedForecast, FusionArtifact, FusionEngine, FusionRepository
from afre.fusion.diagnostics import DiversityMatrix
from afre.fusion.storage import fusion_schema
from afre.schema import Artifact, ContractError
from afre.selection import SelectionRepository
from afre.selection.schema import SelectionBounds
from afre.serialization import canonical_json
from examples.fusion_fixture import FusionFixture, apply_partition

Case = tuple[FusionRepository, FusionFixture]


def test_migration_preserves_ddl_metadata_rows(tmp_path: Path) -> None:
    path = tmp_path / "prior.sqlite"
    with SelectionRepository(path) as r:
        with r.transaction():
            r.put(SelectionBounds())
        ddl = dict(
            r._connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        )
        metadata = dict(r._connection.execute("SELECT * FROM metadata"))
        rows = tuple(r._connection.execute("SELECT * FROM sel_artifacts"))
    with FusionRepository(path) as r:
        current = dict(
            r._connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        )
        assert all(current[n] == s for n, s in ddl.items())
        assert dict(r._connection.execute("SELECT * FROM metadata")).items() >= metadata.items()
        assert tuple(r._connection.execute("SELECT * FROM sel_artifacts")) == rows
        assert r._connection.execute("PRAGMA user_version").fetchone()[0] == 22


def test_migration_rollback_future_and_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import afre.fusion.repository as module

    path = tmp_path / "rollback.sqlite"
    with SelectionRepository(path):
        pass
    monkeypatch.setattr(module, "fusion_schema", lambda: (*fusion_schema(), "INVALID SQL"))
    with pytest.raises(sqlite3.OperationalError):
        FusionRepository(path)
    with SelectionRepository(path) as r:
        assert r._connection.execute("PRAGMA user_version").fetchone()[0] == 21
        assert not r._connection.execute(
            "SELECT name FROM sqlite_master WHERE name LIKE 'fus_%'"
        ).fetchall()
        r._connection.execute("PRAGMA user_version=23")
    with pytest.raises(ContractError, match="future"):
        FusionRepository(path)


def prepared(repo: FusionRepository, f: FusionFixture) -> tuple[Artifact, ...]:
    e = FusionEngine(repo)
    a = e.fit(f.spec, 0, 0, 0)
    ids = apply_partition(repo, f, a.fingerprint, f.validation)
    pool = e.trial_pool(((f.spec.fingerprint, ids),))
    d = e.diversity(
        f.spec.source_ids, tuple(i for s in f.validation for i in f.observations(s)), 100
    )
    comparison = e.evaluate(ids, pool.fingerprint, 100, 100)
    return (f.references[0], f.spec, a, repo.get(FusedForecast, ids[0]), d, comparison)


@pytest.mark.parametrize("index", range(6))
def test_corrupted_payload_closed(fusion_case: Case, index: int) -> None:
    repo, f = fusion_case
    value = prepared(repo, f)[index]
    row = repo._connection.execute(
        "SELECT payload FROM fus_artifacts WHERE fingerprint=?", (value.fingerprint,)
    ).fetchone()
    wire = json.loads(row[0])
    wire["artifact"]["fields"][next(iter(wire["artifact"]["fields"]))] = "tampered"
    trigger = repo._connection.execute(
        "SELECT sql FROM sqlite_master WHERE name='immutable_fus_artifacts_update'"
    ).fetchone()[0]
    repo._connection.execute("DROP TRIGGER immutable_fus_artifacts_update")
    repo._connection.execute(
        "UPDATE fus_artifacts SET payload=? WHERE fingerprint=?",
        (json.dumps(wire), value.fingerprint),
    )
    repo._connection.execute(trigger)
    with pytest.raises(ContractError):
        repo.get_any(value.fingerprint)


@pytest.mark.parametrize("index", range(6))
def test_valid_hash_semantic_forgery_rejected(fusion_case: Case, index: int) -> None:
    repo, f = fusion_case
    value = prepared(repo, f)[index]
    forged: Artifact
    if index == 0:
        forged = replace(f.references[0], calibration_state="forged-calibration")
    elif index == 1:
        forged = replace(f.spec, horizon_id=f.references[0].target_id)
    elif index == 2:
        a = repo.get(FusionArtifact, value.fingerprint)
        forged = replace(a, intercept=88.0)
    elif index == 3:
        forecast = repo.get(FusedForecast, value.fingerprint)
        forged = replace(forecast, value=99.0)
    elif index == 4:
        d = repo.get(DiversityMatrix, value.fingerprint)
        forged = replace(d, pairs=(replace(d.pairs[0], sign_agreement=0.123), *d.pairs[1:]))
    else:
        from afre.fusion.diagnostics import FusionComparison

        c = repo.get(FusionComparison, value.fingerprint)
        forged = replace(c, deltas=tuple((i, n, 999.0) for i, n, _ in c.deltas))
    assert forged.fingerprint != value.fingerprint
    with repo.transaction(), pytest.raises(ContractError):
        repo.put(forged)


@pytest.mark.parametrize("table", ("fus_artifacts", "fus_records", "fus_links"))
@pytest.mark.parametrize("operation", ("UPDATE", "DELETE"))
def test_sql_immutability(fusion_case: Case, table: str, operation: str) -> None:
    repo, f = fusion_case
    prepared(repo, f)
    sql = (
        f"UPDATE {table} SET fingerprint=fingerprint"
        if operation == "UPDATE"
        else f"DELETE FROM {table}"
    )
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        repo._connection.execute(sql)


def test_idempotence_and_restart(fusion_case: Case, tmp_path: Path) -> None:
    repo, f = fusion_case
    values = prepared(repo, f)
    with repo.transaction(), repo.validation_cache():
        for v in values:
            assert repo.put(v) == v.fingerprint
    path = tmp_path / "reopen.sqlite"
    with sqlite3.connect(path) as target:
        repo._connection.backup(target)
    with FusionRepository(path) as restarted:
        for v in values:
            assert canonical_json(restarted.get_any(v.fingerprint)) == canonical_json(v)
        assert restarted.audit() > 0

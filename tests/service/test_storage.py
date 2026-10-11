"""Additive migration, rollback, strict layout and forged semantic projections."""

import sqlite3
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from afre.challenger import ChallengeRepository
from afre.schema import ContractError
from afre.serialization import canonical_json
from afre.service import ServiceRepository, ServiceStatus, SnapshotPublication
from afre.service.storage import links, record_index
from tests.service.conftest import ServiceCase


def test_migration_and_future(tmp_path: Path) -> None:
    path = tmp_path / "old.sqlite"
    with ChallengeRepository(path) as repo:
        old = dict(repo._connection.execute("SELECT name,sql FROM sqlite_master"))
        metadata = dict(repo._connection.execute("SELECT key,value FROM metadata"))
    with ServiceRepository(path) as repo:
        new = dict(repo._connection.execute("SELECT name,sql FROM sqlite_master"))
        assert all(new[k] == v for k, v in old.items())
        assert all(
            dict(repo._connection.execute("SELECT key,value FROM metadata"))[k] == v
            for k, v in metadata.items()
        )
        assert repo._connection.execute("PRAGMA user_version").fetchone()[0] == 25
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version=26")
    with pytest.raises(ContractError, match="future"):
        ServiceRepository(path)


def test_migration_rollback(tmp_path: Path) -> None:
    path = tmp_path / "rollback.sqlite"
    with ChallengeRepository(path):
        pass
    with (
        patch(
            "afre.service.repository.service_schema",
            return_value=("CREATE TABLE should_rollback (x TEXT)", "INVALID DDL"),
        ),
        pytest.raises(sqlite3.Error),
    ):
        ServiceRepository(path)
    with ChallengeRepository(path) as repo:
        assert repo._connection.execute("PRAGMA user_version").fetchone()[0] == 24
        assert not repo._connection.execute(
            "SELECT 1 FROM sqlite_master WHERE name='should_rollback'"
        ).fetchone()


@pytest.mark.parametrize("part", ["payload", "index", "links", "layout", "metadata"])
def test_corruption_fails_closed(service_case: ServiceCase, part: str) -> None:
    c = service_case
    s = c.publisher.publish(SnapshotPublication(c.fixture.ids("point")[0], "v1", 120))
    with c.repo.transaction():
        if part == "payload":
            c.repo._connection.execute("DROP TRIGGER immutable_svc_artifacts_update")
            c.repo._connection.execute(
                "UPDATE svc_artifacts SET payload='bad' WHERE fingerprint=?", (s.fingerprint,)
            )
        elif part == "index":
            c.repo._connection.execute("DROP TRIGGER immutable_svc_records_update")
            c.repo._connection.execute(
                "UPDATE svc_records SET producer_id='bad' WHERE fingerprint=?", (s.fingerprint,)
            )
        elif part == "links":
            c.repo._connection.execute(
                "INSERT INTO svc_links VALUES (?,?)", (s.fingerprint, "bad")
            )
        elif part == "layout":
            c.repo._connection.execute("CREATE TABLE unexpected (x TEXT)")
        else:
            c.repo._connection.execute("DROP TRIGGER immutable_metadata_update")
            c.repo._connection.execute(
                "UPDATE metadata SET value='bad' WHERE key='service_engine_version'"
            )
    assert c.service.get_snapshot(s.fingerprint).status is ServiceStatus.CORRUPT_ARTIFACT


def test_valid_hash_forgery(service_case: ServiceCase) -> None:
    c = service_case
    s = c.publisher.publish(SnapshotPublication(c.fixture.ids("point")[0], "v1", 120))
    forged = replace(
        s, output=replace(s.output, point=s.output.point + 0.5 if s.output.point else 0.5)
    )
    with c.repo.transaction():
        c.repo._connection.execute(
            "INSERT INTO svc_artifacts VALUES (?,?,?,?)",
            (forged.fingerprint, type(forged).__name__, "1.0", canonical_json(forged)),
        )
        c.repo._connection.execute(
            "INSERT INTO svc_records VALUES (?,?,?,?,?,?,?,?,?,?)", record_index(forged)
        )
        c.repo._connection.executemany(
            "INSERT INTO svc_links VALUES (?,?)",
            tuple((forged.fingerprint, i) for i in links(forged)),
        )
    assert c.service.get_snapshot(forged.fingerprint).status is ServiceStatus.CORRUPT_ARTIFACT
    with pytest.raises(ContractError, match="semantic"), c.repo.transaction():
        c.repo.put(forged)


def test_write_boundaries(service_case: ServiceCase) -> None:
    c = service_case
    s = c.publisher.publish(SnapshotPublication(c.fixture.ids("point")[0], "v1", 120))
    with pytest.raises(ContractError, match="transaction"):
        c.repo.put(s)
    with c.repo.read_snapshot(), pytest.raises(ContractError), c.repo.transaction():
        pass
    with c.repo.transaction(), pytest.raises(sqlite3.IntegrityError):
        c.repo._connection.execute(
            "DELETE FROM svc_artifacts WHERE fingerprint=?", (s.fingerprint,)
        )

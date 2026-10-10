"""Transactional additive migration, immutable projections and corruption boundaries."""

import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from afre.multiple_testing.repository import MultipleTestingRepository
from afre.multiple_testing.schema import MultipleTestingBounds
from afre.schema import ContractError
from afre.selection import SelectionRepository
from afre.selection.results import SelectionResult
from afre.selection.storage import selection_schema
from tests.selection.conftest import SelectionCase


def test_migration_preserves_prior_ddl_metadata_rows(tmp_path: Path) -> None:
    path = tmp_path / "migration.sqlite"
    with MultipleTestingRepository(path) as repo:
        with repo.transaction():
            repo.put(MultipleTestingBounds())
        ddl = dict(
            repo._connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        )
        metadata = dict(repo._connection.execute("SELECT * FROM metadata"))
        rows = tuple(repo._connection.execute("SELECT * FROM mt_artifacts"))
    with SelectionRepository(path) as repo:
        current = dict(
            repo._connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        )
        assert all(current[n] == s for n, s in ddl.items())
        assert (
            dict(repo._connection.execute("SELECT * FROM metadata")).items() >= metadata.items()
        )
        assert tuple(repo._connection.execute("SELECT * FROM mt_artifacts")) == rows
        assert repo._connection.execute("PRAGMA user_version").fetchone()[0] == 21


def test_migration_rollback_and_future_rejection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import afre.selection.repository as module

    path = tmp_path / "rollback.sqlite"
    with MultipleTestingRepository(path):
        pass
    original = selection_schema
    monkeypatch.setattr(
        module, "selection_schema", lambda: (*original(), "THIS IS NOT VALID SQL")
    )
    with pytest.raises(sqlite3.OperationalError):
        SelectionRepository(path)
    with MultipleTestingRepository(path) as repo:
        assert repo._connection.execute("PRAGMA user_version").fetchone()[0] == 20
        assert not repo._connection.execute(
            "SELECT name FROM sqlite_master WHERE name LIKE 'sel_%'"
        ).fetchall()
        repo._connection.execute("PRAGMA user_version=22")
    with pytest.raises(ContractError, match="future"):
        SelectionRepository(path)


@pytest.mark.parametrize(
    "kind",
    (
        "SearchSpace",
        "CandidateSpec",
        "ResourceBudget",
        "CandidateFitResult",
        "CandidateValidationResult",
        "SelectionResult",
        "CandidateRegistrySnapshot",
    ),
)
def test_payload_corruption_closed(case: SelectionCase, kind: str) -> None:
    repo = case.repository
    identity, payload = repo._connection.execute(
        "SELECT fingerprint,payload FROM sel_artifacts WHERE type_name=? LIMIT 1", (kind,)
    ).fetchone()
    raw = json.loads(payload)
    fields = raw["artifact"]["fields"]
    first = next(iter(fields))
    fields[first] = "tampered"
    trigger = repo._connection.execute(
        "SELECT sql FROM sqlite_master WHERE name='immutable_sel_artifacts_update'"
    ).fetchone()[0]
    repo._connection.execute("DROP TRIGGER immutable_sel_artifacts_update")
    repo._connection.execute(
        "UPDATE sel_artifacts SET payload=? WHERE fingerprint=?", (json.dumps(raw), identity)
    )
    repo._connection.execute(trigger)
    with pytest.raises(ContractError):
        repo.get_any(identity)


@pytest.mark.parametrize("projection", ("records", "links"))
def test_relational_corruption(case: SelectionCase, projection: str) -> None:
    repo = case.repository
    table = "sel_" + projection
    trigger = repo._connection.execute(
        "SELECT sql FROM sqlite_master WHERE name=?", (f"immutable_{table}_delete",)
    ).fetchone()[0]
    repo._connection.execute(f"DROP TRIGGER immutable_{table}_delete")
    repo._connection.execute(
        f"DELETE FROM {table} WHERE fingerprint=?", (case.result.fingerprint,)
    )
    repo._connection.execute(trigger)
    with pytest.raises(ContractError, match="index|link"):
        repo.resolve(SelectionResult, case.result.fingerprint)


@pytest.mark.parametrize("table", ("sel_artifacts", "sel_records", "sel_links"))
@pytest.mark.parametrize("operation", ("UPDATE", "DELETE"))
def test_immutable_sql_records(case: SelectionCase, table: str, operation: str) -> None:
    sql = f"{operation} {table} " + (
        "SET fingerprint=fingerprint" if operation == "UPDATE" else ""
    )
    if operation == "DELETE":
        sql = f"DELETE FROM {table}"
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        case.repository._connection.execute(sql)


def test_layout_and_metadata_tampering_reopen(case: SelectionCase) -> None:
    repo = case.repository
    trigger = repo._connection.execute(
        "SELECT sql FROM sqlite_master WHERE name='immutable_metadata_update'"
    ).fetchone()[0]
    repo._connection.execute("DROP TRIGGER immutable_metadata_update")
    repo._connection.execute("UPDATE metadata SET value='9.9' WHERE key='selection_schema'")
    repo._connection.execute(trigger)
    with pytest.raises(ContractError, match="metadata"):
        SelectionRepository(case.path)


@pytest.mark.parametrize(
    "field", ("train_rows_reserved", "validation_rows_reserved", "payload_bytes")
)
def test_forged_usage_with_valid_new_hash_fails_semantic_replay(
    case: SelectionCase, field: str
) -> None:
    usage = replace(case.result.usage, **{field: getattr(case.result.usage, field) + 1})
    forged = replace(case.result, usage=usage)
    with case.repository.transaction(), pytest.raises(ContractError, match="usage replay"):
        case.repository.put(forged)

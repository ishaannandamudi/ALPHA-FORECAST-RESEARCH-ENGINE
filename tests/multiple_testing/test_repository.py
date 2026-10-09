"""Transactional SQLite20 migration and hostile persisted evidence fail closed."""

import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from afre.costs import CostResearchRepository
from afre.feature_store.models import SourceReference
from afre.hashing import bytes_digest
from afre.lineage import ProvenanceRef
from afre.multiple_testing import (
    AdjustedHypothesisResult,
    HypothesisFamily,
    MultipleTestingRepository,
    PValueResult,
    ResearchTrial,
)
from afre.multiple_testing.lineage import testing_edges as reference_edges
from afre.multiple_testing.raw_tests import raw_results_for
from afre.multiple_testing.storage import multiple_testing_schema, record_index
from afre.schema import Artifact, ContractError
from afre.serialization import canonical_json, deserialize
from tests.multiple_testing.conftest import TestingCase as MTCase
from tests.multiple_testing.helpers import analyses, trial


def layout(db: sqlite3.Connection) -> tuple[tuple[object, ...], ...]:
    return tuple(
        db.execute(
            "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    )


def test_migration_prior_ddl_metadata_rows_preserved(tmp_path: Path) -> None:
    path = tmp_path / "old.sqlite"
    provenance = ProvenanceRef("native-migration", "prior-record", "1", bytes_digest(b"old"))
    source = SourceReference(provenance, provenance.fingerprint)
    with CostResearchRepository(path) as old:
        with old.transaction():
            old.put(source)
        before = layout(old._connection)
        metadata = dict(old._connection.execute("SELECT key,value FROM metadata"))
        tables = tuple(
            t
            for (t,) in old._connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        )
        rows = {
            t: old._connection.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall()
            for t in tables
            if t != "metadata"
        }
    with MultipleTestingRepository(path) as new:
        assert new._connection.execute("PRAGMA user_version").fetchone()[0] == 20
        assert set(before) <= set(layout(new._connection))
        after = dict(new._connection.execute("SELECT key,value FROM metadata"))
        assert (
            all(after[k] == v for k, v in metadata.items()) and len(after) == len(metadata) + 3
        )
        assert all(
            new._connection.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall() == rows[t]
            for t in rows
        )
        assert new.audit() >= 1
        assert new.get_any(source.fingerprint) == source


def test_migration_rollback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import afre.multiple_testing.repository as module

    path = tmp_path / "rollback.sqlite"
    with CostResearchRepository(path) as old:
        before = layout(old._connection)
        metadata = old._connection.execute("SELECT * FROM metadata ORDER BY key").fetchall()
    statements = multiple_testing_schema()
    monkeypatch.setattr(
        module,
        "multiple_testing_schema",
        lambda: (*statements, "CREATE TABLE metadata (broken TEXT)"),
    )
    with pytest.raises(sqlite3.OperationalError):
        MultipleTestingRepository(path)
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 19
        assert layout(db) == before
        assert db.execute("SELECT * FROM metadata ORDER BY key").fetchall() == metadata


@pytest.mark.parametrize("kind", ["future", "metadata", "layout"])
def test_schema_rejection(tmp_path: Path, kind: str) -> None:
    path = tmp_path / "bad.sqlite"
    with MultipleTestingRepository(path):
        pass
    with sqlite3.connect(path) as db:
        if kind == "future":
            db.execute("PRAGMA user_version=21")
        elif kind == "metadata":
            db.execute("DROP TRIGGER immutable_metadata_update")
            db.execute("UPDATE metadata SET value='99' WHERE key='multiple_testing_schema'")
        else:
            db.execute("DROP INDEX mt_family_idx")
    with pytest.raises(ContractError):
        MultipleTestingRepository(path)


@pytest.mark.parametrize("kind", ["raw", "effect", "trial", "adjusted", "analysis"])
def test_semantic_forgery_atomic(completed_case: MTCase, kind: str) -> None:
    t = trial(completed_case, "phase-5")
    p, e = raw_results_for(completed_case.repo, t.fingerprint, t.completed_ns)
    value: Artifact
    if kind == "raw":
        value = replace(p, raw_p_value=0.314159)
    elif kind == "effect":
        value = replace(e, estimate=(e.estimate or 0) + 1)
    elif kind == "trial":
        value = replace(
            t,
            observations=(
                replace(t.observations[0], value=t.observations[0].value + 1),
                *t.observations[1:],
            ),
            completed_ns=t.completed_ns + 1,
        )
    elif kind == "adjusted":
        r = completed_case.repo.resolve(
            AdjustedHypothesisResult, analyses(completed_case)[0].adjusted_ids[0]
        )
        value = replace(r, reason="manufactured")
    else:
        value = replace(analyses(completed_case)[0], reason="manufactured")
    count = completed_case.repo._connection.execute(
        "SELECT count(*) FROM mt_artifacts"
    ).fetchone()[0]
    with pytest.raises(ContractError), completed_case.repo.transaction():
        completed_case.repo.put(value)
    assert (
        completed_case.repo._connection.execute("SELECT count(*) FROM mt_artifacts").fetchone()[
            0
        ]
        == count
    )


def test_valid_hash_relational_forgery_rejected_on_resolve(completed_case: MTCase) -> None:
    t = trial(completed_case, "phase-5")
    raw = raw_results_for(completed_case.repo, t.fingerprint, t.completed_ns)[0]
    value = replace(raw, raw_p_value=0.314159)
    with completed_case.repo.transaction():
        completed_case.repo._connection.execute(
            "INSERT INTO mt_artifacts VALUES (?,?,?,?)",
            (value.fingerprint, type(value).__name__, "1.0", canonical_json(value)),
        )
        completed_case.repo._connection.execute(
            "INSERT INTO mt_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", record_index(value)
        )
        completed_case.repo._connection.executemany(
            "INSERT INTO mt_links VALUES (?,?)",
            tuple((value.fingerprint, i) for i in sorted(set(reference_edges(value)))),
        )
    with pytest.raises(ContractError, match="semantic replay"):
        completed_case.repo.resolve(PValueResult, value.fingerprint)


@pytest.mark.parametrize(
    "kind", ["payload", "type", "schema", "index", "links", "test-projection"]
)
def test_stored_projection_corruption(completed_case: MTCase, kind: str) -> None:
    t = trial(completed_case, "test-0")
    with completed_case.repo.transaction():
        if kind == "links":
            completed_case.repo._connection.execute("DROP TRIGGER immutable_mt_links_delete")
            completed_case.repo._connection.execute(
                "DELETE FROM mt_links WHERE fingerprint=?", (t.fingerprint,)
            )
        elif kind == "test-projection":
            completed_case.repo._connection.execute(
                "DROP TRIGGER immutable_mt_test_uses_delete"
            )
            completed_case.repo._connection.execute(
                "DELETE FROM mt_test_uses WHERE fingerprint=?", (t.fingerprint,)
            )
        elif kind == "index":
            completed_case.repo._connection.execute("DROP TRIGGER immutable_mt_records_update")
            completed_case.repo._connection.execute(
                "UPDATE mt_records SET family_id='forged' WHERE fingerprint=?", (t.fingerprint,)
            )
        else:
            completed_case.repo._connection.execute(
                "DROP TRIGGER immutable_mt_artifacts_update"
            )
            field, value = (
                ("payload", "{}")
                if kind == "payload"
                else ("type_name", "PValueResult")
                if kind == "type"
                else ("schema_version", "99")
            )
            completed_case.repo._connection.execute(
                f"UPDATE mt_artifacts SET {field}=? WHERE fingerprint=?", (value, t.fingerprint)
            )
    with pytest.raises(ContractError):
        completed_case.repo.resolve(ResearchTrial, t.fingerprint)


def test_idempotence_transaction_restart(mt_case: MTCase) -> None:
    f = mt_case.fixture.family
    with pytest.raises(ContractError):
        mt_case.repo.put(f)
    count = mt_case.repo._connection.execute("SELECT count(*) FROM mt_artifacts").fetchone()[0]
    mt_case.engine.family(f)
    assert (
        mt_case.repo._connection.execute("SELECT count(*) FROM mt_artifacts").fetchone()[0]
        == count
    )
    path = mt_case.repo._connection.execute("PRAGMA database_list").fetchone()[2]
    with MultipleTestingRepository(path) as restarted:
        assert restarted.resolve(HypothesisFamily, f.fingerprint) == f
        assert deserialize(canonical_json(f)) == f


@pytest.mark.parametrize("table", ["mt_artifacts", "mt_records", "mt_links", "mt_test_uses"])
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_immutable_sql_triggers(mt_case: MTCase, table: str, operation: str) -> None:
    command = (
        f"DELETE FROM {table}"
        if operation == "DELETE"
        else f"UPDATE {table} SET fingerprint=fingerprint"
    )
    # mt_test_uses needs an actual TEST completion to fire.
    if table == "mt_test_uses":
        p = mt_case.fixture.plan("test-0")
        mt_case.engine.complete(
            p.fingerprint,
            mt_case.fixture.family.fingerprint,
            100,
            100,
            test_identity="trigger-test",
        )
    with pytest.raises(sqlite3.IntegrityError), mt_case.repo.transaction():
        mt_case.repo._connection.execute(command)

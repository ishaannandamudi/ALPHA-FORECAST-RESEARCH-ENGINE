import sqlite3
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from afre.feature_store import FeatureStoreRepository
from afre.schema import ContractError
from afre.serialization import canonical_json
from afre.target_engine import TargetRepository
from afre.universe import (
    EligibilityPolicy,
    IssuerRecord,
    SecurityRecord,
    UniverseBounds,
    UniverseInputBuild,
    UniverseRepository,
    UniverseSnapshot,
)
from afre.universe.engine import build_snapshot
from afre.universe.repository import universe_schema
from afre.universe.schema import MembershipState
from examples.feature_store_demo import populate as feature_populate
from examples.target_demo import populate as target_populate
from examples.universe_demo import (
    SECURITIES,
    DemoFixture,
    correction,
    evidence,
    populate,
)
from tests.feature_store.test_repository import corrupt
from tests.universe.test_queries import insert


@pytest.mark.parametrize("prior_class", [FeatureStoreRepository, TargetRepository])
def test_additive_migration_preserves_previous_bytes(tmp_path: Path, prior_class: Any) -> None:
    path = tmp_path / "upgrade.sqlite"
    with prior_class(path) as previous:
        feature_populate(previous)
        if prior_class is TargetRepository:
            target_populate(previous)
    with sqlite3.connect(path) as connection:
        names = tuple(
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        )
        before = {
            name: connection.execute(f"SELECT * FROM {name} ORDER BY 1").fetchall()
            for name in names
        }
        layout = dict(
            connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        )
    with UniverseRepository(path) as upgraded:
        assert upgraded.audit() > 0
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 4
        after_layout = dict(
            connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        )
        assert all(after_layout[name] == ddl for name, ddl in layout.items())
        for name, rows in before.items():
            after = connection.execute(f"SELECT * FROM {name} ORDER BY 1").fetchall()
            assert set(rows) <= set(after) if name == "metadata" else rows == after
    with pytest.raises(ContractError):
        prior_class(path)


def test_migration_failure_rolls_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import afre.universe.repository as module

    path = tmp_path / "rollback.sqlite"
    with TargetRepository(path) as repository:
        target_populate(repository)
    statements = universe_schema()
    monkeypatch.setattr(module, "universe_schema", lambda: (*statements, "INVALID SQL"))
    with pytest.raises(sqlite3.OperationalError):
        UniverseRepository(path)
    with TargetRepository(path) as previous:
        assert previous.audit() > 0
        assert previous._connection.execute("PRAGMA user_version").fetchone()[0] == 3
        assert not previous._connection.execute(
            "SELECT name FROM sqlite_master WHERE name GLOB 'u_*'"
        ).fetchall()


@pytest.mark.parametrize("version", [-1, 5, 99])
def test_future_store_versions_fail_closed(tmp_path: Path, version: int) -> None:
    path = tmp_path / "future.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute(f"PRAGMA user_version={version}")
    with pytest.raises(ContractError, match="future"):
        UniverseRepository(path)


@pytest.mark.parametrize(
    "table,column,bad",
    [
        ("u_artifacts", "payload", "{}"),
        ("u_artifacts", "type_name", "Unknown"),
        ("u_artifacts", "schema_version", "2.0"),
        ("u_records", "known_ns", 999),
        ("u_records", "security_id", "wrong"),
        ("u_identities", "stable_id", "wrong"),
        ("u_definitions", "name", "wrong"),
        ("u_snapshots", "valid_ns", 999),
        ("u_eligibility", "state", "wrong"),
        ("u_build_records", "record_id", "wrong"),
        ("u_build_features", "vintage_id", "wrong"),
    ],
)
def test_corruption_fails_closed(tmp_path: Path, table: str, column: str, bad: object) -> None:
    path = tmp_path / "corrupt.sqlite"
    with UniverseRepository(path) as repository:
        populate(repository)
    with sqlite3.connect(path) as connection:
        trigger = f"immutable_{table}_update"
        ddl = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name=?", (trigger,)
        ).fetchone()[0]
        connection.execute(f"DROP TRIGGER {trigger}")
        connection.execute(
            f"UPDATE {table} SET {column}=? WHERE rowid=(SELECT min(rowid) FROM {table})",
            (bad,),
        )
        connection.execute(ddl)
    with UniverseRepository(path) as repository, pytest.raises((ContractError, KeyError)):
        repository.audit()


@pytest.mark.parametrize("kind", ["index", "metadata", "orphan", "input"])
def test_layout_and_orphan_integrity(tmp_path: Path, kind: str) -> None:
    path = tmp_path / "layout.sqlite"
    UniverseRepository(path).close()
    if kind == "metadata":
        corrupt(path, "metadata", "value", "wrong")
    else:
        with sqlite3.connect(path) as connection:
            if kind == "index":
                connection.execute("DROP INDEX u_symbol_idx")
            elif kind == "orphan":
                connection.execute(
                    "INSERT INTO u_definitions VALUES ('orphan','universe.orphan','1')"
                )
            else:
                connection.execute(
                    "INSERT INTO u_build_records VALUES ('orphan','missing','missing')"
                )
    if kind in ("orphan", "input"):
        with (
            UniverseRepository(path) as repository,
            pytest.raises(ContractError, match="orphan"),
        ):
            repository.audit()
    else:
        with pytest.raises(ContractError):
            UniverseRepository(path)


def test_immutability_idempotence_master_conflict_and_forged_snapshot(
    fixture: DemoFixture,
) -> None:
    repository = fixture.engine.repository
    insert(fixture, fixture.snapshot)
    with pytest.raises(ContractError, match="writer transaction"):
        repository.put(fixture.snapshot)
    for table in (
        "u_artifacts",
        "u_records",
        "u_identities",
        "u_definitions",
        "u_build_records",
        "u_build_features",
        "u_snapshots",
        "u_eligibility",
    ):
        for statement in (
            f"DELETE FROM {table}",
            f"UPDATE {table} SET fingerprint=fingerprint",
            f"INSERT OR REPLACE INTO {table} SELECT * FROM {table}",
        ):
            with pytest.raises(sqlite3.IntegrityError), repository.transaction():
                repository._connection.execute(statement)
    record = repository.master(SecurityRecord, SECURITIES[0].instrument.fingerprint)
    with pytest.raises(sqlite3.IntegrityError), repository.transaction():
        repository.put(replace(record, share_class="conflicting-share-class"))
    with pytest.raises(ContractError, match="deterministic"), repository.transaction():
        forged = replace(fixture.snapshot.eligibility[0], price=1234.0)
        repository.put(forged)
    with pytest.raises(sqlite3.IntegrityError), repository.transaction():
        repository.put(replace(fixture.universe, eligibility=EligibilityPolicy()))
    old = fixture.memberships[0]
    with pytest.raises(ContractError, match="predecessor"), repository.transaction():
        repository.put(
            replace(
                old,
                evidence=replace(
                    old.evidence, predecessor_id=fixture.memberships[1].fingerprint
                ),
            )
        )
    with pytest.raises(KeyError):
        repository.master(IssuerRecord, SECURITIES[0].instrument.fingerprint)
    with pytest.raises(KeyError):
        repository.get(UniverseSnapshot, "afre.u_snapshot:1.0:" + "0" * 64)
    with pytest.raises(ContractError):
        repository.get_any("afre.u_snapshot:1.0:" + "0" * 64)


def test_concurrent_backdated_correction_preserves_read_and_frozen_build(
    fixture: DemoFixture, tmp_path: Path
) -> None:
    repository = fixture.engine.repository
    snapshot = fixture.snapshot
    errors: list[BaseException] = []
    revised = replace(
        correction(fixture),
        evidence=evidence(
            SECURITIES[2].instrument, known=30, predecessor=fixture.memberships[2].fingerprint
        ),
    )

    def writer() -> None:
        try:
            with UniverseRepository(tmp_path / "universe.sqlite") as other, other.transaction():
                other.put(revised)
        except BaseException as error:
            errors.append(error)

    with repository.read_snapshot(), repository.validation_cache():
        repository.resolve(UniverseSnapshot, snapshot.fingerprint)
        thread = threading.Thread(target=writer)
        thread.start()
        thread.join(timeout=10)
        assert not thread.is_alive() and not errors
        replay = build_snapshot(
            repository, fixture.universe, 30, 30, snapshot.input_build_id, 30
        )
        assert canonical_json(replay) == canonical_json(snapshot)
    current = fixture.engine.universe_as_of(fixture.universe, 30, 30)
    assert current.fingerprint != snapshot.fingerprint
    assert (
        next(m for m in current.memberships if m.security == SECURITIES[2]).state
        is MembershipState.EXCLUDED
    )
    assert canonical_json(
        repository.get(UniverseSnapshot, snapshot.fingerprint)
    ) == canonical_json(snapshot)


@pytest.mark.parametrize(
    "field,limit,operation",
    [
        ("securities", 3, "snapshot"),
        ("records", 3, "freeze"),
        ("vintages", 1, "history"),
        ("vintages", 1, "memberships"),
        ("snapshots", 1, "snapshots"),
        ("serialized_bytes", 4000, "lineage"),
        ("lineage_nodes", 3, "lineage"),
        ("lineage_depth", 1, "lineage"),
    ],
)
def test_explicit_bounds(fixture: DemoFixture, field: str, limit: int, operation: str) -> None:
    repository = fixture.engine.repository
    if operation == "snapshots":
        fixture.engine.persist_snapshot(fixture.engine.universe_as_of(fixture.universe, 25, 25))
    repository.universe_bounds = replace(UniverseBounds(), **{field: limit})
    with pytest.raises(ContractError, match="bound"):
        if operation == "snapshot":
            fixture.engine.universe_as_of(fixture.universe, 30, 30)
        elif operation == "freeze":
            fixture.engine.freeze_source(30)
        elif operation == "history":
            fixture.engine.security_history(SECURITIES[0], 30)
        elif operation == "memberships":
            fixture.engine.universe_history(fixture.universe, 30)
        elif operation == "snapshots":
            fixture.engine.snapshot_history(fixture.universe, 30)
        else:
            repository.lineage(fixture.snapshot.fingerprint)


def test_audit_and_source_identity_membership_validation(fixture: DemoFixture) -> None:
    audit = fixture.engine.audit_security(fixture.snapshot.fingerprint, SECURITIES[0])
    insert(fixture, audit)
    assert len(audit.lineage_ids) > 10
    assert fixture.engine.audit() > 0
    build = fixture.engine.repository.get(UniverseInputBuild, fixture.snapshot.input_build_id)
    with pytest.raises(ContractError, match="backdated/future"):
        insert(fixture, replace(build, known_as_of_ns=1))
    with pytest.raises(ContractError, match="cutoff"):
        fixture.engine.universe_as_of(fixture.universe, 30, 31, build.fingerprint)

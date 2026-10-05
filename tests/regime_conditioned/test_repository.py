"""Additive migration, immutable bytes, hostile data and bounded replay."""

import shutil
import sqlite3
from pathlib import Path

import pytest

from afre.event_conditioned import EventRepository
from afre.regime_conditioned import (
    RegimeConditionedForecast,
    RegimeRepository,
    RegimeSnapshot,
)
from afre.regime_conditioned import repository as repository_module
from afre.regime_conditioned.storage import regime_schema
from afre.schema import Artifact, ContractError
from afre.serialization import canonical_json
from examples.cross_sectional_demo import cross_fixture
from tests.regime_conditioned.conftest import Case
from tests.regime_conditioned.test_temporal import context
from tests.statistical_models.test_repository import database_snapshot


def first(case: Case) -> RegimeConditionedForecast:
    return context(case)[0]


@pytest.fixture(scope="module")
def legacy(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("event-legacy") / "legacy.sqlite"
    with EventRepository(path) as repo:
        cross_fixture(repo)
    return path


def test_additive_eleven_to_twelve(tmp_path: Path, legacy: Path) -> None:
    path = tmp_path / "upgrade.sqlite"
    shutil.copyfile(legacy, path)
    before = database_snapshot(path)
    with sqlite3.connect(path) as conn:
        ddl = dict(
            conn.execute("SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")
        )
    with RegimeRepository(path) as repo:
        assert repo._connection.execute("PRAGMA user_version").fetchone()[0] == 12
        assert repo.audit() > 0
        after_ddl = dict(
            repo._connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        )
    after = database_snapshot(path)
    assert all(after[t] == rows for t, rows in before.items() if t != "metadata")
    assert set(before["metadata"]) < set(after["metadata"])
    assert all(after_ddl[k] == v for k, v in ddl.items())
    with pytest.raises(ContractError, match="future"):
        EventRepository(path)


def test_migration_rollback(
    tmp_path: Path, legacy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "rollback.sqlite"
    shutil.copyfile(legacy, path)
    before = database_snapshot(path)
    monkeypatch.setattr(
        repository_module,
        "regime_schema",
        lambda: (*regime_schema()[:2], "invalid migration SQL"),
    )
    with pytest.raises(sqlite3.OperationalError):
        RegimeRepository(path)
    assert database_snapshot(path) == before
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 11


@pytest.mark.parametrize("table", ["rc_artifacts", "rc_records"])
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE", "INSERT"])
def test_immutable_tables(case: Case, table: str, operation: str) -> None:
    sql = (
        f"UPDATE {table} SET fingerprint=fingerprint"
        if operation == "UPDATE"
        else f"DELETE FROM {table}"
        if operation == "DELETE"
        else f"INSERT INTO {table} SELECT * FROM {table} LIMIT 1"
    )
    with case.repo.transaction(), pytest.raises(sqlite3.IntegrityError, match="immutable"):
        case.repo._connection.execute(sql)


@pytest.mark.parametrize(
    "kind",
    ["future", "metadata", "layout", "hash", "family", "schema", "index", "orphan", "missing"],
)
def test_corruption_fail_closed(case: Case, kind: str) -> None:
    identity = first(case).fingerprint
    if kind in ("future", "metadata", "layout"):
        case.repo.close()
        with sqlite3.connect(case.path) as conn:
            if kind == "future":
                conn.execute("PRAGMA user_version=13")
            elif kind == "metadata":
                conn.execute("DROP TRIGGER immutable_metadata_update")
                conn.execute(
                    "UPDATE metadata SET value='future' WHERE key='regime_conditioned_schema'"
                )
            else:
                conn.execute("DROP INDEX rc_snapshot_idx")
        with pytest.raises(ContractError):
            RegimeRepository(case.path)
        return
    with case.repo.transaction():
        if kind in ("hash", "family", "schema"):
            case.repo._connection.execute("DROP TRIGGER immutable_rc_artifacts_update")
            column, value = (
                ("payload", "{}")
                if kind == "hash"
                else ("type_name", "FutureClass")
                if kind == "family"
                else ("schema_version", "2.0")
            )
            case.repo._connection.execute(
                f"UPDATE rc_artifacts SET {column}=? WHERE fingerprint=?", (value, identity)
            )
        elif kind == "index":
            case.repo._connection.execute("DROP TRIGGER immutable_rc_records_update")
            case.repo._connection.execute(
                "UPDATE rc_records SET available_ns=0 WHERE fingerprint=?", (identity,)
            )
        elif kind == "missing":
            case.repo._connection.execute("DROP TRIGGER immutable_rc_records_delete")
            case.repo._connection.execute(
                "DELETE FROM rc_records WHERE fingerprint=?", (identity,)
            )
        else:
            columns = case.repo._connection.execute("PRAGMA table_info(rc_records)").fetchall()
            values: tuple[object, ...] = (
                "orphan",
                "RegimeSnapshot",
                *(None for _ in columns[2:]),
            )
            case.repo._connection.execute(
                "INSERT INTO rc_records VALUES (" + ",".join("?" for _ in values) + ")", values
            )
    with pytest.raises(ContractError):
        case.repo.audit() if kind == "orphan" else case.repo.get(
            RegimeConditionedForecast, identity
        )


@pytest.mark.parametrize(
    "kind",
    [
        "snapshot-clock",
        "snapshot-taxonomy",
        "soft-vector",
        "model",
        "transition",
        "forecast",
        "evaluation",
        "drift",
    ],
)
def test_semantic_corruption_rejected(case: Case, kind: str) -> None:
    from afre.regime_conditioned.memberships import RegimeMembership
    from afre.regime_conditioned.schema import RegimeMembershipKind
    from afre.regime_conditioned.transitions import transition_for
    from examples.feature_store_demo import clocks
    from examples.regime_conditioned_demo import snapshot
    from tests.regime_conditioned.test_models import changed

    p, sample, s = context(case)
    bad: Artifact
    if kind == "snapshot-clock":
        with pytest.raises(ContractError):
            changed(s, clocks=clocks(1))
        return
    if kind == "snapshot-taxonomy":
        tax = changed(s.taxonomy, states=("C", "D"))
        with pytest.raises(ContractError):
            changed(s, taxonomy=tax)
        return
    if kind == "soft-vector":
        with pytest.raises(ContractError):
            RegimeMembership(
                RegimeMembershipKind.SOFT, ("A", "B"), probabilities=(("A", 0.2), ("B", 0.2))
            )
        return
    if kind == "model":
        bad = changed(case.hard.model, global_offset=case.hard.model.global_offset + 1.0)
    elif kind == "transition":
        a, b = (
            snapshot(s.taxonomy, sample, at=59, state="A"),
            snapshot(s.taxonomy, sample, at=60, state="B"),
        )
        case.engine.publish_snapshot(a)
        case.engine.publish_snapshot(b)
        bad = changed(transition_for(a, b), probability_mass_change=0.2)
    elif kind == "forecast":
        bad = changed(p, value=p.value + 1.0)
    elif kind == "evaluation":
        bad = changed(
            case.engine.evaluate(case.hard.forecast_ids, 100, 100), low_confidence_count=100
        )
    else:
        eval_a = case.engine.evaluate(case.hard.forecast_ids, 100, 100)
        eval_b = case.engine.evaluate(case.hard.test_ids, 100, 100, "corruption-drift")
        bad = changed(
            case.engine.drift(eval_a.fingerprint, eval_b.fingerprint, 100),
            state_probability_deltas=(("A", 100.0),),
        )
    before = database_snapshot(case.path)
    with (
        pytest.raises(ContractError, match="contamination"),
        case.repo.transaction(),
        case.repo.validation_cache(),
    ):
        case.repo.put(bad)
    assert database_snapshot(case.path) == before


def test_idempotence_restart_and_write_transaction(case: Case) -> None:
    p, _, s = context(case)
    with pytest.raises(ContractError, match="transaction"):
        case.repo.put(p)
    before = database_snapshot(case.path)
    case.engine.publish_snapshot(s)
    case.engine.forecast(
        case.hard.model.fingerprint,
        p.observation_id,
        p.base_forecast_id,
        60,
        p.base_probability_id,
    )
    assert database_snapshot(case.path) == before
    frozen = canonical_json(p)
    case.repo.close()
    with RegimeRepository(case.path) as repo:
        assert canonical_json(repo.get_any(p.fingerprint)) == frozen
        assert repo.audit() > 0
        with pytest.raises(KeyError):
            repo.get(RegimeSnapshot, "afre.rc_snapshot:1.0:" + "0" * 64)

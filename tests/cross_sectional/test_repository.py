"""Migration preservation, immutable storage, corruption, bounds and restart."""

import shutil
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from afre.cross_sectional import (
    CrossSectionBounds,
    CrossSectionRanking,
    CrossSectionRepository,
    PeerState,
    RawScore,
)
from afre.cross_sectional import repository as repository_module
from afre.cross_sectional.storage import cross_section_schema
from afre.multihorizon import MultiHorizonRepository
from afre.schema import Artifact, ContractError
from afre.serialization import canonical_json
from examples.multihorizon_demo import build_fixture
from tests.cross_sectional.conftest import Case
from tests.statistical_models.test_repository import database_snapshot


@pytest.fixture(scope="module")
def legacy(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("cross-section-legacy") / "legacy.sqlite"
    with MultiHorizonRepository(path) as repo:
        build_fixture(repo)
    return path


def test_additive_9_to_10(tmp_path: Path, legacy: Path) -> None:
    path = tmp_path / "upgrade.sqlite"
    shutil.copyfile(legacy, path)
    before = database_snapshot(path)
    with sqlite3.connect(path) as conn:
        ddl = dict(
            conn.execute("SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")
        )
    with CrossSectionRepository(path) as repo:
        assert repo._connection.execute("PRAGMA user_version").fetchone()[0] == 10
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
        MultiHorizonRepository(path)


def test_migration_rollback(
    tmp_path: Path, legacy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "rollback.sqlite"
    shutil.copyfile(legacy, path)
    before = database_snapshot(path)
    monkeypatch.setattr(
        repository_module,
        "cross_section_schema",
        lambda: (*cross_section_schema()[:2], "invalid migration SQL"),
    )
    with pytest.raises(sqlite3.OperationalError):
        CrossSectionRepository(path)
    assert database_snapshot(path) == before
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 9


@pytest.mark.parametrize("table", ["cs_artifacts", "cs_records", "cs_members"])
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE", "INSERT"])
def test_tables_immutable(case: Case, table: str, operation: str) -> None:
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
    ["future", "metadata", "layout", "hash", "family", "schema", "index", "member", "orphan"],
)
def test_corruption_fail_closed(case: Case, kind: str) -> None:
    rank = case.fixture.ranking
    if kind in ("future", "metadata", "layout"):
        case.repo.close()
        with sqlite3.connect(case.path) as conn:
            if kind == "future":
                conn.execute("PRAGMA user_version=11")
            elif kind == "metadata":
                conn.execute("DROP TRIGGER immutable_metadata_update")
                conn.execute(
                    "UPDATE metadata SET value='future' WHERE key='cross_sectional_schema'"
                )
            else:
                conn.execute("DROP INDEX cs_origin_idx")
        with pytest.raises(ContractError):
            CrossSectionRepository(case.path)
        return
    with case.repo.transaction():
        if kind in ("hash", "family", "schema"):
            case.repo._connection.execute("DROP TRIGGER immutable_cs_artifacts_update")
            column, value = (
                ("payload", "{}")
                if kind == "hash"
                else ("type_name", "FutureClass")
                if kind == "family"
                else ("schema_version", "2.0")
            )
            case.repo._connection.execute(
                f"UPDATE cs_artifacts SET {column}=? WHERE fingerprint=?",
                (value, rank.fingerprint),
            )
        elif kind == "index":
            case.repo._connection.execute("DROP TRIGGER immutable_cs_records_update")
            case.repo._connection.execute(
                "UPDATE cs_records SET available_ns=0 WHERE fingerprint=?", (rank.fingerprint,)
            )
        elif kind == "member":
            case.repo._connection.execute("DROP TRIGGER immutable_cs_members_delete")
            case.repo._connection.execute(
                "DELETE FROM cs_members WHERE fingerprint=?", (rank.fingerprint,)
            )
        else:
            case.repo._connection.execute(
                "INSERT INTO cs_members VALUES (?,?,?,?)", ("orphan", "security", None, None)
            )
    with pytest.raises(ContractError):
        case.repo.audit() if kind == "orphan" else case.repo.get(
            CrossSectionRanking, rank.fingerprint
        )


@pytest.mark.parametrize("kind", ["score", "rank", "normalization", "group", "membership"])
def test_semantic_tampering_rejected(case: Case, kind: str) -> None:
    f = case.fixture
    included = next(e for e in f.ranking.entries if e.rank is not None)
    value: Artifact
    if kind == "score":
        value = replace(case.repo.get(RawScore, included.raw_id), value=99.0)
    elif kind == "normalization":
        value = replace(case.repo.get(PeerState, f.ranking.normalization_id), center=99.0)
    elif kind == "group":
        assert f.ranking.group_neutral_id is not None
        value = replace(
            case.repo.get(PeerState, f.ranking.group_neutral_id),
            group_statistics=(("forged", 2, 99.0),),
        )
    elif kind == "membership":
        value = replace(
            f.ranking,
            entries=f.ranking.entries[:-1],
            eligible_count=3,
            ranked_count=2,
            coverage=2 / 3,
        )
    else:
        value = replace(
            f.ranking,
            entries=tuple(
                replace(e, rank=9.0) if e == included else e for e in f.ranking.entries
            ),
        )
    with case.repo.transaction(), pytest.raises(ContractError):
        case.repo.put(value)


@pytest.mark.parametrize(
    "kind",
    [
        "securities",
        "groups",
        "external_signals",
        "truths",
        "bytes",
        "nodes",
        "depth",
        "rankings",
        "features",
    ],
)
def test_bounds(case: Case, kind: str) -> None:
    f = case.fixture
    kwargs = {
        "serialized_bytes"
        if kind == "bytes"
        else "audit_nodes"
        if kind == "nodes"
        else "audit_depth"
        if kind == "depth"
        else kind: 1
    }
    case.repo.cross_section_bounds = CrossSectionBounds(**kwargs)
    with pytest.raises(ContractError, match="bound|too large"):
        if kind in ("nodes", "depth"):
            case.engine.audit_lineage(f.ranking.fingerprint)
        elif kind == "truths":
            case.engine.evaluate(f.ranking.fingerprint, f.targets, 100, 100)
        elif kind == "external_signals":
            from examples.cross_sectional_demo import external

            case.engine.publish_external(external(f.ranking.entries[0].security, 60, 99.0))
        elif kind == "rankings":
            case.engine.build_ranking(
                replace(f.spec, maximum_missing_fraction=0.9), f.sources, f.group_refs
            )
        elif kind == "features":
            # A zero feature bound is forbidden before any allocation.
            replace(case.repo.cross_section_bounds, features=0)
        else:
            case.engine.build_ranking(f.spec, f.sources, f.group_refs)


def test_restart_full_audit(case: Case) -> None:
    f = case.fixture
    result = case.engine.evaluate(f.ranking.fingerprint, f.targets, 100, 100)
    case.engine.audit_lineage(result.fingerprint)
    old = canonical_json(f.ranking)
    assert case.repo.audit() > 0
    case.repo.close()
    with CrossSectionRepository(case.path) as repo:
        assert canonical_json(repo.get(CrossSectionRanking, f.ranking.fingerprint)) == old
        assert repo.audit() > 0

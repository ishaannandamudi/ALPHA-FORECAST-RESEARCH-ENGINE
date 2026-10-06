"""Transactional additive migration, immutability and forged semantic/projection rejection."""

import shutil
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from afre.schema import Artifact, ContractError
from afre.sequence import SequenceRepository
from afre.serialization import canonical_json
from afre.uncertainty import (
    ForecastUncertaintyDecomposition,
    UncertaintyEvaluationSpec,
    UncertaintyRepository,
)
from afre.uncertainty import repository as repository_module
from afre.uncertainty.storage import uncertainty_schema
from tests.statistical_models.test_repository import database_snapshot
from tests.uncertainty.conftest import Base, Case


def legacy_copy(base: Base, path: Path) -> None:
    shutil.copyfile(base.path, path)
    with sqlite3.connect(path) as c:
        triggers = c.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='trigger'"
        ).fetchall()
        for name, _ in triggers:
            c.execute(f"DROP TRIGGER {name}")
        for (name,) in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'unc_%'"
        ).fetchall():
            c.execute(f"DROP TABLE {name}")
        c.execute("DELETE FROM metadata WHERE key LIKE 'uncertainty_%'")
        for name, sql in triggers:
            if "unc_" not in name:
                c.execute(sql)
        c.execute("PRAGMA user_version=15")


def test_migration_preserves_all_prior(base: Base, tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite"
    legacy_copy(base, path)
    before = database_snapshot(path)
    with SequenceRepository(path) as old:
        ddl = dict(
            old._connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        )
        metadata = dict(old._connection.execute("SELECT key,value FROM metadata"))
    with UncertaintyRepository(path) as repo:
        assert repo._connection.execute("PRAGMA user_version").fetchone()[0] == 16
        afterddl = dict(
            repo._connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        )
        aftermetadata = dict(repo._connection.execute("SELECT key,value FROM metadata"))
    after = database_snapshot(path)
    assert all(after[t] == rows for t, rows in before.items() if t != "metadata")
    assert all(afterddl[k] == v for k, v in ddl.items())
    assert all(aftermetadata[k] == v for k, v in metadata.items())
    with pytest.raises(ContractError, match="future"):
        SequenceRepository(path)


def test_migration_rollback_future(
    base: Base, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "rollback.sqlite"
    legacy_copy(base, path)
    before = database_snapshot(path)
    monkeypatch.setattr(
        repository_module,
        "uncertainty_schema",
        lambda: (*uncertainty_schema()[:2], "invalid migration SQL"),
    )
    with pytest.raises(sqlite3.OperationalError):
        UncertaintyRepository(path)
    assert database_snapshot(path) == before
    with sqlite3.connect(path) as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == 15
        c.execute("PRAGMA user_version=17")
    with pytest.raises(ContractError, match="future"):
        UncertaintyRepository(path)


@pytest.mark.parametrize("table", ["unc_artifacts", "unc_records", "unc_links"])
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
        "component",
        "covariance",
        "decomposition",
        "pair",
        "evaluation",
        "interval",
        "comparison",
        "drift",
        "audit",
    ],
)
def test_semantic_forgery(case: Case, kind: str) -> None:
    from afre.uncertainty import UncertaintyInterval

    d = case.result()
    a = case.engine.evaluate(
        case.fixture.results("gaussian"), UncertaintyEvaluationSpec(bucket_count=2), 100, 100
    )
    value: Artifact
    if kind == "component":
        c = next(c for c in d.components if c.value is not None)
        value = replace(c, value=100.0)
    elif kind == "covariance":
        cov = case.fixture.covariances[0]
        value = replace(cov, covariance=tuple(tuple(v * 2 for v in r) for r in cov.covariance))
    elif kind == "decomposition":
        value = replace(d, total_variance=100.0)
    elif kind == "pair":
        value = replace(a.pairs[0], truth=100.0)
    elif kind == "evaluation":
        value = replace(a, scores=())
    elif kind == "interval":
        old = case.repo.get(UncertaintyInterval, d.interval_id)
        assert old.lower is not None and old.upper is not None
        value = replace(
            old,
            lower=old.lower + 1,
            upper=old.upper + 1,
            width=(old.upper + 1) - (old.lower + 1),
        )
    elif kind == "comparison":
        b = case.engine.evaluate(
            case.fixture.results("empirical"),
            UncertaintyEvaluationSpec(bucket_count=2),
            100,
            100,
        )
        value = replace(
            case.engine.compare(a.fingerprint, b.fingerprint, 100), coverage_delta=99.0
        )
    elif kind == "drift":
        b = case.engine.evaluate(
            case.fixture.test_ids,
            UncertaintyEvaluationSpec(bucket_count=2),
            100,
            100,
            "forge-test",
        )
        value = replace(
            case.engine.drift((a.fingerprint, b.fingerprint), 100), variance_shifts=(99.0,)
        )
    else:
        value = replace(case.engine.audit_lineage(d.fingerprint), assertions=("false claim",))
    before = case.repo._connection.execute("SELECT count(*) FROM unc_artifacts").fetchone()[0]
    with pytest.raises((ContractError, KeyError)), case.repo.transaction():
        case.repo.put(value)
    assert (
        case.repo._connection.execute("SELECT count(*) FROM unc_artifacts").fetchone()[0]
        == before
    )


@pytest.mark.parametrize(
    "kind", ["family", "schema", "hash", "index", "links", "orphan", "metadata", "ddl"]
)
def test_sql_corruption(case: Case, kind: str) -> None:
    c = case.repo._connection
    for (name,) in c.execute(
        "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name LIKE 'unc_%'"
    ).fetchall():
        c.execute(f"DROP TRIGGER {name}")
    identity = case.result().fingerprint
    if kind == "family":
        c.execute(
            "UPDATE unc_artifacts SET type_name='ParameterCovariance' WHERE fingerprint=?",
            (identity,),
        )
    elif kind == "schema":
        c.execute(
            "UPDATE unc_artifacts SET schema_version='2.0' WHERE fingerprint=?", (identity,)
        )
    elif kind == "hash":
        c.execute(
            "UPDATE unc_artifacts SET payload=? WHERE fingerprint=?",
            (canonical_json(replace(case.result(), total_variance=100.0)), identity),
        )
    elif kind == "index":
        c.execute("UPDATE unc_records SET available_ns=123 WHERE fingerprint=?", (identity,))
    elif kind == "links":
        c.execute("DELETE FROM unc_links WHERE fingerprint=?", (identity,))
    elif kind == "orphan":
        c.execute("DELETE FROM unc_artifacts WHERE fingerprint=?", (identity,))
    elif kind == "metadata":
        c.execute("DROP TRIGGER immutable_metadata_delete")
        c.execute("DELETE FROM metadata WHERE key='uncertainty_schema'")
    else:
        c.execute("DROP INDEX unc_target_idx")
    with pytest.raises(ContractError):
        if kind in ("metadata", "ddl"):
            case.repo._validate_layout()
        else:
            case.repo.get_any(identity)


def test_idempotence_and_restart(case: Case) -> None:
    d = case.result()
    with case.repo.transaction():
        assert case.repo.put(d) == d.fingerprint
    with pytest.raises(ContractError):
        case.repo.put(d)
    with pytest.raises(KeyError):
        case.repo.get(
            ForecastUncertaintyDecomposition, "afre.unc_decomposition:1.0:" + "f" * 64
        )
    path = case.repo._connection.execute("PRAGMA database_list").fetchone()[2]
    with UncertaintyRepository(path) as second:
        assert canonical_json(second.get_any(d.fingerprint)) == canonical_json(d)
    audit = case.engine.audit_lineage(d.fingerprint)
    assert d.forecast_id in audit.node_ids
    assert case.fixture.covariances[0].fingerprint in audit.node_ids

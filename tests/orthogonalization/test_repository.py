"""Additive migration, corruption detection, semantic replay and immutable indexes."""

import shutil
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from afre.orthogonalization import (
    OrthogonalizationRepository,
    RedundancyMatrix,
    SignalObservation,
)
from afre.orthogonalization import repository as repository_module
from afre.orthogonalization.storage import orthogonalization_schema
from afre.research_datasets.schema import Partition
from afre.schema import Artifact, ContractError
from afre.serialization import canonical_json
from afre.uncertainty import UncertaintyRepository
from tests.orthogonalization.conftest import Base, Case
from tests.statistical_models.test_repository import database_snapshot


def legacy_copy(base: Base, path: Path) -> None:
    shutil.copyfile(base.path, path)
    with sqlite3.connect(path) as c:
        for (name,) in c.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' "
            "AND name LIKE 'immutable_ort_%'"
        ).fetchall():
            c.execute(f"DROP TRIGGER {name}")
        for (name,) in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'ort_%'"
        ).fetchall():
            c.execute(f"DROP TABLE {name}")
        metadata_trigger = c.execute(
            "SELECT sql FROM sqlite_master WHERE name='immutable_metadata_delete'"
        ).fetchone()[0]
        c.execute("DROP TRIGGER immutable_metadata_delete")
        c.execute("DELETE FROM metadata WHERE key LIKE 'orthogonalization_%'")
        c.execute(metadata_trigger)
        c.execute("PRAGMA user_version=16")


def test_additive_migration(base: Base, tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite"
    legacy_copy(base, path)
    before = database_snapshot(path)
    with UncertaintyRepository(path) as old:
        ddl = dict(
            old._connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        )
    with OrthogonalizationRepository(path) as r:
        assert r._connection.execute("PRAGMA user_version").fetchone()[0] == 17
        afterddl = dict(
            r._connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        )
    after = database_snapshot(path)
    assert all(after[k] == v for k, v in before.items() if k != "metadata")
    assert all(afterddl[k] == v for k, v in ddl.items())
    assert set(after["metadata"]) >= set(before["metadata"])
    with pytest.raises(ContractError):
        UncertaintyRepository(path)


def test_rollback_future(base: Base, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "rollback.sqlite"
    legacy_copy(base, path)
    before = database_snapshot(path)
    monkeypatch.setattr(
        repository_module,
        "orthogonalization_schema",
        lambda: (*orthogonalization_schema()[:2], "invalid migration SQL"),
    )
    with pytest.raises(sqlite3.OperationalError):
        OrthogonalizationRepository(path)
    assert database_snapshot(path) == before
    with sqlite3.connect(path) as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == 16
        c.execute("PRAGMA user_version=18")
    with pytest.raises(ContractError, match="future"):
        OrthogonalizationRepository(path)


@pytest.mark.parametrize("table", ["ort_artifacts", "ort_records", "ort_links"])
@pytest.mark.parametrize("verb", ["UPDATE", "DELETE"])
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
    [
        "coefficient",
        "center",
        "scale",
        "row",
        "observation",
        "matrix",
        "residual",
        "evaluation",
        "target-model",
        "partial",
        "stability",
        "audit",
    ],
)
def test_semantic_forgery(case: Case, kind: str) -> None:
    e, f = case.engine, case.fixture
    model = f.projection
    vals = f.residual_ids(Partition.VALIDATION)
    evaluation = e.evaluate(vals, 100, 100)
    value: Artifact
    if kind == "coefficient":
        value = replace(model, coefficients=tuple(v + 0.1 for v in model.coefficients))
    elif kind == "center":
        value = replace(model, centers=tuple(v + 0.1 for v in model.centers))
    elif kind == "scale":
        value = replace(model, scales=tuple(v * 2 for v in model.scales))
    elif kind == "row":
        value = replace(f.rows[0], candidate=100.0)
    elif kind == "observation":
        value = replace(
            case.repo.get(SignalObservation, f.rows[0].observation_ids[0]), value=100.0
        )
    elif kind == "matrix":
        old = case.repo.get(RedundancyMatrix, model.matrix_id)
        value = replace(old, intersection_sample_ids=old.intersection_sample_ids[1:])
    elif kind == "residual":
        oldv = f.residuals[0]
        assert oldv.raw_candidate is not None and oldv.projected is not None
        value = replace(
            oldv,
            raw_candidate=oldv.raw_candidate + 1,
            residual=oldv.raw_candidate + 1 - oldv.projected,
        )
    elif kind == "evaluation":
        value = replace(evaluation, projection_metrics=())
    elif kind == "target-model":
        oldpair = e.fit_target_models(model.fingerprint, 40)
        value = replace(oldpair, base_intercept=oldpair.base_intercept + 1)
    elif kind == "partial":
        oldpart = e.partial(vals, vals, 100)
        value = replace(oldpart, pearson=replace(oldpart.pearson, value=0.5))
    elif kind == "stability":
        a = e.evaluate(
            tuple(v.fingerprint for v in f.residuals if v.origin.timestamp_ns == 50), 100, 100
        )
        b = e.evaluate(
            tuple(v.fingerprint for v in f.residuals if v.origin.timestamp_ns == 60), 100, 100
        )
        oldst = e.stability((a.fingerprint, b.fingerprint), 100)
        value = replace(oldst, coefficient_ranges=())
    else:
        oldaudit = e.audit_lineage(evaluation.fingerprint)
        value = replace(oldaudit, assertions=("forged",))
    with pytest.raises(ContractError), case.repo.transaction():
        case.repo.put(value)


@pytest.mark.parametrize(
    "kind",
    [
        "reference",
        "coefficient",
        "preprocessing",
        "residual",
        "matrix",
        "evaluation",
        "type",
        "schema",
        "index",
        "links",
    ],
)
def test_persisted_corruption(case: Case, kind: str) -> None:
    f = case.fixture
    evaluation = case.engine.evaluate(f.residual_ids(Partition.VALIDATION), 100, 100)
    value: Artifact = (
        f.spec.candidate
        if kind == "reference"
        else f.residuals[0]
        if kind == "residual"
        else case.repo.get(RedundancyMatrix, f.projection.matrix_id)
        if kind == "matrix"
        else evaluation
        if kind == "evaluation"
        else f.projection
    )
    c = case.repo._connection
    if kind == "links":
        c.execute("DROP TRIGGER immutable_ort_links_delete")
        c.execute("DELETE FROM ort_links WHERE fingerprint=?", (value.fingerprint,))
    elif kind == "index":
        table = "ort_records" if kind == "index" else "ort_links"
        c.execute(f"DROP TRIGGER immutable_{table}_update")
        column = "available_ns" if kind == "index" else "reference_id"
        replacement = 999 if kind == "index" else f.spec.candidate.fingerprint
        c.execute(
            f"UPDATE {table} SET {column}=? WHERE fingerprint=?",
            (replacement, value.fingerprint),
        )
    else:
        c.execute("DROP TRIGGER immutable_ort_artifacts_update")
        if kind in ("type", "schema"):
            column = "type_name" if kind == "type" else "schema_version"
            c.execute(
                f"UPDATE ort_artifacts SET {column}=? WHERE fingerprint=?",
                ("invalid", value.fingerprint),
            )
        else:
            payload = canonical_json(value).replace(
                '"schema_version":"1.0"', '"schema_version":"9.0"', 1
            )
            assert payload != canonical_json(value)
            c.execute(
                "UPDATE ort_artifacts SET payload=? WHERE fingerprint=?",
                (payload, value.fingerprint),
            )
    with pytest.raises(ContractError):
        case.repo.get_any(value.fingerprint)


def test_restart_audit_indexes(case: Case) -> None:
    evaluation = case.engine.evaluate(case.fixture.residual_ids(Partition.VALIDATION), 100, 100)
    audit = case.engine.audit_lineage(evaluation.fingerprint)
    assert case.fixture.projection.fingerprint in audit.node_ids
    assert case.fixture.projection.train_sample_ids[0] in audit.node_ids
    identities = tuple(
        i[0]
        for i in case.repo._connection.execute(
            "SELECT fingerprint FROM ort_artifacts ORDER BY fingerprint"
        )
    )
    before = tuple(canonical_json(case.repo.get_any(i)) for i in identities)
    path = case.repo._connection.execute("PRAGMA database_list").fetchone()[2]
    with OrthogonalizationRepository(path) as reopened:
        assert tuple(canonical_json(reopened.get_any(i)) for i in identities) == before
        assert reopened.audit() >= len(identities)
        assert (
            len(
                reopened._connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'ort_%'"
                ).fetchall()
            )
            == 6
        )


@pytest.mark.parametrize("kind", ["metadata", "schema", "version"])
def test_layout_tamper(case: Case, kind: str) -> None:
    path = case.repo._connection.execute("PRAGMA database_list").fetchone()[2]
    c = case.repo._connection
    if kind == "metadata":
        c.execute("DROP TRIGGER immutable_metadata_update")
        c.execute("UPDATE metadata SET value='wrong' WHERE key='orthogonalization_schema'")
    elif kind == "schema":
        c.execute("DROP INDEX ort_origin_idx")
    else:
        c.execute("PRAGMA user_version=18")
    with pytest.raises(ContractError):
        OrthogonalizationRepository(path)

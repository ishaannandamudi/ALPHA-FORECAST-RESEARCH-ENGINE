"""Transactional 13→14, unchanged prior registry bytes, semantic and indexed corruption."""

import shutil
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from afre.mixture import MixtureRepository
from afre.nonlinear import (
    FittedTransformArtifact,
    InteractionMatrix,
    NonlinearForecast,
    NonlinearRepository,
)
from afre.nonlinear import repository as repository_module
from afre.nonlinear.storage import nonlinear_schema
from afre.schema import Artifact, ContractError
from afre.serialization import canonical_json
from examples.mixture_demo import build_fixture
from tests.nonlinear.conftest import Case
from tests.statistical_models.test_repository import database_snapshot


@pytest.fixture(scope="module")
def legacy(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("nonlinear-legacy") / "legacy.sqlite"
    with MixtureRepository(path) as repo:
        build_fixture(repo)
    return path


def test_additive_thirteen_to_fourteen(tmp_path: Path, legacy: Path) -> None:
    path = tmp_path / "upgrade.sqlite"
    shutil.copyfile(legacy, path)
    before = database_snapshot(path)
    with sqlite3.connect(path) as connection:
        ddl = dict(
            connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        )
    with NonlinearRepository(path) as repo:
        assert repo._connection.execute("PRAGMA user_version").fetchone()[0] == 14
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
        MixtureRepository(path)


def test_migration_rollback(
    tmp_path: Path, legacy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "rollback.sqlite"
    shutil.copyfile(legacy, path)
    before = database_snapshot(path)
    monkeypatch.setattr(
        repository_module,
        "nonlinear_schema",
        lambda: (*nonlinear_schema()[:2], "invalid migration SQL"),
    )
    with pytest.raises(sqlite3.OperationalError):
        NonlinearRepository(path)
    assert database_snapshot(path) == before
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 13


@pytest.mark.parametrize("table", ["nl_artifacts", "nl_records", "nl_links"])
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE", "INSERT"])
def test_immutable(case: Case, table: str, operation: str) -> None:
    sql = (
        f"UPDATE {table} SET fingerprint=fingerprint"
        if operation == "UPDATE"
        else f"DELETE FROM {table}"
        if operation == "DELETE"
        else f"INSERT INTO {table} SELECT * FROM {table} LIMIT 1"
    )
    with case.repo.transaction(), pytest.raises(sqlite3.IntegrityError):
        case.repo._connection.execute(sql)


@pytest.mark.parametrize(
    "kind",
    [
        "future",
        "metadata",
        "layout",
        "payload",
        "family",
        "schema",
        "index",
        "link",
        "missing",
        "orphan",
        "orphan-link",
    ],
)
def test_corruption(case: Case, kind: str) -> None:
    identity = case.forecast.fingerprint
    if kind in ("future", "metadata", "layout"):
        case.repo.close()
        with sqlite3.connect(case.path) as connection:
            if kind == "future":
                connection.execute("PRAGMA user_version=15")
            elif kind == "metadata":
                connection.execute("DROP TRIGGER immutable_metadata_update")
                connection.execute(
                    "UPDATE metadata SET value='future' WHERE key='nonlinear_schema'"
                )
            else:
                connection.execute("DROP INDEX nl_model_idx")
        with pytest.raises(ContractError):
            NonlinearRepository(case.path)
        return
    with case.repo.transaction():
        if kind in ("payload", "family", "schema"):
            case.repo._connection.execute("DROP TRIGGER immutable_nl_artifacts_update")
            column, content = (
                ("payload", "{}")
                if kind == "payload"
                else ("type_name", "UnknownClass")
                if kind == "family"
                else ("schema_version", "2.0")
            )
            case.repo._connection.execute(
                f"UPDATE nl_artifacts SET {column}=? WHERE fingerprint=?", (content, identity)
            )
        elif kind == "index":
            case.repo._connection.execute("DROP TRIGGER immutable_nl_records_update")
            case.repo._connection.execute(
                "UPDATE nl_records SET available_ns=0 WHERE fingerprint=?", (identity,)
            )
        elif kind == "missing":
            case.repo._connection.execute("DROP TRIGGER immutable_nl_records_delete")
            case.repo._connection.execute(
                "DELETE FROM nl_records WHERE fingerprint=?", (identity,)
            )
        elif kind == "link":
            case.repo._connection.execute("DROP TRIGGER immutable_nl_links_delete")
            case.repo._connection.execute(
                "DELETE FROM nl_links WHERE fingerprint=?", (identity,)
            )
        elif kind == "orphan":
            case.repo._connection.execute(
                "INSERT INTO nl_records VALUES (" + ",".join("?" for _ in range(14)) + ")",
                ("orphan", *(None for _ in range(13))),
            )
        else:
            case.repo._connection.execute(
                "INSERT INTO nl_links VALUES (?,?)", ("orphan", identity)
            )
    with pytest.raises(ContractError):
        if kind.startswith("orphan"):
            case.repo.audit()
        else:
            case.repo.get(NonlinearForecast, identity)


@pytest.mark.parametrize(
    "kind",
    [
        "definition",
        "knots",
        "coefficients",
        "tree",
        "forecast",
        "evaluation",
        "scalar",
        "matrix",
    ],
)
def test_semantic_forgery_fails_atomic(case: Case, kind: str) -> None:
    value: Artifact
    if kind == "definition":
        definition = case.fixture.specs[0].interaction_set.definitions[0]
        feature = replace(definition.inputs[0], source_key=("forged",))
        value = replace(definition, inputs=(feature, *definition.inputs[1:]))
    elif kind == "knots":
        state = case.repo.get(FittedTransformArtifact, case.fixture.models[0].transform_ids[0])
        value = replace(state, knots=tuple(k + 1 for k in state.knots))
    elif kind == "coefficients":
        model = case.fixture.models[0]
        value = replace(model, intercept=model.intercept + 1.0)
    elif kind == "tree":
        model = case.fixture.models[2]
        value = replace(
            model,
            nodes=(replace(model.nodes[0], value=model.nodes[0].value + 1.0), *model.nodes[1:]),
        )
    elif kind == "forecast":
        value = replace(case.forecast, value=case.forecast.value + 1.0)
    elif kind == "evaluation":
        evaluation = case.engine.evaluate(case.fixture.forecast_ids[0], 100, 100)
        value = replace(evaluation, metrics=())
    elif kind == "scalar":
        scalar = case.inputs.scalars[0]
        value = replace(scalar, value=(scalar.value or 0.0) + 1.0)
    else:
        matrix = case.repo.get(InteractionMatrix, case.fixture.models[0].matrix_id)
        value = replace(
            matrix,
            rows=(
                replace(matrix.rows[0], response=matrix.rows[0].response + 1.0),
                *matrix.rows[1:],
            ),
        )
    before = case.repo._connection.execute("SELECT count(*) FROM nl_artifacts").fetchone()[0]
    with pytest.raises((ContractError, KeyError)), case.repo.transaction():
        case.repo.put(value)
    assert (
        case.repo._connection.execute("SELECT count(*) FROM nl_artifacts").fetchone()[0]
        == before
    )


def test_idempotence_lookup_restart_and_audit(case: Case) -> None:
    forecast = case.forecast
    before = canonical_json(forecast)
    with case.repo.transaction():
        assert case.repo.put(forecast) == forecast.fingerprint
    assert case.repo.get_any(forecast.fingerprint) == forecast
    with pytest.raises(KeyError):
        case.repo.get(NonlinearForecast, "afre.nl_forecast:1.0:" + "f" * 64)
    with pytest.raises(ContractError):
        case.repo.put(forecast)
    audit = case.engine.audit_lineage(forecast.fingerprint)
    assert forecast.model_id in audit.node_ids and case.inputs.fingerprint in audit.node_ids
    with NonlinearRepository(case.path) as reader:
        assert canonical_json(reader.get(NonlinearForecast, forecast.fingerprint)) == before
        assert reader.audit() > 0

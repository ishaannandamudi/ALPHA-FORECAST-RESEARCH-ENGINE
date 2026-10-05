"""Strict additive store13 migration, immutable records and corruption rejection."""

import json
import shutil
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from afre.mixture import MixtureForecast, MixtureRepository
from afre.mixture import repository as repository_module
from afre.mixture.storage import mixture_schema
from afre.regime_conditioned import RegimeRepository
from afre.schema import ContractError
from afre.serialization import canonical_json
from examples.regime_conditioned_demo import build_fixture
from tests.mixture.conftest import Case
from tests.statistical_models.test_repository import database_snapshot


@pytest.fixture(scope="module")
def legacy(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("mixture-legacy") / "legacy.sqlite"
    with RegimeRepository(path) as repo:
        build_fixture(repo)
    return path


def test_additive_twelve_to_thirteen(tmp_path: Path, legacy: Path) -> None:
    path = tmp_path / "upgrade.sqlite"
    shutil.copyfile(legacy, path)
    before = database_snapshot(path)
    with sqlite3.connect(path) as conn:
        ddl = dict(
            conn.execute("SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")
        )
    with MixtureRepository(path) as repo:
        assert repo._connection.execute("PRAGMA user_version").fetchone()[0] == 13
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
        RegimeRepository(path)


def test_rollback(tmp_path: Path, legacy: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "rollback.sqlite"
    shutil.copyfile(legacy, path)
    before = database_snapshot(path)
    monkeypatch.setattr(
        repository_module,
        "mixture_schema",
        lambda: (*mixture_schema()[:2], "invalid migration SQL"),
    )
    with pytest.raises(sqlite3.OperationalError):
        MixtureRepository(path)
    assert database_snapshot(path) == before
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 12


@pytest.mark.parametrize("table", ["mix_artifacts", "mix_records"])
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE", "INSERT"])
def test_immutable(case: Case, table: str, operation: str) -> None:
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
    ["future", "metadata", "layout", "hash", "family", "schema", "index", "missing", "orphan"],
)
def test_corruption(case: Case, kind: str) -> None:
    identity = case.forecast.fingerprint
    if kind in ("future", "metadata", "layout"):
        case.repo.close()
        with sqlite3.connect(case.path) as conn:
            if kind == "future":
                conn.execute("PRAGMA user_version=14")
            elif kind == "metadata":
                conn.execute("DROP TRIGGER immutable_metadata_update")
                conn.execute("UPDATE metadata SET value='future' WHERE key='mixture_schema'")
            else:
                conn.execute("DROP INDEX mix_gate_idx")
        with pytest.raises(ContractError):
            MixtureRepository(case.path)
        return
    with case.repo.transaction():
        if kind in ("hash", "family", "schema"):
            case.repo._connection.execute("DROP TRIGGER immutable_mix_artifacts_update")
            column, value = (
                ("payload", "{}")
                if kind == "hash"
                else ("type_name", "UnknownClass")
                if kind == "family"
                else ("schema_version", "2.0")
            )
            case.repo._connection.execute(
                f"UPDATE mix_artifacts SET {column}=? WHERE fingerprint=?", (value, identity)
            )
        elif kind == "index":
            case.repo._connection.execute("DROP TRIGGER immutable_mix_records_update")
            case.repo._connection.execute(
                "UPDATE mix_records SET available_ns=0 WHERE fingerprint=?", (identity,)
            )
        elif kind == "missing":
            case.repo._connection.execute("DROP TRIGGER immutable_mix_records_delete")
            case.repo._connection.execute(
                "DELETE FROM mix_records WHERE fingerprint=?", (identity,)
            )
        else:
            case.repo._connection.execute(
                "INSERT INTO mix_records VALUES (" + ",".join("?" for _ in range(14)) + ")",
                ("orphan", *(None for _ in range(13))),
            )
    with pytest.raises(ContractError):
        case.repo.audit() if kind == "orphan" else case.repo.get(MixtureForecast, identity)


@pytest.mark.parametrize(
    "name",
    [
        "ExpertReference",
        "FixedGateSpec",
        "GateModelArtifact",
        "MixtureComponent",
        "MixtureForecast",
        "MixtureEvaluation",
    ],
)
def test_tampered_payloads_fail_hash_checks(case: Case, name: str) -> None:
    case.engine.evaluate(case.fixture.forecast_ids, 100, 100)
    identity, payload = case.repo._connection.execute(
        "SELECT fingerprint,payload FROM mix_artifacts WHERE type_name=? LIMIT 1", (name,)
    ).fetchone()
    decoded = json.loads(payload)
    decoded["unknown_tamper"] = name
    with case.repo.transaction():
        case.repo._connection.execute("DROP TRIGGER immutable_mix_artifacts_update")
        case.repo._connection.execute(
            "UPDATE mix_artifacts SET payload=? WHERE fingerprint=?",
            (json.dumps(decoded), identity),
        )
    with pytest.raises((ContractError, TypeError, ValueError)):
        case.repo.get_any(identity)


def test_semantic_gate_binding_component_evaluation_forgery(case: Case) -> None:
    from afre.mixture import ExpertForecastBinding

    binding = case.repo.get(
        ExpertForecastBinding, case.forecast.request.expert_inputs[0][1] or ""
    )
    forged = replace(binding, available_ns=binding.available_ns + 1)
    with case.repo.transaction(), pytest.raises(ContractError, match="contamination"):
        case.repo.put(forged)
    weights = tuple((i, 1 - w) for i, w in case.fixture.learned.weights)
    forged_gate = replace(case.fixture.learned, weights=weights)
    with case.repo.transaction(), pytest.raises(ContractError, match="contamination"):
        case.repo.put(forged_gate)
    evaluation = case.engine.evaluate(case.fixture.forecast_ids, 100, 100)
    with case.repo.transaction(), pytest.raises(ContractError, match="contamination"):
        case.repo.put(replace(evaluation, metrics=()))
    assert case.repo.get(MixtureForecast, case.forecast.fingerprint) == case.forecast


def test_idempotence(case: Case) -> None:
    before = canonical_json(case.forecast)
    with case.repo.transaction():
        assert case.repo.put(case.forecast) == case.forecast.fingerprint
    assert canonical_json(case.engine.forecast(case.forecast.request)) == before

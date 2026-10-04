"""Additive migration, immutable writes, corruption, restart and concurrency."""

import hashlib
import json
import shutil
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from afre.research_datasets import DatasetEngine, DatasetRepository, ResearchDatasetManifest
from afre.schema import ContractError
from afre.serialization import canonical_json
from afre.statistical_models import (
    FittedModelArtifact,
    ModelBounds,
    ModelEngine,
    ModelFitRun,
    ModelRepository,
)
from afre.statistical_models.storage import model_schema
from examples.feature_store_demo import clocks, source_vintage
from examples.research_dataset_demo import populate
from examples.universe_demo import SECURITIES
from tests.statistical_models.conftest import ModelCase


@pytest.fixture(scope="module")
def legacy_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("model-legacy") / "research.sqlite"
    with DatasetRepository(path) as repo:
        fixture = populate(repo)
        dataset = DatasetEngine(repo).build_dataset(
            fixture.definition, fixture.requests, 100, 100
        )
        with repo.transaction():
            repo.put(replace(dataset, engine_version="0.5.0"))
    return path


def database_snapshot(path: Path) -> dict[str, tuple[tuple[object, ...], ...]]:
    with sqlite3.connect(path) as connection:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ]
        return {
            table: tuple(connection.execute(f"SELECT * FROM {table} ORDER BY 1"))
            for table in tables
        }


def test_additive_migration_preserves_old_bytes(tmp_path: Path, legacy_path: Path) -> None:
    path = tmp_path / "upgrade.sqlite"
    shutil.copyfile(legacy_path, path)
    before = database_snapshot(path)
    with sqlite3.connect(path) as connection:
        old_sql = dict(
            connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        )
    with ModelRepository(path) as repo:
        assert repo._connection.execute("PRAGMA user_version").fetchone()[0] == 6
        for identity, name in repo._connection.execute(
            "SELECT fingerprint,type_name FROM r_artifacts "
            "WHERE type_name='ResearchDatasetManifest'"
        ):
            assert name == "ResearchDatasetManifest"
            value = repo.get(ResearchDatasetManifest, identity)
            repo._validate_links(value)
        repo.audit()
    after = database_snapshot(path)
    assert all(after[t] == rows for t, rows in before.items() if t != "metadata")
    assert set(before["metadata"]) < set(after["metadata"])
    with sqlite3.connect(path) as connection:
        sql = dict(
            connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        )
    assert all(sql[name] == statement for name, statement in old_sql.items())


def test_migration_rollback(
    tmp_path: Path, legacy_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "rollback.sqlite"
    shutil.copyfile(legacy_path, path)
    before = database_snapshot(path)
    monkeypatch.setattr(
        "afre.statistical_models.repository.model_schema",
        lambda: (*model_schema()[:1], "INVALID MIGRATION"),
    )
    with pytest.raises(sqlite3.OperationalError):
        ModelRepository(path)
    assert database_snapshot(path) == before
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 5


def test_future_store_version(tmp_path: Path) -> None:
    path = tmp_path / "future.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version=7")
    with pytest.raises(ContractError, match="future"):
        ModelRepository(path)


def test_restart_immutability_and_payload_hash(model_case: ModelCase) -> None:
    c = model_case
    run = c.engine.fit_model(c.spec(), 40, 40, 40)
    artifact = c.engine.model_artifact(run.artifact_id)
    digest = hashlib.sha256(canonical_json(artifact).encode()).hexdigest()
    for operation in ("UPDATE m_artifacts SET payload=payload", "DELETE FROM m_artifacts"):
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            c.repository._connection.execute(operation)
    with ModelRepository(c.path) as reopened:
        assert reopened.get(ModelFitRun, run.fingerprint) == run
        assert (
            hashlib.sha256(
                canonical_json(reopened.get(FittedModelArtifact, run.artifact_id)).encode()
            ).hexdigest()
            == digest
        )
        reopened.audit()


@pytest.mark.parametrize(
    "kind", ("coefficient", "family", "schema", "index", "orphan", "layout", "metadata")
)
def test_corruption_fails_closed(model_case: ModelCase, kind: str) -> None:
    c = model_case
    run = c.engine.fit_model(c.spec(), 40, 40, 40)
    connection = c.repository._connection
    if kind in ("coefficient", "family", "schema"):
        trigger = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name='immutable_m_artifacts_update'"
        ).fetchone()[0]
        connection.execute("DROP TRIGGER immutable_m_artifacts_update")
        if kind == "coefficient":
            payload = json.loads(canonical_json(c.engine.model_artifact(run.artifact_id)))
            payload["artifact"]["fields"]["coefficients"][0] += 1
            serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            connection.execute(
                "UPDATE m_artifacts SET payload=? WHERE fingerprint=?",
                (serialized, run.artifact_id),
            )
        else:
            column, value = (
                ("type_name", "ModelFitRun") if kind == "family" else ("schema_version", "9.0")
            )
            connection.execute(
                f"UPDATE m_artifacts SET {column}=? WHERE fingerprint=?",
                (value, run.artifact_id),
            )
        connection.execute(trigger)
        with pytest.raises(ContractError):
            c.engine.model_artifact(run.artifact_id)
    elif kind == "index":
        trigger = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name='immutable_m_fits_update'"
        ).fetchone()[0]
        connection.execute("DROP TRIGGER immutable_m_fits_update")
        connection.execute(
            "UPDATE m_fits SET available_ns=99 WHERE fingerprint=?", (run.fingerprint,)
        )
        connection.execute(trigger)
        with pytest.raises(ContractError, match="index"):
            c.repository.get(ModelFitRun, run.fingerprint)
    elif kind == "orphan":
        fake = "afre.m_spec:1.0:" + "a" * 64
        connection.execute(
            "INSERT INTO m_specs VALUES (?, ?, ?, ?, ?)",
            (
                fake,
                "linear_regression",
                c.spec().fold_id,
                c.spec().target.fingerprint,
                c.fixture.definition.feature_set.fingerprint,
            ),
        )
        with pytest.raises(ContractError, match="orphan"):
            c.repository.audit()
    elif kind == "layout":
        connection.execute("DROP TRIGGER immutable_m_artifacts_delete")
        with pytest.raises(ContractError, match="schema"):
            ModelRepository(c.path)
    else:
        connection.execute("DROP TRIGGER immutable_metadata_update")
        connection.execute("UPDATE metadata SET value='9.9' WHERE key='model_schema'")
        with pytest.raises(ContractError, match="schema|metadata"):
            ModelRepository(c.path)


def test_consistent_fit_snapshot_and_corrected_rebuild(model_case: ModelCase) -> None:
    c = model_case
    first = c.engine.fit_model(c.spec(), 40, 40, 40)
    old = source_vintage(
        c.fixture.preprocessing.normalization.feature,
        10,
        10,
        10.0,
        entity=SECURITIES[0].instrument,
    )
    corrected = replace(old, value=999.0, clocks=clocks(10), predecessor_id=old.fingerprint)

    def insert() -> None:
        with ModelRepository(c.path) as writer, writer.transaction():
            writer.put(corrected)

    assert c.engine.fit_model(c.spec(), 40, 40, 40, snapshot_hook=insert) == first
    assert c.engine.model_artifact(first.artifact_id).fit_inputs_id == first.inputs.fingerprint
    rebuilt = DatasetEngine(c.repository).build_dataset(
        c.fixture.definition, c.fixture.requests, 100, 100
    )
    assert rebuilt.fingerprint != c.dataset.fingerprint


def test_declared_read_and_prediction_bounds(model_case: ModelCase) -> None:
    c = model_case
    run = c.engine.fit_model(c.spec(), 40, 40, 40)
    with (
        ModelRepository(c.path, ModelBounds(serialized_bytes=128)) as bounded,
        pytest.raises(ContractError, match="byte bound"),
    ):
        ModelEngine(bounded).model_artifact(run.artifact_id)
    with pytest.raises(ContractError, match="writer"):
        c.repository.put(c.spec())

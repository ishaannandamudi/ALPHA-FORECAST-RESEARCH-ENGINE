"""Additive migration, rollback, corruption, immutability and pinned read regression."""

import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

import afre.research_datasets.repository as repository_module
from afre.research_datasets import DatasetEngine, DatasetRepository, ResearchDatasetManifest
from afre.research_datasets.storage import dataset_schema
from afre.schema import ContractError
from afre.serialization import canonical_json
from afre.universe.repository import UniverseRepository
from examples.feature_store_demo import source_vintage
from examples.research_dataset_demo import populate, split_definition
from examples.universe_demo import SECURITIES
from examples.universe_demo import populate as universe_populate
from tests.research_datasets.conftest import Case


def test_additive_migration_preserves_previous_payloads_and_layout(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite"
    with UniverseRepository(path) as repository:
        fixture = universe_populate(repository)
        prior_payloads = repository._connection.execute(
            "SELECT * FROM u_artifacts ORDER BY fingerprint"
        ).fetchall()
        prior_layout = dict(
            repository._connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        )
        prior_metadata = dict(repository._connection.execute("SELECT key,value FROM metadata"))
        assert fixture.snapshot.engine_version == "0.5.0"
        historical = replace(fixture.snapshot, engine_version="0.4.0")
        with repository.transaction():
            repository.put(historical)
    with DatasetRepository(path) as repository:
        assert repository._connection.execute("PRAGMA user_version").fetchone()[0] == 5
        layout = dict(
            repository._connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        )
        assert all(layout[name] == sql for name, sql in prior_layout.items())
        assert (
            prior_metadata.items()
            <= dict(repository._connection.execute("SELECT key,value FROM metadata")).items()
        )
        current_payloads = repository._connection.execute(
            "SELECT * FROM u_artifacts ORDER BY fingerprint"
        ).fetchall()
        assert set(prior_payloads) <= set(current_payloads)
        assert canonical_json(
            repository.get(type(historical), historical.fingerprint)
        ) == canonical_json(historical)
        repository.audit()


def test_migration_failure_rolls_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "rollback.sqlite"
    with UniverseRepository(path):
        pass
    monkeypatch.setattr(
        repository_module,
        "dataset_schema",
        lambda: (*dataset_schema(), "INVALID migration statement"),
    )
    with pytest.raises(sqlite3.OperationalError):
        DatasetRepository(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 4
        assert (
            connection.execute(
                "SELECT count(*) FROM sqlite_master WHERE name LIKE 'r_%'"
            ).fetchone()[0]
            == 0
        )
    with UniverseRepository(path) as repository:
        repository.audit()


@pytest.mark.parametrize("kind", ["future", "index", "metadata", "trigger"])
def test_layout_fails_closed(tmp_path: Path, kind: str) -> None:
    path = tmp_path / "invalid.sqlite"
    with DatasetRepository(path):
        pass
    with sqlite3.connect(path) as connection:
        if kind == "future":
            connection.execute("PRAGMA user_version = 6")
        elif kind == "index":
            connection.execute("DROP INDEX r_origin_idx")
        elif kind == "trigger":
            connection.execute("DROP TRIGGER immutable_r_samples_update")
        else:
            connection.execute("DROP TRIGGER immutable_metadata_update")
            connection.execute("UPDATE metadata SET value='2.0' WHERE key='dataset_schema'")
    with pytest.raises(ContractError, match="future|corruption"):
        DatasetRepository(path)


@pytest.mark.parametrize(
    "kind",
    [
        "payload",
        "sample_index",
        "dataset_index",
        "partition_index",
        "fold_payload",
        "orphan",
        "wrong_family",
    ],
)
def test_artifact_and_index_tamper_fail_closed(case: Case, kind: str) -> None:
    split = case.engine.build_split(case.dataset.fingerprint, split_definition(case.fixture))
    connection = case.repository._connection
    if kind == "payload":
        connection.execute("DROP TRIGGER immutable_r_artifacts_update")
        connection.execute(
            "UPDATE r_artifacts SET payload='{}' WHERE fingerprint=?",
            (case.dataset.fingerprint,),
        )
    elif kind == "sample_index":
        connection.execute("DROP TRIGGER immutable_r_samples_update")
        connection.execute(
            "UPDATE r_samples SET origin_ns=999 WHERE fingerprint=?",
            (case.dataset.sample_ids[0],),
        )
    elif kind == "dataset_index":
        connection.execute("DROP TRIGGER immutable_r_dataset_samples_delete")
        connection.execute(
            "DELETE FROM r_dataset_samples WHERE dataset_id=? AND ordinal=0",
            (case.dataset.fingerprint,),
        )
    elif kind == "partition_index":
        connection.execute("DROP TRIGGER immutable_r_memberships_update")
        connection.execute(
            "UPDATE r_memberships SET partition='train' WHERE fold_id=?", (split.fold_ids[0],)
        )
    elif kind == "fold_payload":
        connection.execute("DROP TRIGGER immutable_r_artifacts_update")
        connection.execute(
            "UPDATE r_artifacts SET schema_version='2.0' WHERE fingerprint=?",
            (split.fold_ids[0],),
        )
    elif kind == "wrong_family":
        connection.execute(
            "INSERT INTO r_folds VALUES (?,'absent','absent',0,0)", (case.dataset.fingerprint,)
        )
    else:
        connection.execute("INSERT INTO r_folds VALUES ('orphan','absent','absent',0,0)")
    with pytest.raises((ContractError, KeyError)):
        case.repository.audit()


def test_immutable_and_idempotent(case: Case) -> None:
    connection = case.repository._connection
    for table in ("r_artifacts", "r_samples", "r_dataset_samples"):
        for operation in (f"UPDATE {table} SET fingerprint='changed'", f"DELETE FROM {table}"):
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                connection.execute(operation)
    with case.repository.transaction():
        assert case.repository.put(case.dataset) == case.dataset.fingerprint
    with pytest.raises(ContractError, match="writer"):
        case.repository.put(case.dataset)
    with (
        case.repository.read_snapshot(),
        pytest.raises(ContractError, match="nested"),
        case.repository.read_snapshot(),
    ):
        pass
    with pytest.raises(KeyError):
        case.repository.get(
            ResearchDatasetManifest, replace(case.dataset, constructed_ns=101).fingerprint
        )


def test_concurrent_backdated_insert_remains_outside_pinned_build(case: Case) -> None:
    feature = case.fixture.preprocessing.normalization.feature
    old = source_vintage(feature, 10, 10, 10.0, entity=SECURITIES[0].instrument)
    revision = replace(old, value=999.0, predecessor_id=old.fingerprint)

    def concurrent_write() -> None:
        with DatasetRepository(case.path) as other, other.transaction():
            other.put(revision)

    current = case.engine.build_dataset(
        case.fixture.definition, case.fixture.requests, 100, 100, concurrent_write
    )
    assert current == case.dataset
    corrected = case.engine.build_dataset(
        case.fixture.definition, case.fixture.requests, 100, 100
    )
    assert corrected.fingerprint != current.fingerprint
    frozen = canonical_json(current)
    with DatasetRepository(case.path) as reopened:
        assert (
            canonical_json(reopened.get(ResearchDatasetManifest, current.fingerprint)) == frozen
        )
        assert DatasetEngine(reopened).export_rows(
            current.fingerprint, 100
        ) == case.engine.export_rows(current.fingerprint, 100)
        reopened.audit()


def test_reversed_upstream_insertion(
    tmp_path: Path, research_baseline: tuple[Path, object, ResearchDatasetManifest]
) -> None:
    _, _, baseline = research_baseline
    with DatasetRepository(tmp_path / "reverse.sqlite") as repository:
        fixture = populate(repository, reverse=True)
        manifest = DatasetEngine(repository).build_dataset(
            fixture.definition, tuple(reversed(fixture.requests)), 100, 100
        )
        assert canonical_json(manifest) == canonical_json(baseline)

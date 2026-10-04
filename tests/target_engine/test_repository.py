import os
import socket
import sqlite3
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from afre.feature_store import FeatureStoreRepository, NormalizationSpec, NormalizationState
from afre.feature_store.normalization import NormalizationMethod
from afre.schema import ContractError
from afre.serialization import canonical_json
from afre.target_engine import (
    TargetDatasetManifest,
    TargetEngine,
    TargetRepository,
    TargetSetManifest,
    TargetVintage,
)
from afre.target_engine.repository import target_schema
from examples.feature_store_demo import SOURCE, UNIVERSE, clocks, origin, source_vintage
from examples.feature_store_demo import definition as feature_definition
from examples.feature_store_demo import populate as feature_populate
from examples.target_demo import CALENDAR_TARGET, SOURCE_MARKET, bar, definition, populate
from tests.feature_store.test_repository import corrupt
from tests.target_engine.test_builders import append, build


def test_additive_migration_preserves_all_prior_rows(tmp_path: Path) -> None:
    path = tmp_path / "upgrade.sqlite"
    with FeatureStoreRepository(path) as prior:
        feature_populate(prior)
    with sqlite3.connect(path) as connection:
        tables = tuple(
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        )
        before = {
            name: connection.execute(f"SELECT * FROM {name} ORDER BY 1").fetchall()
            for name in tables
        }
    with TargetRepository(path) as upgraded:
        assert upgraded.audit() > 0
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
        for name, rows in before.items():
            after = connection.execute(f"SELECT * FROM {name} ORDER BY 1").fetchall()
            if name == "metadata":
                assert set(rows) <= set(after)
            else:
                assert rows == after
    with pytest.raises(ContractError):
        FeatureStoreRepository(path)


def test_migration_rollback_and_future_versions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import afre.target_engine.repository as module

    path = tmp_path / "rollback.sqlite"
    FeatureStoreRepository(path).close()
    statements = target_schema()
    monkeypatch.setattr(module, "target_schema", lambda: (*statements, "INVALID SQL"))
    with pytest.raises(sqlite3.OperationalError):
        TargetRepository(path)
    with FeatureStoreRepository(path) as prior:
        assert prior.audit() == 0
        assert prior._connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert not prior._connection.execute(
            "SELECT name FROM sqlite_master WHERE name LIKE 'target_%'"
        ).fetchall()
    for version in (-1, 4, 99):
        future = tmp_path / f"future-{version}.sqlite"
        with sqlite3.connect(future) as connection:
            connection.execute(f"PRAGMA user_version = {version}")
        with pytest.raises(ContractError, match="future"):
            TargetRepository(future)


@pytest.mark.parametrize(
    "table,column,bad",
    [
        ("target_artifacts", "payload", "{}"),
        ("target_artifacts", "type_name", "Unknown"),
        ("target_artifacts", "schema_version", "2.0"),
        ("target_artifacts", "fingerprint", "afre.target_vintage:1.0:" + "0" * 64),
        ("target_vintages", "available_ns", 999),
        ("target_vintages", "origin_id", "wrong"),
        ("target_bars", "end_ns", 999),
        ("target_definitions", "name", "target.corrupt"),
        ("target_build_bars", "instrument_id", "wrong"),
        ("target_dataset_rows", "row_id", "wrong"),
    ],
)
def test_payload_fingerprint_and_index_corruption(
    tmp_path: Path, table: str, column: str, bad: object
) -> None:
    path = tmp_path / "corrupt.sqlite"
    with TargetRepository(path) as repository:
        populate(repository)
    # A fingerprint replacement across all records collides; corrupt one selected record.
    with sqlite3.connect(path) as connection:
        trigger = f"immutable_{table}_update"
        ddl = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = ?", (trigger,)
        ).fetchone()[0]
        connection.execute(f"DROP TRIGGER {trigger}")
        connection.execute(
            f"UPDATE {table} SET {column} = ? WHERE rowid = (SELECT min(rowid) FROM {table})",
            (bad,),
        )
        connection.execute(ddl)
    with TargetRepository(path) as repository, pytest.raises((ContractError, KeyError)):
        repository.audit()


@pytest.mark.parametrize("kind", ["index", "metadata", "orphan", "membership"])
def test_layout_and_orphan_integrity(tmp_path: Path, kind: str) -> None:
    path = tmp_path / "layout.sqlite"
    TargetRepository(path).close()
    if kind == "metadata":
        corrupt(path, "metadata", "value", "wrong")
    else:
        with sqlite3.connect(path) as connection:
            if kind == "index":
                connection.execute("DROP INDEX target_known_idx")
            elif kind == "orphan":
                connection.execute(
                    "INSERT INTO target_definitions VALUES ('orphan', 'target.orphan', '1')"
                )
            else:
                connection.execute(
                    "INSERT INTO target_build_bars VALUES "
                    "('orphan', 'missing-build', 'missing-bar', 'instrument', 1)"
                )
    if kind in ("orphan", "membership"):
        with TargetRepository(path) as repository, pytest.raises(ContractError, match="orphan"):
            repository.audit()
    else:
        with pytest.raises(ContractError):
            TargetRepository(path)


def test_immutability_idempotence_definition_conflict_and_calculation_tampering(
    engine: TargetEngine,
) -> None:
    append(engine, bar(1, 100.0), bar(5, 105.0))
    row = build(engine)
    with engine.repository.transaction():
        assert engine.repository.put(row) == row.fingerprint
    with (
        pytest.raises(ContractError, match="calculation/evidence"),
        engine.repository.transaction(),
    ):
        engine.repository.put(replace(row, value=999.0))
    with pytest.raises(sqlite3.IntegrityError), engine.repository.transaction():
        engine.repository.put(
            replace(row.definition, horizon=replace(row.definition.horizon, duration_ns=3))
        )
    with pytest.raises(ContractError, match="writer transaction"):
        engine.repository.put(row)
    for table in (
        "target_artifacts",
        "target_definitions",
        "target_bars",
        "target_build_bars",
        "target_vintages",
        "target_datasets",
        "target_dataset_rows",
    ):
        for statement in (
            f"DELETE FROM {table}",
            f"UPDATE {table} SET fingerprint = fingerprint",
            f"INSERT OR REPLACE INTO {table} SELECT * FROM {table}",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                engine.repository._connection.execute(statement)
    assert engine.repository.get_any(SOURCE.fingerprint) == SOURCE
    assert engine.repository.lineage(SOURCE.fingerprint) == (SOURCE,)
    with pytest.raises(KeyError):
        engine.repository.get(TargetVintage, "afre.target_vintage:1.0:" + "0" * 64)
    audit = engine.audit_target(row.fingerprint)
    append(engine, audit)
    assert row in engine.repository.lineage(audit.fingerprint)
    engine.audit()


def test_frozen_build_restart_insertion_order_and_concurrent_correction(tmp_path: Path) -> None:
    outputs = []
    for reverse in (False, True):
        path = tmp_path / f"order-{reverse}.sqlite"
        with TargetRepository(path) as repository:
            from examples.target_demo import register_sources

            register_sources(repository)
            observations = tuple(bar(n, 100.0 + n) for n in range(1, 6))
            with repository.transaction():
                for item in reversed(observations) if reverse else observations:
                    repository.put(item)
            engine = TargetEngine(repository)
            source = engine.freeze_source(SOURCE_MARKET, CALENDAR_TARGET, 7)
            dataset = engine.build_dataset(
                "frozen",
                (origin(1),),
                TargetSetManifest((definition(),)),
                source.fingerprint,
                UNIVERSE,
                clocks(7),
            )
            frozen = tuple(canonical_json(row) for row in engine.rows(dataset))
            outputs.append((canonical_json(source), canonical_json(dataset), frozen))
            with TargetRepository(path) as writer, repository.read_snapshot():
                old = repository.get_any(dataset.row_ids[0])
                with writer.transaction():
                    writer.put(
                        replace(
                            observations[-1],
                            close=120.0,
                            clocks=clocks(10),
                            predecessor_id=observations[-1].fingerprint,
                        )
                    )
                # Bypass nested facade snapshots while one pinned read is already open.
                assert canonical_json(
                    repository.get(TargetVintage, dataset.row_ids[0])
                ) == canonical_json(old)
                assert repository.bars(source, origin(1).instrument.fingerprint, 5, 5) == (
                    observations[-1],
                )
            assert tuple(canonical_json(row) for row in engine.rows(dataset)) == frozen
            new_source = engine.freeze_source(SOURCE_MARKET, CALENDAR_TARGET, 10)
            rebuilt = engine.build_dataset(
                "frozen",
                (origin(1),),
                dataset.targets,
                new_source.fingerprint,
                UNIVERSE,
                clocks(10),
            )
            assert rebuilt.fingerprint != dataset.fingerprint
            assert engine.rows(rebuilt)[0].value != engine.rows(dataset)[0].value
        with TargetRepository(path) as restarted:
            replay = TargetEngine(restarted)
            assert (
                canonical_json(restarted.get(TargetDatasetManifest, dataset.fingerprint))
                == outputs[-1][1]
            )
            assert tuple(canonical_json(row) for row in replay.rows(dataset)) == frozen
            replay.audit()
    assert outputs[0] == outputs[1]


def test_target_cannot_enter_features_dag_or_normalization(
    engine: TargetEngine, tmp_path: Path
) -> None:
    from afre.feature_store.dag import Transformation
    from examples.feature_store_demo import computation

    append(engine, bar(1, 100.0), bar(5, 105.0))
    row = build(engine)
    with FeatureStoreRepository(tmp_path / "features-only.sqlite") as feature_repo:
        for target in (row, row.definition, definition().endpoints):
            with pytest.raises(ContractError), feature_repo.transaction():
                feature_repo.put(target)
    raw = feature_definition()
    derived = feature_definition("market.derived", dependencies=(raw,))
    bad_inputs: Any = (row.definition,)
    with pytest.raises(ContractError):
        replace(computation(derived, (raw,), Transformation.IDENTITY), inputs=bad_inputs)
    spec = NormalizationSpec(raw, NormalizationMethod.NONE, "supplied-v1")
    with pytest.raises(ContractError):
        NormalizationState(spec, (row.fingerprint,), 7, 7, (), SOURCE.dataset_id)
    for identity in (row.fingerprint, row.definition.fingerprint, row.source_build_id):
        with pytest.raises(ContractError):
            replace(SOURCE, parent_source_ids=(identity,))
        with pytest.raises(ContractError):
            replace(source_vintage(raw, 1, 2), input_ids=(identity,))


@pytest.mark.parametrize("seed", ["0", "1", "42", "random"])
def test_target_hash_seeds_offline_demo(seed: str) -> None:
    # Also block DNS/sockets in the child, where pytest's fixture does not apply.
    script = """
import socket
def denied(*args, **kwargs):
    raise AssertionError('network forbidden')
for name in ('socket', 'create_connection', 'getaddrinfo', 'gethostbyname',
             'gethostbyname_ex', 'gethostbyaddr', 'socketpair'):
    setattr(socket, name, denied)
from examples.target_demo import main
main()
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=dict(os.environ, PYTHONHASHSEED=seed, PYTHONPATH="src:."),
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    assert "Byte-identical target restart replay" in result.stdout
    assert (
        "afre.target_dataset:1.0:1765c546e8e30022bc904eefe6fe08342278b7dee026391528139c4e306ec697"
        in result.stdout
    )


def test_network_is_blocked() -> None:
    for call in (lambda: socket.socket(), lambda: socket.getaddrinfo("localhost", 80)):
        with pytest.raises(AssertionError, match="network"):
            call()

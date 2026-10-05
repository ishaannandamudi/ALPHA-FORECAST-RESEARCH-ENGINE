"""Additive migration, rollback, immutable storage and fail-closed corruption."""

import shutil
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from afre.calibration import CalibrationEngine, CalibrationRepository
from afre.multihorizon import MultiHorizonBounds, MultiHorizonForecast, MultiHorizonRepository
from afre.multihorizon import repository as repository_module
from afre.multihorizon.storage import multihorizon_schema
from afre.schema import ContractError
from afre.serialization import canonical_json
from examples.calibration_demo import build_calibration_fixture
from tests.multihorizon.conftest import Case
from tests.statistical_models.test_repository import database_snapshot


@pytest.fixture(scope="module")
def legacy(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("afre8-legacy") / "old.sqlite"
    with CalibrationRepository(path) as repo:
        f = build_calibration_fixture(repo)
        CalibrationEngine(repo).fit(f.spec, f.requests, 55, 55, 55)
    return path


def test_additive_migration(tmp_path: Path, legacy: Path) -> None:
    path = tmp_path / "upgrade.sqlite"
    shutil.copyfile(legacy, path)
    before = database_snapshot(path)
    with sqlite3.connect(path) as conn:
        ddl = dict(
            conn.execute("SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")
        )
    with MultiHorizonRepository(path) as repo:
        assert repo._connection.execute("PRAGMA user_version").fetchone()[0] == 9
        repo.audit()
        after_ddl = dict(
            repo._connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        )
    after = database_snapshot(path)
    assert all(after[t] == rows for t, rows in before.items() if t != "metadata")
    assert set(before["metadata"]) < set(after["metadata"])
    assert all(after_ddl[k] == sql for k, sql in ddl.items())
    with pytest.raises(ContractError, match="future"):
        CalibrationRepository(path)


def test_migration_rollback(
    tmp_path: Path, legacy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "rollback.sqlite"
    shutil.copyfile(legacy, path)
    before = database_snapshot(path)
    monkeypatch.setattr(
        repository_module,
        "multihorizon_schema",
        lambda: (*multihorizon_schema()[:2], "invalid migration statement"),
    )
    with pytest.raises(sqlite3.OperationalError):
        MultiHorizonRepository(path)
    assert database_snapshot(path) == before
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 8


@pytest.mark.parametrize("table", ["mh_artifacts", "mh_records", "mh_targets"])
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE", "INSERT"])
def test_all_tables_immutable(case: Case, table: str, operation: str) -> None:
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
    [
        "metadata",
        "future",
        "layout",
        "hash",
        "family",
        "index",
        "extra-target",
        "missing-target",
        "orphan",
    ],
)
def test_corruption(case: Case, kind: str) -> None:
    bundle = case.fixture.bundles[0]
    if kind in ("metadata", "future", "layout"):
        case.repo.close()
        with sqlite3.connect(case.path) as conn:
            if kind == "metadata":
                conn.execute("DROP TRIGGER immutable_metadata_update")
                conn.execute(
                    "UPDATE metadata SET value='future' WHERE key='multihorizon_schema'"
                )
            elif kind == "future":
                conn.execute("PRAGMA user_version=10")
            else:
                conn.execute("DROP INDEX mh_origin_idx")
        with pytest.raises(ContractError):
            MultiHorizonRepository(case.path)
        # Fixture cleanup closes the connection again safely.
        return
    with case.repo.transaction():
        if kind in ("hash", "family"):
            case.repo._connection.execute("DROP TRIGGER immutable_mh_artifacts_update")
            column, value = (
                ("payload", canonical_json(replace(bundle, available_ns=61)))
                if kind == "hash"
                else ("type_name", "Unknown")
            )
            case.repo._connection.execute(
                f"UPDATE mh_artifacts SET {column}=? WHERE fingerprint=?",
                (value, bundle.fingerprint),
            )
        elif kind == "index":
            case.repo._connection.execute("DROP TRIGGER immutable_mh_records_update")
            case.repo._connection.execute(
                "UPDATE mh_records SET origin_ns=999 WHERE fingerprint=?", (bundle.fingerprint,)
            )
        elif kind in ("extra-target", "orphan"):
            identity = bundle.fingerprint if kind == "extra-target" else "unknown"
            case.repo._connection.execute(
                "INSERT INTO mh_targets VALUES (?, ?, ?, NULL, NULL, NULL)",
                (
                    identity,
                    case.fixture.spec.bindings[0].target_definition_id,
                    case.fixture.spec.horizon_set.horizons[0].fingerprint,
                ),
            )
        else:
            case.repo._connection.execute("DROP TRIGGER immutable_mh_targets_delete")
            case.repo._connection.execute(
                "DELETE FROM mh_targets WHERE fingerprint=?", (case.fixture.spec.fingerprint,)
            )
    with pytest.raises(ContractError):
        if kind == "missing-target":
            case.repo.get(type(case.fixture.spec), case.fixture.spec.fingerprint)
        elif kind == "orphan":
            case.repo.audit()
        else:
            case.repo.get(MultiHorizonForecast, bundle.fingerprint)


def test_roundtrip_idempotence_and_bounds(case: Case) -> None:
    bundle = case.fixture.bundles[0]
    with pytest.raises(ContractError, match="transaction"):
        case.repo.put(bundle)
    with case.repo.transaction():
        assert case.repo.put(bundle) == bundle.fingerprint
    with pytest.raises(KeyError):
        case.repo.get(MultiHorizonForecast, replace(bundle, available_ns=61).fingerprint)
    with pytest.raises(ContractError, match="unresolved"):
        case.repo.get_any(replace(bundle, available_ns=61).fingerprint)
    case.repo.multihorizon_bounds = replace(MultiHorizonBounds(), horizons=1)
    with pytest.raises(ContractError, match="bound"):
        case.repo.get(MultiHorizonForecast, bundle.fingerprint)
    case.repo.multihorizon_bounds = replace(MultiHorizonBounds(), serialized_bytes=100)
    with pytest.raises(ContractError, match="byte"):
        case.repo.get(MultiHorizonForecast, bundle.fingerprint)


def test_restart_full_lineage(case: Case) -> None:
    bundle = case.fixture.bundles[0]
    audit = case.engine.lineage_audit(bundle.fingerprint)
    frozen = canonical_json(audit)
    with MultiHorizonRepository(case.path) as restarted:
        assert restarted.get(MultiHorizonForecast, bundle.fingerprint) == bundle
        from afre.multihorizon import MultiHorizonEngine

        assert (
            canonical_json(MultiHorizonEngine(restarted).lineage_audit(bundle.fingerprint))
            == frozen
        )
        assert restarted.audit() > 0
    case.repo.multihorizon_bounds = replace(MultiHorizonBounds(), audit_nodes=5)
    with pytest.raises(ContractError, match="bound"):
        case.engine.lineage_audit(bundle.fingerprint)


def test_concurrent_correction_frozen_snapshot(case: Case) -> None:
    from afre.research_datasets.samples import ResearchSample
    from examples.calibration_demo import corrected_calibration_truth

    bundle = case.fixture.bundles[0]
    original = canonical_json(bundle)
    raw = case.fixture.deployment[1][0]
    sample = case.repo.get(ResearchSample, raw.input.sample_id or "")
    corrected = []

    def concurrent_writer() -> None:
        with MultiHorizonRepository(case.path) as writer:
            corrected.append(
                corrected_calibration_truth(writer, sample.target_id or "", 110, 10.0)
            )
        # Frozen read view must not see the concurrent insert.
        from afre.target_engine.models import TargetVintage

        with pytest.raises(KeyError):
            case.repo.get(TargetVintage, corrected[0])

    result = case.engine.build_bundle(
        bundle.fit_run_id, bundle.origin, bundle.entries, 60, snapshot_hook=concurrent_writer
    )
    assert canonical_json(result) == original
    assert corrected
    # A revised upstream point-model identity gives a revised aggregate identity.
    from afre.statistical_models import ModelEngine
    from afre.statistical_models.artifacts import PointForecast
    from afre.statistical_models.definitions import BaselineModelSpec

    binding = case.fixture.spec.bindings[1]
    base = replace(case.repo.get(BaselineModelSpec, binding.point_spec_id), random_seed=1)
    point_run = ModelEngine(case.repo).fit_model(base, 40, 40, 40)
    old_point = case.repo.get(PointForecast, bundle.entries[1].point_forecast_id or "")
    new_point = ModelEngine(case.repo).predict(point_run.artifact_id, old_point.input, 60)
    spec = replace(
        case.fixture.spec,
        bindings=tuple(
            replace(
                b,
                probability_spec_id=None,
                probability_model_id=None,
                calibration_spec_id=None,
                calibration_state_id=None,
                point_spec_id=base.fingerprint if h else b.point_spec_id,
                point_model_id=point_run.artifact_id if h else b.point_model_id,
            )
            for h, b in enumerate(case.fixture.spec.bindings)
        ),
    )
    run = case.engine.fit(spec, 55, 55, 55)
    changed = case.engine.build_bundle(
        run.fingerprint,
        bundle.origin,
        (
            replace(
                bundle.entries[0], probability_forecast_id=None, calibrated_forecast_id=None
            ),
            replace(
                bundle.entries[1],
                point_forecast_id=new_point.fingerprint,
                probability_forecast_id=None,
                calibrated_forecast_id=None,
            ),
        ),
        60,
    )
    assert changed.fingerprint != bundle.fingerprint
    assert canonical_json(case.repo.get(MultiHorizonForecast, bundle.fingerprint)) == original


@pytest.mark.parametrize("table", ["m_fits", "p_fits", "c_fits"])
def test_composition_requires_completed_fit(case: Case, table: str) -> None:
    with case.repo.transaction():
        case.repo._connection.execute(f"DROP TRIGGER immutable_{table}_delete")
        case.repo._connection.execute(f"DELETE FROM {table}")
    with pytest.raises(ContractError, match="completed fit"):
        case.engine.fit(case.fixture.spec, 55, 55, 55)

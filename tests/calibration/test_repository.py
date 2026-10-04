"""Transactional upgrade/publication, immutable evidence, corruption and snapshots."""

import json
import shutil
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from afre.calibration import (
    CalibrationBounds,
    CalibrationDriftSpec,
    CalibrationFitRun,
    CalibrationMethod,
    CalibrationObservationSet,
    CalibrationRepository,
    CalibrationState,
    DriftMetric,
    ProbabilityMapping,
)
from afre.calibration.storage import TABLES, calibration_schema
from afre.probabilistic import ProbabilisticRepository
from afre.schema import Artifact, ContractError
from afre.serialization import canonical_json
from examples.calibration_demo import corrected_calibration_truth as corrected_truth
from examples.research_dataset_demo import populate
from tests.calibration.conftest import CalibrationCase
from tests.statistical_models.test_repository import database_snapshot


@pytest.fixture(scope="module")
def old_store(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("calibration-legacy") / "old.sqlite"
    with ProbabilisticRepository(path) as repo:
        populate(repo)
    return path


def test_migration_preserves_rows_metadata_and_DDL(tmp_path: Path, old_store: Path) -> None:
    path = tmp_path / "upgrade.sqlite"
    shutil.copyfile(old_store, path)
    before = database_snapshot(path)
    with sqlite3.connect(path) as connection:
        old_sql = dict(
            connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        )
    with CalibrationRepository(path) as repo:
        assert repo._connection.execute("PRAGMA user_version").fetchone()[0] == 8
        assert repo.audit() > 100
    after = database_snapshot(path)
    assert all(after[t] == rows for t, rows in before.items() if t != "metadata")
    assert set(after["metadata"]) - set(before["metadata"]) == {
        ("calibration_store_schema_version", "1.7"),
        ("calibration_schema", "1.0"),
        ("calibration_engine_version", "0.8.0"),
    }
    with sqlite3.connect(path) as connection:
        new_sql = dict(
            connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        )
    assert all(new_sql[k] == v for k, v in old_sql.items())


def test_upgrade_rollback(
    tmp_path: Path, old_store: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "rollback.sqlite"
    shutil.copyfile(old_store, path)
    before = database_snapshot(path)
    monkeypatch.setattr(
        "afre.calibration.repository.calibration_schema",
        lambda: (*calibration_schema()[:2], "INVALID MIGRATION"),
    )
    with pytest.raises(sqlite3.OperationalError):
        CalibrationRepository(path)
    assert database_snapshot(path) == before
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 7
        assert not tuple(
            connection.execute("SELECT name FROM sqlite_master WHERE name LIKE 'c_%'")
        )


@pytest.mark.parametrize("version", [9, 99])
def test_future_store_rejected(tmp_path: Path, version: int) -> None:
    path = tmp_path / "future.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute(f"PRAGMA user_version={version}")
    with pytest.raises(ContractError, match="future"):
        CalibrationRepository(path)


def test_fit_rollback_retry_and_idempotence(
    calibration_case: CalibrationCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = calibration_case
    before = database_snapshot(c.path)
    original = c.repo.put

    def fail(value: Artifact) -> str:
        if isinstance(value, CalibrationFitRun):
            raise RuntimeError("injected publication failure")
        return original(value)

    with monkeypatch.context() as patch:
        patch.setattr(c.repo, "put", fail)
        with pytest.raises(RuntimeError, match="publication"):
            c.fit()
    assert database_snapshot(c.path) == before
    run = c.fit()
    assert c.fit() == run
    with pytest.raises(ContractError, match="transaction"):
        c.repo.put(run)
    with c.repo.transaction():
        assert c.repo.put(run) == run.fingerprint
    with pytest.raises(ContractError, match="not persistable"), c.repo.transaction():
        c.repo.put(Artifact())


@pytest.mark.parametrize("table", TABLES)
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE", "INSERT"])
def test_immutable_tables(
    calibration_case: CalibrationCase, table: str, operation: str
) -> None:
    c = calibration_case
    method = (
        CalibrationMethod.QUANTILE_OFFSET
        if table == "c_offsets"
        else CalibrationMethod.ISOTONIC_PROBABILITY
    )
    run = c.fit(method)
    forecasts = c.engine.apply_batch(
        run.state_id, tuple(p.fingerprint for p in c.fixture.deployment_raw)
    )
    ev = c.engine.evaluate(tuple(f.fingerprint for f in forecasts), 75, 75)
    c.engine.diagnose_drift(CalibrationDriftSpec(1, 1, DriftMetric.ECE, 0.5), (ev.fingerprint,))
    sql = (
        f"UPDATE {table} SET fingerprint=fingerprint"
        if operation == "UPDATE"
        else f"DELETE FROM {table}"
        if operation == "DELETE"
        else f"INSERT INTO {table} SELECT * FROM {table} LIMIT 1"
    )
    with pytest.raises(sqlite3.IntegrityError, match="immutable"), c.repo.transaction():
        c.repo._connection.execute(sql)


@pytest.mark.parametrize(
    "kind", ["payload", "class", "schema", "index", "orphan", "unknown-class"]
)
def test_corruption_fails_closed(calibration_case: CalibrationCase, kind: str) -> None:
    c = calibration_case
    run = c.fit(CalibrationMethod.ISOTONIC_PROBABILITY)
    state = c.repo.get(CalibrationState, run.state_id)
    identity = state.mapping_ids[0]
    with c.repo.transaction():
        c.repo._connection.execute("DROP TRIGGER immutable_c_artifacts_update")
        c.repo._connection.execute("DROP TRIGGER immutable_c_mappings_update")
        if kind == "payload":
            payload = json.loads(canonical_json(c.repo.get(ProbabilityMapping, identity)))
            payload["artifact"]["fields"]["blocks"][0]["fields"]["probability"] = 0.123
            c.repo._connection.execute(
                "UPDATE c_artifacts SET payload=? WHERE fingerprint=?",
                (json.dumps(payload, sort_keys=True, separators=(",", ":")), identity),
            )
        elif kind == "class":
            c.repo._connection.execute(
                "UPDATE c_artifacts SET type_name='CalibrationState' WHERE fingerprint=?",
                (identity,),
            )
        elif kind == "schema":
            c.repo._connection.execute(
                "UPDATE c_artifacts SET schema_version='99' WHERE fingerprint=?", (identity,)
            )
        elif kind == "index":
            c.repo._connection.execute(
                "UPDATE c_mappings SET event_id='altered' WHERE fingerprint=?", (identity,)
            )
        elif kind == "orphan":
            c.repo._connection.execute("INSERT INTO c_mappings VALUES ('orphan','bad','bad')")
        else:
            c.repo._connection.execute(
                "UPDATE c_artifacts SET type_name='ExecutableMapping' WHERE fingerprint=?",
                (identity,),
            )
    with pytest.raises(ContractError):
        if kind in ("orphan", "unknown-class"):
            c.repo.audit()
        else:
            c.repo.get(ProbabilityMapping, identity)


def test_forged_state_mapping_scores_and_evaluation_rejected(
    calibration_case: CalibrationCase,
) -> None:
    c = calibration_case
    run = c.fit(CalibrationMethod.ISOTONIC_PROBABILITY)
    state = c.repo.get(CalibrationState, run.state_id)
    mapping = c.repo.get(ProbabilityMapping, state.mapping_ids[0])
    first = mapping.blocks[0]
    changed = replace(
        mapping, blocks=(replace(first, successes=0, probability=0.0), *mapping.blocks[1:])
    )
    with pytest.raises(ContractError, match="map contamination"), c.repo.transaction():
        c.repo.put(changed)
    with pytest.raises(ContractError, match="state contamination"), c.repo.transaction():
        c.repo.put(replace(state, mapping_ids=()))
    with pytest.raises(ContractError, match="fit-input contamination"), c.repo.transaction():
        c.repo.put(replace(run.inputs, sample_ids=run.inputs.sample_ids[:-1]))
    fs = c.engine.apply_batch(
        run.state_id, tuple(p.fingerprint for p in c.fixture.deployment_raw)
    )
    with pytest.raises(ContractError, match="forecast mismatch"), c.repo.transaction():
        c.repo.put(replace(fs[0], full_distribution_preserved=True))
    ev = c.engine.evaluate(tuple(f.fingerprint for f in fs), 75, 75)
    with pytest.raises(ContractError, match="evaluation contamination"), c.repo.transaction():
        c.repo.put(replace(ev, pairs=()))
    comparison = c.engine.compare(ev.raw_evaluation_id, ev.fingerprint)
    with pytest.raises(ContractError, match="comparison contamination"), c.repo.transaction():
        c.repo.put(replace(comparison, interval_width_delta=999.0))
    drift = c.engine.diagnose_drift(
        CalibrationDriftSpec(1, 1, DriftMetric.ECE, 0.5), (ev.fingerprint,)
    )
    with (
        pytest.raises(ContractError, match="drift contamination|inconsistent drift history"),
        c.repo.transaction(),
    ):
        c.repo.put(replace(drift, windows=()))


def test_snapshot_concurrent_later_truth_and_restart(calibration_case: CalibrationCase) -> None:
    c = calibration_case
    base = c.fit()
    frozen = canonical_json(c.repo.get(CalibrationState, base.state_id))

    def later() -> None:
        with type(c.repo)(c.path) as writer:
            corrected_truth(writer, c.fixture.requests[0].target_id)

    spec = replace(c.fixture.spec, random_seed=42)
    changed = c.engine.fit(spec, c.fixture.requests, 55, 55, 55, snapshot_hook=later)
    obs = c.repo.get(CalibrationObservationSet, changed.inputs.observations_id)
    assert tuple(r.target_id for r in obs.rows) == tuple(
        r.target_id
        for r in c.repo.get(CalibrationObservationSet, base.inputs.observations_id).rows
    )
    assert canonical_json(c.repo.get(CalibrationState, base.state_id)) == frozen
    with CalibrationRepository(c.path) as restarted:
        assert canonical_json(restarted.get(CalibrationState, base.state_id)) == frozen
        assert restarted.audit() > 100


@pytest.mark.parametrize(
    ("field", "limit"),
    [
        ("observations", 1),
        ("bins", 1),
        ("quantiles", 1),
        ("events", 1),
        ("blocks", 1),
        ("conformal_scores", 1),
        ("rolling_window", 1),
        ("forecasts", 1),
        ("work_cells", 1),
        ("serialized_bytes", 100),
    ],
)
def test_bounds_fail_explicitly(
    calibration_case: CalibrationCase, field: str, limit: int
) -> None:
    c = calibration_case
    c.repo.calibration_bounds = replace(CalibrationBounds(), **{field: limit})
    method = (
        CalibrationMethod.ROLLING_CONFORMAL
        if field in ("conformal_scores", "rolling_window")
        else CalibrationMethod.ISOTONIC_PROBABILITY
    )
    if field == "blocks":
        from afre.calibration.bounds import check_bounds
        from afre.calibration.isotonic import pav

        event = c.fixture.spec.events.requests[0]
        pairs = (
            (0.1, False, "afre.c_observation:1.0:" + "0" * 64),
            (0.9, True, "afre.c_observation:1.0:" + "1" * 64),
        )
        mapping = ProbabilityMapping(
            c.fixture.spec.fingerprint,
            "afre.c_observations:1.0:" + "0" * 64,
            event,
            CalibrationMethod.ISOTONIC_PROBABILITY,
            pav(pairs),
        )
        with pytest.raises(ContractError, match="block/bin/evidence bound"):
            check_bounds(mapping, replace(CalibrationBounds(), blocks=1))
        return
    if field == "events":
        from afre.calibration.bounds import check_bounds

        run = c.fit()
        state = c.repo.get(CalibrationState, run.state_id)
        with pytest.raises(ContractError, match="state evidence bound"):
            check_bounds(
                replace(
                    state, mapping_ids=tuple(f"afre.c_mapping:1.0:{i:064x}" for i in range(2))
                ),
                replace(CalibrationBounds(), events=1),
            )
        return
    with pytest.raises(ContractError):
        run = c.fit(method)
        if field == "forecasts":
            c.engine.apply_batch(
                run.state_id, tuple(p.fingerprint for p in c.fixture.deployment_raw)
            )


def test_audit_bounds_and_invalid_roots(calibration_case: CalibrationCase) -> None:
    c = calibration_case
    run = c.fit()
    with pytest.raises(ContractError, match="root"):
        c.engine.calibration_audit(c.fixture.raw_run.artifact_id)
    c.repo.calibration_bounds = replace(CalibrationBounds(), audit_nodes=1)
    with pytest.raises(ContractError, match="depth/node"):
        c.engine.calibration_audit(run.state_id)
    c.repo.calibration_bounds = replace(CalibrationBounds(), audit_depth=1)
    with pytest.raises(ContractError, match="depth/node"):
        c.engine.calibration_audit(run.state_id)

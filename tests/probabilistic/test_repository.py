"""Additive store migration, immutable publication, tamper rejection and pinned snapshots."""

import json
import shutil
import sqlite3
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from afre.probabilistic import (
    ProbabilisticBounds,
    ProbabilisticEngine,
    ProbabilisticFitRun,
    ProbabilisticRepository,
    TrainingDistribution,
    TrainingObservations,
)
from afre.probabilistic.storage import probabilistic_schema
from afre.research_datasets import DatasetEngine
from afre.schema import Artifact, ContractError
from afre.serialization import canonical_json
from afre.statistical_models import (
    BaselineModelSpec,
    ModelEngine,
    ModelRepository,
    PredictionScope,
)
from examples.feature_store_demo import clocks, source_vintage
from examples.research_dataset_demo import populate, split_definition
from examples.statistical_baselines_demo import baseline_spec
from examples.universe_demo import SECURITIES
from tests.probabilistic.conftest import ProbabilityCase
from tests.statistical_models.test_repository import database_snapshot


@pytest.fixture(scope="module")
def legacy_probability_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("probability-legacy") / "old.sqlite"
    with ModelRepository(path) as repo:
        populate(repo)
    return path


def test_additive_migration_preserves_every_prior_row_and_sql(
    tmp_path: Path, legacy_probability_path: Path
) -> None:
    path = tmp_path / "upgrade.sqlite"
    shutil.copyfile(legacy_probability_path, path)
    before = database_snapshot(path)
    with sqlite3.connect(path) as conn:
        old_sql = dict(
            conn.execute("SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")
        )
    with ProbabilisticRepository(path) as repo:
        assert repo._connection.execute("PRAGMA user_version").fetchone()[0] == 7
        assert repo.audit() > 100
    after = database_snapshot(path)
    assert all(after[t] == rows for t, rows in before.items() if t != "metadata")
    assert set(after["metadata"]) - set(before["metadata"]) == {
        ("probabilistic_store_schema_version", "1.6"),
        ("probabilistic_schema", "1.0"),
        ("probabilistic_engine_version", "0.7.0"),
    }
    with sqlite3.connect(path) as conn:
        sql = dict(
            conn.execute("SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")
        )
    assert all(sql[k] == v for k, v in old_sql.items())


def test_migration_rollback(
    tmp_path: Path, legacy_probability_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "rollback.sqlite"
    shutil.copyfile(legacy_probability_path, path)
    before = database_snapshot(path)
    monkeypatch.setattr(
        "afre.probabilistic.repository.probabilistic_schema",
        lambda: (*probabilistic_schema()[:2], "INVALID MIGRATION"),
    )
    with pytest.raises(sqlite3.OperationalError):
        ProbabilisticRepository(path)
    assert database_snapshot(path) == before
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 6
        assert not tuple(conn.execute("SELECT name FROM sqlite_master WHERE name LIKE 'p_%'"))


@pytest.mark.parametrize("version", [8, 99])
def test_future_version(tmp_path: Path, version: int) -> None:
    path = tmp_path / "future.sqlite"
    with sqlite3.connect(path) as conn:
        conn.execute(f"PRAGMA user_version={version}")
    with pytest.raises(ContractError, match="future"):
        ProbabilisticRepository(path)


def test_atomic_fit_rollback_and_retry(
    probability_case: ProbabilityCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = probability_case
    before = database_snapshot(c.path)
    original = c.repo.put

    def failed(value: Artifact) -> str:
        if isinstance(value, ProbabilisticFitRun):
            raise RuntimeError("injected publication failure")
        return original(value)

    with monkeypatch.context() as patch:
        patch.setattr(c.repo, "put", failed)
        with pytest.raises(RuntimeError, match="publication"):
            c.fit()
    assert database_snapshot(c.path) == before
    run = c.fit()
    assert c.fit() == run
    with pytest.raises(ContractError, match="writer"):
        c.repo.put(c.residual_spec)
    with c.repo.transaction():
        assert c.repo.put(run) == run.fingerprint


@pytest.mark.parametrize(
    "table", ["p_artifacts", "p_specs", "p_fits", "p_forecasts", "p_evaluations"]
)
@pytest.mark.parametrize("operation", ["update", "delete", "duplicate"])
def test_immutable_probability_tables(
    probability_case: ProbabilityCase, table: str, operation: str
) -> None:
    c = probability_case
    run = c.fit()
    ids = c.forecast_ids(run)
    c.engine.evaluate(ids, 100, 100)
    statements = {
        "update": f"UPDATE {table} SET fingerprint=fingerprint",
        "delete": f"DELETE FROM {table}",
        "duplicate": f"INSERT INTO {table} SELECT * FROM {table} LIMIT 1",
    }
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        c.repo._connection.execute(statements[operation])


@pytest.mark.parametrize(
    "kind", ["parameters", "family", "schema", "index", "orphan", "layout", "metadata"]
)
def test_corruption_closed(probability_case: ProbabilityCase, kind: str) -> None:
    c = probability_case
    run = c.fit()
    conn = c.repo._connection
    if kind in ("parameters", "family", "schema"):
        trigger = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name='immutable_p_artifacts_update'"
        ).fetchone()[0]
        conn.execute("DROP TRIGGER immutable_p_artifacts_update")
        if kind == "parameters":
            payload = json.loads(canonical_json(c.engine.model_artifact(run.artifact_id)))
            payload["artifact"]["fields"]["scale"] += 1
            conn.execute(
                "UPDATE p_artifacts SET payload=? WHERE fingerprint=?",
                (json.dumps(payload, sort_keys=True, separators=(",", ":")), run.artifact_id),
            )
        else:
            column, value = (
                ("type_name", "ProbabilisticFitRun")
                if kind == "family"
                else ("schema_version", "9.0")
            )
            conn.execute(
                f"UPDATE p_artifacts SET {column}=? WHERE fingerprint=?",
                (value, run.artifact_id),
            )
        conn.execute(trigger)
        with pytest.raises(ContractError):
            c.engine.model_artifact(run.artifact_id)
    elif kind == "index":
        trigger = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name='immutable_p_fits_update'"
        ).fetchone()[0]
        conn.execute("DROP TRIGGER immutable_p_fits_update")
        conn.execute(
            "UPDATE p_fits SET available_ns=99 WHERE fingerprint=?", (run.fingerprint,)
        )
        conn.execute(trigger)
        with pytest.raises(ContractError, match="index"):
            c.repo.get(ProbabilisticFitRun, run.fingerprint)
    elif kind == "orphan":
        conn.execute(
            "INSERT INTO p_specs VALUES (?,?,?,?,?)",
            (
                "afre.p_spec:1.0:" + "a" * 64,
                c.residual_spec.point_model_id,
                "empirical_residual",
                c.residual_spec.fold_id,
                c.residual_spec.target.fingerprint,
            ),
        )
        with pytest.raises(ContractError, match="orphan"):
            c.repo.audit()
    elif kind == "layout":
        conn.execute("DROP TRIGGER immutable_p_artifacts_delete")
        with pytest.raises(ContractError, match="schema"):
            ProbabilisticRepository(c.path)
    else:
        trigger = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name='immutable_metadata_update'"
        ).fetchone()[0]
        conn.execute("DROP TRIGGER immutable_metadata_update")
        conn.execute("UPDATE metadata SET value='9.0' WHERE key='probabilistic_schema'")
        conn.execute(trigger)
        with pytest.raises(ContractError, match="metadata"):
            ProbabilisticRepository(c.path)


def test_semantic_forgeries_cannot_publish(probability_case: ProbabilityCase) -> None:
    c = probability_case
    run = c.fit()
    state = c.repo.get(TrainingDistribution, run.distribution_id)
    obs = c.repo.get(TrainingObservations, run.inputs.observations_id)
    model = c.engine.model_artifact(run.artifact_id)
    forecasts = c.forecast_ids(run)
    prediction = c.repo.get_any(forecasts[0])
    evaluation = c.engine.evaluate(forecasts, 100, 100)
    for value in (
        replace(obs, rows=(replace(obs.rows[0], value=999.0), *obs.rows[1:])),
        replace(state, values=(999.0, *state.values[1:])),
        replace(state, available_ns=39),
        replace(run.inputs, train_sample_ids=run.inputs.train_sample_ids[:-1]),
        replace(model, location_offset=999.0),
        replace(run, distribution_id="afre.p_training_distribution:1.0:" + "a" * 64),
        replace(
            evaluation, pairs=(replace(evaluation.pairs[0], truth=999.0), *evaluation.pairs[1:])
        ),
    ):
        with c.repo.transaction(), pytest.raises((ContractError, KeyError)):
            c.repo.put(value)
    from afre.probabilistic import ProbabilisticForecast

    assert isinstance(prediction, ProbabilisticForecast)
    with c.repo.transaction(), pytest.raises(ContractError, match="replay"):
        c.repo.put(replace(prediction, median_value=999.0))
    audit = c.engine.forecast_audit(forecasts[0])
    with c.repo.transaction(), pytest.raises(ContractError, match="evidence"):
        c.repo.put(replace(audit, checks=("forged",)))


def test_pinned_concurrency_and_corrected_new_identity(
    probability_case: ProbabilityCase,
) -> None:
    c = probability_case
    old_run = c.fit()
    frozen = canonical_json(c.engine.model_artifact(old_run.artifact_id))
    vintage = source_vintage(
        c.fixture.preprocessing.normalization.feature,
        10,
        10,
        10.0,
        entity=SECURITIES[0].instrument,
    )
    correction = replace(
        vintage, value=999.0, clocks=clocks(10), predecessor_id=vintage.fingerprint
    )
    later_models = []

    def concurrent_write() -> None:
        with ProbabilisticRepository(c.path) as writer:
            with writer.transaction():
                writer.put(correction)
            research = DatasetEngine(writer)
            dataset = research.build_dataset(c.fixture.definition, c.fixture.requests, 100, 100)
            split = research.build_split(dataset.fingerprint, split_definition(c.fixture))
            state = research.fit_preprocessing(split.fold_ids[0], c.fixture.preprocessing)
            from afre.statistical_models import ModelFamily

            run = ModelEngine(writer).fit_model(
                baseline_spec(c.fixture, split, state, ModelFamily.RIDGE_REGRESSION), 40, 40, 40
            )
            later_models.append(run)

    assert (
        c.engine.fit_model(c.residual_spec, 40, 40, 40, snapshot_hook=concurrent_write)
        == old_run
    )
    new_base = later_models[0]
    bs = c.repo.get(
        BaselineModelSpec, ModelEngine(c.repo).model_artifact(new_base.artifact_id).spec_id
    )
    new = c.fit(
        replace(c.residual_spec, point_model_id=new_base.artifact_id, fold_id=bs.fold_id)
    )
    assert new.artifact_id != old_run.artifact_id
    assert canonical_json(c.engine.model_artifact(old_run.artifact_id)) == frozen
    with ProbabilisticRepository(c.path) as reopened:
        assert (
            canonical_json(ProbabilisticEngine(reopened).model_artifact(old_run.artifact_id))
            == frozen
        )
        assert reopened.get(ProbabilisticFitRun, new.fingerprint) == new
        reopened.audit()


def test_all_resource_limits(probability_case: ProbabilityCase) -> None:
    c = probability_case
    run = c.fit()
    ids = c.forecast_ids(run)
    bounds = c.repo.probabilistic_bounds
    cases: list[tuple[ProbabilisticBounds, Callable[[], object]]] = [
        (replace(bounds, observations=1), lambda: c.fit()),
        (replace(bounds, quantiles=1), lambda: c.fit()),
        (replace(bounds, thresholds=1), lambda: c.fit()),
        (
            replace(bounds, serialized_bytes=128),
            lambda: c.engine.model_artifact(run.artifact_id),
        ),
        (replace(bounds, forecasts=1), lambda: c.forecast_ids(run)),
        (replace(bounds, work_cells=1), lambda: c.forecast_ids(run)),
        (replace(bounds, work_cells=1), lambda: c.engine.evaluate(ids, 100, 100)),
        (replace(bounds, audit_nodes=1), lambda: c.engine.model_audit(run.artifact_id)),
        (replace(bounds, audit_depth=1), lambda: c.engine.model_audit(run.artifact_id)),
        (
            replace(bounds, serialized_bytes=20000),
            lambda: c.engine.model_audit(run.artifact_id),
        ),
    ]
    for limit, call in cases:
        c.repo.probabilistic_bounds = limit
        with pytest.raises(ContractError, match="bound"):
            call()
    c.repo.probabilistic_bounds = replace(bounds, evaluations=1)
    first = c.engine.evaluate(ids, 100, 100)
    assert c.engine.evaluate(ids, 100, 100) == first
    with pytest.raises(ContractError, match="result bound"):
        c.engine.evaluate(ids, 99, 100)
    c.fit(replace(c.residual_spec, random_seed=1))
    with pytest.raises(ContractError, match="history bound"):
        c.engine.model_history(c.residual_spec.fold_id)
    c.repo.probabilistic_bounds = bounds
    with pytest.raises(ContractError, match="root"):
        c.engine.model_audit(c.residual_spec.point_model_id)
    with pytest.raises(ContractError):
        c.engine.predict_batch(run.artifact_id, ())
    with pytest.raises(ContractError):
        c.engine.predict_samples(
            run.artifact_id,
            (),
            PredictionScope.VALIDATION,
        )

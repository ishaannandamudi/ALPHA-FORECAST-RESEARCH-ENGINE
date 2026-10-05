"""Additive migration, immutable bytes, hostile data and bounded replay."""

import shutil
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from afre.cross_sectional import CrossSectionRepository
from afre.event_conditioned import (
    EventBounds,
    EventConditionedForecast,
    EventReference,
    EventRepository,
)
from afre.event_conditioned import repository as repository_module
from afre.event_conditioned.artifacts import EventConditionedObservation, EventMatchSet
from afre.event_conditioned.storage import event_schema
from afre.schema import Artifact, ContractError
from afre.serialization import canonical_json
from examples.cross_sectional_demo import cross_fixture
from tests.event_conditioned.conftest import Case
from tests.event_conditioned.test_models import first
from tests.statistical_models.test_repository import database_snapshot


@pytest.fixture(scope="module")
def legacy(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("event-legacy") / "legacy.sqlite"
    with CrossSectionRepository(path) as repo:
        cross_fixture(repo)
    return path


def test_additive_ten_to_eleven(tmp_path: Path, legacy: Path) -> None:
    path = tmp_path / "upgrade.sqlite"
    shutil.copyfile(legacy, path)
    before = database_snapshot(path)
    with sqlite3.connect(path) as conn:
        ddl = dict(
            conn.execute("SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")
        )
    with EventRepository(path) as repo:
        assert repo._connection.execute("PRAGMA user_version").fetchone()[0] == 11
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
        CrossSectionRepository(path)


def test_migration_rollback(
    tmp_path: Path, legacy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "rollback.sqlite"
    shutil.copyfile(legacy, path)
    before = database_snapshot(path)
    monkeypatch.setattr(
        repository_module,
        "event_schema",
        lambda: (*event_schema()[:2], "invalid migration SQL"),
    )
    with pytest.raises(sqlite3.OperationalError):
        EventRepository(path)
    assert database_snapshot(path) == before
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 10


@pytest.mark.parametrize("table", ["ec_artifacts", "ec_records"])
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE", "INSERT"])
def test_immutable_tables(case: Case, table: str, operation: str) -> None:
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
    ["future", "metadata", "layout", "hash", "family", "schema", "index", "orphan", "missing"],
)
def test_corruption_fail_closed(case: Case, kind: str) -> None:
    identity = first(case).fingerprint
    if kind in ("future", "metadata", "layout"):
        case.repo.close()
        with sqlite3.connect(case.path) as conn:
            if kind == "future":
                conn.execute("PRAGMA user_version=12")
            elif kind == "metadata":
                conn.execute("DROP TRIGGER immutable_metadata_update")
                conn.execute(
                    "UPDATE metadata SET value='future' WHERE key='event_conditioned_schema'"
                )
            else:
                conn.execute("DROP INDEX ec_event_idx")
        with pytest.raises(ContractError):
            EventRepository(case.path)
        return
    with case.repo.transaction():
        if kind in ("hash", "family", "schema"):
            case.repo._connection.execute("DROP TRIGGER immutable_ec_artifacts_update")
            column, value = (
                ("payload", "{}")
                if kind == "hash"
                else ("type_name", "FutureClass")
                if kind == "family"
                else ("schema_version", "2.0")
            )
            case.repo._connection.execute(
                f"UPDATE ec_artifacts SET {column}=? WHERE fingerprint=?", (value, identity)
            )
        elif kind == "index":
            case.repo._connection.execute("DROP TRIGGER immutable_ec_records_update")
            case.repo._connection.execute(
                "UPDATE ec_records SET available_ns=0 WHERE fingerprint=?", (identity,)
            )
        elif kind == "missing":
            case.repo._connection.execute("DROP TRIGGER immutable_ec_records_delete")
            case.repo._connection.execute(
                "DELETE FROM ec_records WHERE fingerprint=?", (identity,)
            )
        else:
            columns = case.repo._connection.execute("PRAGMA table_info(ec_records)").fetchall()
            values: tuple[object, ...] = (
                "orphan",
                "EventReference",
                *(None for _ in columns[2:]),
            )
            case.repo._connection.execute(
                "INSERT INTO ec_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", values
            )
    with pytest.raises(ContractError):
        case.repo.audit() if kind == "orphan" else case.repo.get(
            EventConditionedForecast, identity
        )


@pytest.mark.parametrize(
    "kind",
    ["model", "observation", "overlap", "reactions", "forecast", "evaluation", "calibration"],
)
def test_semantic_tampering_rejected(case: Case, kind: str) -> None:
    p = first(case)
    o = case.repo.get(EventConditionedObservation, p.observation_id)
    value: Artifact
    if kind == "model":
        model = case.fixture.model
        value = replace(
            model, class_values=tuple((c, v + 1, n) for c, v, n in model.class_values)
        )
    elif kind == "observation":
        value = replace(o, distance=99)
    elif kind == "overlap":
        value = replace(case.repo.get(EventMatchSet, o.matches_id), selected_ids=())
    elif kind == "reactions":
        value = replace(p, reaction_ids=(case.fixture.upstream.sources[0][1],))
    elif kind == "forecast":
        value = replace(p, value=p.value + 1, shift=p.shift + 1)
    elif kind == "calibration":
        value = replace(case.engine.assess_calibration(p.fingerprint, (), 100), reason="forged")
    else:
        value = replace(case.engine.evaluate(case.fixture.forecast_ids, 100, 100), pairs=())
    with case.repo.transaction(), pytest.raises(ContractError):
        case.repo.put(value)


@pytest.mark.parametrize(
    "kind",
    [
        "events",
        "matches",
        "samples",
        "reactions",
        "groups",
        "nodes",
        "depth",
        "bytes",
        "stored",
        "spec",
    ],
)
def test_explicit_bounds(case: Case, kind: str) -> None:
    from afre.event_conditioned import EventModelFamily, EventOverlapPolicy
    from afre.research_datasets.samples import ResearchSample
    from examples.event_conditioned_demo import event

    p = first(case)
    o = case.repo.get(EventConditionedObservation, p.observation_id)
    sample = case.repo.get(ResearchSample, o.sample_id)
    other = case.engine.publish_event(event(sample, "second"))
    b = (
        "matches_per_sample"
        if kind == "matches"
        else "reaction_features"
        if kind in ("reactions", "spec")
        else "audit_nodes"
        if kind == "nodes"
        else "audit_depth"
        if kind == "depth"
        else "serialized_bytes"
        if kind == "bytes"
        else "events"
        if kind == "stored"
        else kind
    )
    case.repo.event_bounds = EventBounds(**{b: 1})
    with pytest.raises(ContractError, match="bound"):
        if kind in ("events", "matches"):
            case.engine.observe(
                replace(case.fixture.spec, overlap=EventOverlapPolicy.ALL_EVENTS_SEPARATE),
                o.sample_id,
                (o.event_id or "", other),
            )
        elif kind == "samples":
            case.engine.fit(
                case.fixture.spec, case.fixture.training_observation_ids, 40, 40, 40
            )
        elif kind == "reactions":
            case.engine.observe(
                case.fixture.spec, o.sample_id, (), tuple("x" + str(i) for i in range(129))
            )
        elif kind == "groups":
            case.engine.evaluate(case.fixture.forecast_ids, 100, 100)
        elif kind in ("nodes", "depth"):
            case.engine.audit_lineage(p.fingerprint)
        elif kind == "stored":
            case.engine.publish_event(event(sample, "overflow"))
        elif kind == "spec":
            score = case.fixture.upstream.spec.score
            spec = replace(
                case.fixture.spec,
                family=EventModelFamily.EVENT_FEATURE_LINEAR,
                reaction_specs=(score, replace(score, signal_name="another")),
            )
            case.engine.observe(spec, o.sample_id, ())
        else:
            case.engine.observe(case.fixture.spec, o.sample_id, ())


def test_restart_idempotence_and_full_audit(case: Case) -> None:
    p = first(case)
    result = case.engine.evaluate(case.fixture.forecast_ids, 100, 100)
    case.engine.audit_lineage(result.fingerprint)
    assert case.repo.audit() > 0
    with case.repo.transaction():
        assert case.repo.put(p) == p.fingerprint
    before = canonical_json(p)
    case.repo.close()
    with EventRepository(case.path) as repo:
        assert canonical_json(repo.get(EventConditionedForecast, p.fingerprint)) == before
        assert repo.get(type(result), result.fingerprint) == result
        assert repo.audit() > 0


def test_event_clock_and_subject_bytes_detected(case: Case) -> None:
    old = case.repo.get(EventReference, first(case).event_ids[0])
    for changed in (
        replace(old, clocks=replace(old.clocks, final_available_ns=61)),
        replace(
            old,
            subject=replace(
                old.subject,
                security=case.repo.get(
                    EventConditionedForecast, case.fixture.forecast_ids[-1]
                ).security,
            ),
        ),
    ):
        if changed == old:
            continue
        with case.repo.transaction():
            case.repo._connection.execute(
                "DROP TRIGGER IF EXISTS immutable_ec_artifacts_update"
            )
            case.repo._connection.execute(
                "UPDATE ec_artifacts SET payload=? WHERE fingerprint=?",
                (canonical_json(changed), old.fingerprint),
            )
        with pytest.raises(ContractError, match="hash"):
            case.repo.get(EventReference, old.fingerprint)

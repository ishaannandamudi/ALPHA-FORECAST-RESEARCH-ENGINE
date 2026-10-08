"""Transactional additive migration and structural/semantic corruption fail closed."""

import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from afre.costs import CostResearchRepository
from afre.costs.artifacts import (
    CostAwareSampleEvaluation,
    CostComponentEstimate,
    ResearchExposureChange,
)
from afre.costs.definitions import CostScenario
from afre.costs.lineage import cost_edges
from afre.costs.storage import costs_index, costs_schema
from afre.feature_store.models import SourceReference
from afre.hashing import bytes_digest
from afre.invariance import InvarianceRepository
from afre.lineage import ProvenanceRef
from afre.schema import Artifact, ContractError
from afre.serialization import canonical_json, deserialize
from tests.costs.conftest import CostCase


def layout(db: sqlite3.Connection) -> tuple[tuple[object, ...], ...]:
    return tuple(
        db.execute(
            "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    )


def test_migration_preserves_prior_ddl_metadata_rows(tmp_path: Path) -> None:
    path = tmp_path / "old.sqlite"
    provenance = ProvenanceRef("neutral-baseline", "prior-record", "1", bytes_digest(b"old"))
    p = SourceReference(provenance, provenance.fingerprint)
    with InvarianceRepository(path) as old:
        with old.transaction():
            old.put(p)
        before = layout(old._connection)
        metadata = dict(old._connection.execute("SELECT key,value FROM metadata"))
        tables = [
            r[0]
            for r in old._connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        ]
        rows = {
            t: old._connection.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall()
            for t in tables
        }
    with CostResearchRepository(path) as new:
        assert new._connection.execute("PRAGMA user_version").fetchone()[0] == 19
        assert set(before) <= set(layout(new._connection))
        after = dict(new._connection.execute("SELECT key,value FROM metadata"))
        assert (
            all(after[k] == v for k, v in metadata.items()) and len(after) == len(metadata) + 3
        )
        assert all(
            rows[t] == new._connection.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall()
            for t in tables
            if t != "metadata"
        )
        assert new.get_any(p.fingerprint) == p


def test_migration_rollback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import afre.costs.repository as module

    path = tmp_path / "rollback.sqlite"
    with InvarianceRepository(path) as old:
        before = layout(old._connection)
        metadata = old._connection.execute("SELECT * FROM metadata ORDER BY key").fetchall()
    statements = costs_schema()
    monkeypatch.setattr(
        module, "costs_schema", lambda: (*statements, "CREATE TABLE metadata (broken TEXT)")
    )
    with pytest.raises(sqlite3.OperationalError):
        CostResearchRepository(path)
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 18
        assert layout(db) == before
        assert db.execute("SELECT * FROM metadata ORDER BY key").fetchall() == metadata


def test_future_version_rejected(tmp_path: Path) -> None:
    path = tmp_path / "future.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA user_version=20")
    with pytest.raises(ContractError, match="future"):
        CostResearchRepository(path)


@pytest.mark.parametrize(
    "kind", ["component", "total", "sample", "aggregate", "breakeven", "scenario", "exposure"]
)
def test_forgery_atomic(case: CostCase, kind: str) -> None:
    path, totals = case.engine.estimate(case.fixture.scenario.fingerprint, 70)
    evaluation = case.engine.evaluate(
        path.fingerprint, tuple(t.fingerprint for t in totals), 70, 70
    )
    value: Artifact
    if kind == "component":
        c = case.repo.resolve(CostComponentEstimate, totals[0].component_ids[0])
        value = replace(c, amount=(c.amount or 0) + 1.0)
    elif kind == "total":
        value = replace(totals[0], amount=(totals[0].amount or 0) + 1.0)
    elif kind == "sample":
        r = case.repo.resolve(CostAwareSampleEvaluation, evaluation.sample_evaluation_ids[0])
        assert r.gross_contribution is not None and r.net_contribution is not None
        value = replace(
            r,
            gross_contribution=r.gross_contribution + 1.0,
            net_contribution=r.net_contribution + 1.0,
        )
    elif kind == "aggregate":
        value = replace(evaluation, gross_sum=(evaluation.gross_sum or 0) + 1.0)
    elif kind == "breakeven":
        b = case.engine.breakeven(evaluation.fingerprint, 70)
        value = replace(b, threshold=(b.threshold or 0) + 1.0)
    elif kind == "scenario":
        value = replace(case.fixture.scenario, currency="EUR")
    else:
        change = case.repo.resolve(ResearchExposureChange, path.change_ids[0])
        value = replace(
            change,
            exposure=change.exposure + 0.1,
            trade_delta=(change.exposure + 0.1) - change.prior_exposure,
        )
    before = case.repo._connection.execute("SELECT count(*) FROM cost_artifacts").fetchone()[0]
    with pytest.raises(ContractError), case.repo.transaction():
        case.repo.put(value)
    assert (
        case.repo._connection.execute("SELECT count(*) FROM cost_artifacts").fetchone()[0]
        == before
    )


@pytest.mark.parametrize("kind", ["component", "sample"])
def test_consistent_sql_valid_hash_forgery_read_rejected(case: CostCase, kind: str) -> None:
    path, totals = case.engine.estimate(case.fixture.scenario.fingerprint, 70)
    result = case.engine.evaluate(
        path.fingerprint, tuple(t.fingerprint for t in totals), 70, 70
    )
    value: Artifact
    if kind == "component":
        c = case.repo.resolve(CostComponentEstimate, totals[0].component_ids[0])
        value = replace(c, amount=(c.amount or 0) + 1.0)
    else:
        r = case.repo.resolve(CostAwareSampleEvaluation, result.sample_evaluation_ids[0])
        assert r.gross_contribution is not None and r.net_contribution is not None
        value = replace(
            r,
            gross_contribution=r.gross_contribution + 1.0,
            net_contribution=r.net_contribution + 1.0,
        )
    with case.repo.transaction():
        case.repo._connection.execute(
            "INSERT INTO cost_artifacts VALUES (?,?,?,?)",
            (value.fingerprint, type(value).__name__, "1.0", canonical_json(value)),
        )
        case.repo._connection.execute(
            "INSERT INTO cost_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", costs_index(value)
        )
        case.repo._connection.executemany(
            "INSERT INTO cost_links VALUES (?,?)",
            tuple((value.fingerprint, i) for i in sorted(set(cost_edges(value)))),
        )
    with pytest.raises(ContractError, match="semantic replay"):
        case.repo.resolve(type(value), value.fingerprint)


@pytest.mark.parametrize("kind", ["payload", "family", "schema", "index", "links"])
def test_sql_corruption_read_rejected(case: CostCase, kind: str) -> None:
    s = case.fixture.scenario
    with case.repo.transaction():
        if kind == "links":
            case.repo._connection.execute("DROP TRIGGER immutable_cost_links_delete")
            case.repo._connection.execute(
                "DELETE FROM cost_links WHERE fingerprint=?", (s.fingerprint,)
            )
        elif kind == "index":
            case.repo._connection.execute("DROP TRIGGER immutable_cost_records_update")
            case.repo._connection.execute(
                "UPDATE cost_records SET target_id='forged' WHERE fingerprint=?",
                (s.fingerprint,),
            )
        else:
            case.repo._connection.execute("DROP TRIGGER immutable_cost_artifacts_update")
            field, value = (
                ("payload", "{}")
                if kind == "payload"
                else ("type_name", "CostInputReference")
                if kind == "family"
                else ("schema_version", "99")
            )
            case.repo._connection.execute(
                f"UPDATE cost_artifacts SET {field}=? WHERE fingerprint=?",
                (value, s.fingerprint),
            )
    with pytest.raises(ContractError):
        case.repo.resolve(CostScenario, s.fingerprint)


def test_idempotence_restart_and_transaction_required(case: CostCase) -> None:
    scenario = case.fixture.scenario
    before = case.repo._connection.execute("SELECT count(*) FROM cost_artifacts").fetchone()[0]
    with pytest.raises(ContractError, match="transaction"):
        case.repo.put(scenario)
    case.engine.declare(scenario)
    assert (
        case.repo._connection.execute("SELECT count(*) FROM cost_artifacts").fetchone()[0]
        == before
    )
    db = case.repo._connection.execute("PRAGMA database_list").fetchone()[2]
    with CostResearchRepository(db) as restarted:
        assert restarted.resolve(CostScenario, scenario.fingerprint) == scenario
        assert deserialize(canonical_json(scenario)) == scenario


@pytest.mark.parametrize("padding", ("oversized", "noncanonical"))
def test_raw_stored_payload_bytes_and_canonical_form(
    case: CostCase, padding: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import afre.costs.repository as module
    from afre.costs import CostResearchBounds

    value = case.fixture.inputs[0]
    raw = canonical_json(value)
    limit = len(raw.encode()) + 100
    case.repo.cost_research_bounds = replace(CostResearchBounds(), serialized_bytes=limit)
    altered = raw + (" " * limit if padding == "oversized" else " ")
    decoded: list[str] = []
    original = deserialize

    def observe(payload: str) -> Artifact:
        decoded.append(payload)
        return original(payload)

    monkeypatch.setattr(module, "deserialize", observe)
    with case.repo.transaction():
        case.repo._connection.execute("DROP TRIGGER immutable_cost_artifacts_update")
        case.repo._connection.execute(
            "UPDATE cost_artifacts SET payload=? WHERE fingerprint=?",
            (altered, value.fingerprint),
        )
    with pytest.raises(ContractError, match="payload bound|canonical"):
        case.repo.get(type(value), value.fingerprint)
    if padding == "oversized":
        assert not decoded, "cost byte limit must run before decoder"

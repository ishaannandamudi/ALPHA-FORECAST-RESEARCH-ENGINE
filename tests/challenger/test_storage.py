"""Additive migration, rollback, immutable projections, corruption and configured bounds."""

import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from afre.challenger import (
    ChallengeBounds,
    ChallengeRun,
    CommonMatchedEvidence,
    ParticipantMetricResult,
    PromotionAssessment,
)
from afre.challenger import (
    ChallengeMetric as M,
)
from afre.challenger.repository import ChallengeRepository
from afre.challenger.storage import challenge_schema
from afre.health import HealthBounds, HealthRepository
from afre.schema import Artifact, ContractError
from examples.challenger_fixture import evidence_for, program_for
from tests.challenger.conftest import ChallengeCase


def test_migration_preserves_previous_schema(tmp_path: Path) -> None:
    path = tmp_path / "prior.sqlite"
    with HealthRepository(path) as prior:
        with prior.transaction():
            prior.put(HealthBounds())
        ddl = dict(
            prior._connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        )
        metadata = dict(prior._connection.execute("SELECT * FROM metadata"))
        rows = tuple(prior._connection.execute("SELECT * FROM hlt_artifacts"))
    with ChallengeRepository(path) as current:
        after = dict(
            current._connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        )
        assert all(after[n] == sql for n, sql in ddl.items())
        assert (
            dict(current._connection.execute("SELECT * FROM metadata")).items()
            >= metadata.items()
        )
        assert tuple(current._connection.execute("SELECT * FROM hlt_artifacts")) == rows
        assert current._connection.execute("PRAGMA user_version").fetchone()[0] == 24


def test_failed_migration_rolls_back_and_future_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import afre.challenger.repository as module

    path = tmp_path / "rollback.sqlite"
    with HealthRepository(path):
        pass
    monkeypatch.setattr(
        module, "challenge_schema", lambda: (*challenge_schema(), "INVALID SQL")
    )
    with pytest.raises(sqlite3.OperationalError):
        ChallengeRepository(path)
    with HealthRepository(path) as prior:
        assert prior._connection.execute("PRAGMA user_version").fetchone()[0] == 23
        assert not prior._connection.execute(
            "SELECT name FROM sqlite_master WHERE name LIKE 'ch_%'"
        ).fetchall()
        prior._connection.execute("PRAGMA user_version=25")
    with pytest.raises(ContractError, match="future"):
        ChallengeRepository(path)


def prepared(c: ChallengeCase) -> tuple[Artifact, ...]:
    p, r = program_for(c.fixture)
    c.engine.declare(p, r)
    evidence = c.engine.evidence(evidence_for(c.repo, c.fixture, p))
    run = c.engine.evaluate(evidence.fingerprint)
    return (
        p,
        r[0],
        evidence,
        c.repo.resolve(CommonMatchedEvidence, run.common_id),
        c.repo.resolve(ParticipantMetricResult, run.metric_ids[0]),
        c.repo.resolve(PromotionAssessment, run.promotion_ids[0]),
        run,
    )


@pytest.mark.parametrize("index", range(7))
def test_invalid_payload_hash(challenge_case: ChallengeCase, index: int) -> None:
    c = challenge_case
    value = prepared(c)[index]
    row = c.repo._connection.execute(
        "SELECT payload FROM ch_artifacts WHERE fingerprint=?", (value.fingerprint,)
    ).fetchone()
    wire = json.loads(row[0])
    wire["artifact"]["fields"][next(iter(wire["artifact"]["fields"]))] = "tampered"
    c.repo._connection.execute("DROP TRIGGER immutable_ch_artifacts_update")
    c.repo._connection.execute(
        "UPDATE ch_artifacts SET payload=? WHERE fingerprint=?",
        (json.dumps(wire), value.fingerprint),
    )
    with pytest.raises(ContractError):
        c.repo.get_any(value.fingerprint)


@pytest.mark.parametrize("kind", ("metric", "common", "promotion", "run"))
def test_valid_hash_semantic_forgery(challenge_case: ChallengeCase, kind: str) -> None:
    c = challenge_case
    values = prepared(c)
    forged: Artifact
    if kind == "metric":
        m = values[4]
        assert isinstance(m, ParticipantMetricResult)
        forged = replace(m, value=999.0)
    elif kind == "common":
        common = values[3]
        assert isinstance(common, CommonMatchedEvidence)
        forged = replace(common, assignments=())
    elif kind == "promotion":
        p = values[5]
        assert isinstance(p, PromotionAssessment)
        forged = replace(
            p,
            criterion_results=tuple((i, True, "fabricated") for i, _, _ in p.criterion_results),
        )
    else:
        run = values[6]
        assert isinstance(run, ChallengeRun)
        forged = replace(run, metric_ids=run.metric_ids[:-1])
    with c.repo.transaction(), pytest.raises(ContractError):
        c.repo.put(forged)


@pytest.mark.parametrize("table", ("ch_artifacts", "ch_records", "ch_links"))
@pytest.mark.parametrize("operation", ("UPDATE", "DELETE"))
def test_sql_immutable(challenge_case: ChallengeCase, table: str, operation: str) -> None:
    prepared(challenge_case)
    query = (
        f"UPDATE {table} SET fingerprint=fingerprint"
        if operation == "UPDATE"
        else f"DELETE FROM {table}"
    )
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        challenge_case.repo._connection.execute(query)


@pytest.mark.parametrize("projection", ("ch_records", "ch_links"))
def test_projection_tampering(challenge_case: ChallengeCase, projection: str) -> None:
    c = challenge_case
    value = prepared(c)[6]
    c.repo._connection.execute(f"DROP TRIGGER immutable_{projection}_delete")
    c.repo._connection.execute(
        f"DELETE FROM {projection} WHERE fingerprint=?", (value.fingerprint,)
    )
    with pytest.raises(ContractError, match="corruption"):
        c.repo.get_any(value.fingerprint)


@pytest.mark.parametrize(
    "field",
    (
        "samples",
        "shadow_rows",
        "payload_bytes",
        "snapshot_bytes",
        "lineage_nodes",
        "lineage_depth",
        "lineage_bytes",
        "artifacts",
    ),
)
def test_configured_bounds(challenge_case: ChallengeCase, field: str) -> None:
    c = challenge_case
    values = prepared(c)
    c.repo.challenge_bounds = replace(ChallengeBounds(), **{field: 1})
    with pytest.raises(ContractError, match="bound"):
        if field.startswith("lineage"):
            c.engine.audit(values[6].fingerprint)
        elif field == "snapshot_bytes":
            with c.repo.read_snapshot():
                pass
        elif field == "artifacts":
            c.engine.publish((ChallengeBounds(samples=1),))
        else:
            c.repo.get_any(values[2].fingerprint)


@pytest.mark.parametrize("kind", ("indexes", "metadata", "orphan"))
def test_layout_and_orphan_corruption(challenge_case: ChallengeCase, kind: str) -> None:
    c = challenge_case
    if kind == "indexes":
        c.repo._connection.execute("DROP INDEX ch_program_idx")
        with pytest.raises(ContractError, match="layout"):
            c.repo._validate_layout()
    elif kind == "metadata":
        c.repo._connection.execute("INSERT INTO metadata VALUES ('extra','bad')")
        with pytest.raises(ContractError, match="metadata"):
            c.repo._validate_layout()
    else:
        c.repo._connection.execute(
            "INSERT INTO ch_links VALUES (?,?)",
            (
                c.fixture.participants[0].reference.target_id,
                c.fixture.participants[0].fingerprint,
            ),
        )
        with pytest.raises(ContractError, match="orphan"):
            c.repo.audit()


def test_idempotence_missing_type_and_payload_bound(challenge_case: ChallengeCase) -> None:
    c = challenge_case
    values = prepared(c)
    with c.repo.transaction():
        assert c.repo.put(values[6]) == values[6].fingerprint
    with pytest.raises(KeyError):
        assert isinstance(values[6], ChallengeRun)
        c.repo.get(ChallengeRun, replace(values[6], available_ns=121).fingerprint)
    with pytest.raises(ContractError):
        c.repo.put(ChallengeBounds())
    with pytest.raises(ContractError):
        c.repo.get(ParticipantMetricResult, values[6].fingerprint)
    assert c.engine.history(program_for(c.fixture, (M.MSE,))[0].fingerprint) == ()

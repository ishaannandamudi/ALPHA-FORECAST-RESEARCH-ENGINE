"""Semantic corruption, historical metadata revisions and before-cache outcome guards."""

from dataclasses import replace

import pytest

from afre.challenger import ChallengeEngine, ChallengeRun, EvaluationEvidence
from afre.health import HealthEngine, ModelHealthSnapshot
from afre.schema import CONTRACTS, Artifact, ContractError
from afre.serialization import canonical_json
from afre.service import ContextField, ServiceStatus, SnapshotPublication
from afre.service import ServiceContextKind as K
from afre.service.registry_entries import RegistryEntry
from afre.service.repository import OUTCOMES
from afre.service.storage import links, record_index
from tests.service.conftest import ServiceCase


def insert_forged(c: ServiceCase, value: Artifact) -> None:
    with c.repo.transaction():
        c.repo._connection.execute(
            "INSERT INTO svc_artifacts VALUES (?,?,?,?)",
            (value.fingerprint, type(value).__name__, "1.0", canonical_json(value)),
        )
        c.repo._connection.execute(
            "INSERT INTO svc_records VALUES (?,?,?,?,?,?,?,?,?,?)", record_index(value)
        )
        c.repo._connection.executemany(
            "INSERT INTO svc_links VALUES (?,?)",
            tuple((value.fingerprint, i) for i in links(value)),
        )


@pytest.mark.parametrize("part", ["registry", "context", "lineage", "audit", "models"])
def test_valid_hash_semantic_forgery(service_case: ServiceCase, part: str) -> None:
    c = service_case
    source, requests = c.fixture.context_cases[0]
    snapshot = c.publisher.publish(SnapshotPublication(source, "original", 120, requests))
    forged: Artifact
    if part == "registry":
        entry = c.repo.get(RegistryEntry, snapshot.registry_entry_ids[0])
        forged = replace(entry, version="invented-version")
        insert_forged(c, forged)
        result = c.service.get_registry_entry(forged.fingerprint)
    elif part == "audit":
        audit = c.publisher.audit(snapshot.fingerprint)
        forged = replace(audit, limitations=("Forged metadata",))
        insert_forged(c, forged)
        result = c.service.get_audit(forged.fingerprint)
    else:
        if part == "context":
            context = snapshot.contexts[0]
            fields = (*context.fields, ContextField("untrusted.extra", 1.0))
            forged = replace(
                snapshot, contexts=(replace(context, fields=fields), *snapshot.contexts[1:])
            )
        elif part == "lineage":
            forged = replace(snapshot, lineage=replace(snapshot.lineage, edges=()))
        else:
            forged = replace(snapshot, model_ids=(snapshot.target.fingerprint,))
        insert_forged(c, forged)
        result = c.service.get_snapshot(forged.fingerprint)
    assert result.status is ServiceStatus.CORRUPT_ARTIFACT
    with c.repo.transaction(), pytest.raises(ContractError, match="semantic"):
        c.repo.put(forged)
    assert c.service.get_snapshot(snapshot.fingerprint).value == snapshot


@pytest.mark.parametrize("index", [0, 4])
def test_corrected_historical_context(service_case: ServiceCase, index: int) -> None:
    c = service_case
    source, requests = c.fixture.context_cases[index]
    old = c.publisher.publish(SnapshotPublication(source, "context", 120, requests))
    context = next(x for x in old.contexts if x.kind in (K.HEALTH, K.CHALLENGE))
    new_context: ModelHealthSnapshot | ChallengeRun
    if context.kind is K.HEALTH:
        native = c.repo.get(ModelHealthSnapshot, context.artifact_id)
        new_context = HealthEngine(c.repo).evaluate(native.spec_id, 121)
    else:
        run = c.repo.get(ChallengeRun, context.artifact_id)
        evidence = c.repo.get(EvaluationEvidence, run.evidence_id)
        engine = ChallengeEngine(c.repo)
        changed = engine.evidence(replace(evidence, available_ns=121))
        new_context = engine.evaluate(changed.fingerprint)
    updated_requests = tuple(
        replace(r, artifact_id=new_context.fingerprint) if r.kind is context.kind else r
        for r in requests
    )
    new = c.publisher.publish(
        replace(old.publication, contexts=updated_requests, published_ns=121)
    )
    assert new.fingerprint != old.fingerprint and new.output == old.output
    assert c.service.get_snapshot(old.fingerprint).value == old
    assert c.service.get_snapshot(new.fingerprint).value == new


def test_all_closed_outcome_classes_are_guarded(service_case: ServiceCase) -> None:
    c = service_case
    classes = tuple(cls for cls in CONTRACTS.values() if cls.__name__ in OUTCOMES)
    assert len(classes) >= 40
    with c.repo.request():
        for cls in classes:
            identity = "afre." + cls.domain + ":1.0:" + "0" * 64
            for method in (c.repo.get, c.repo.resolve):
                with pytest.raises(ContractError, match="before cache"):
                    method(cls, identity)
            with pytest.raises(ContractError, match="before cache"):
                c.repo.get_any(identity)

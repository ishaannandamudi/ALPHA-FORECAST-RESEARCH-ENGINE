"""Native optional context is bounded, exact, causal or explicitly historical."""

from dataclasses import replace
from unittest.mock import patch

import pytest

from afre.schema import ContractError
from afre.service import (
    ContextRequest,
    ServiceStatus,
    SnapshotPublication,
    canonical_json,
)
from afre.service import (
    ServiceContextKind as K,
)
from afre.target_engine.models import TargetVintage
from tests.service.conftest import ServiceCase


@pytest.mark.parametrize("index", range(5))
def test_native_contexts(service_case: ServiceCase, index: int) -> None:
    c = service_case
    source, requests = c.fixture.context_cases[index]
    core = c.publisher.publish(SnapshotPublication(source, "core", 120))
    with patch.object(c.repo, "get", wraps=c.repo.get) as access:
        snapshot = c.publisher.publish(SnapshotPublication(source, "full", 120, requests))
        assert c.service.get_snapshot(snapshot.fingerprint).value == snapshot
        assert not any(call.args[0] is TargetVintage for call in access.call_args_list)
    assert snapshot.output == core.output and snapshot.fingerprint != core.fingerprint
    assert (
        c.publisher.publish(replace(snapshot.publication, contexts=tuple(reversed(requests))))
        == snapshot
    )
    assert {r.artifact_id for r in requests} == {
        context.artifact_id for context in snapshot.contexts
    }
    for context in snapshot.contexts:
        values = {f.path: f.value for f in context.fields}
        assert values and context.projection_version == "1.0"
        if context.kind is K.HEALTH:
            assert (
                c.service.get_health_metadata(snapshot.fingerprint, context.artifact_id).value
                == context
            )
            assert (
                context.action == "NONE_DESCRIPTIVE_ONLY"
                and context.available_ns > snapshot.origin.timestamp_ns
            )
            assert any(k.endswith("status") for k in values)
        elif context.kind is K.CHALLENGE:
            assert (
                c.service.get_challenge_metadata(
                    snapshot.fingerprint, context.artifact_id
                ).value
                == context
            )
            assert context.action == "MANUAL_ONLY" and context.historical_evaluation
        else:
            assert context.available_ns <= snapshot.final_available_ns
            assert not context.historical_evaluation
        if context.kind is K.UNCERTAINTY:
            assert any(v is None for v in values.values())
        if context.kind is K.RANKING:
            assert "entry.rank" in values and "definition.ties" in values
        if context.kind is K.REGIME:
            assert values["regime.semantics"] == "filtered"
        if context.kind is K.EVENT:
            assert any(k.startswith("events.") for k in values)
    assert canonical_json(c.service.get_snapshot(core.fingerprint)) != canonical_json(
        c.service.get_snapshot(snapshot.fingerprint)
    )
    if index == 0:
        assert (
            c.service.get_snapshot(
                snapshot.fingerprint, ("HEALTH", "RANKING", "UNCERTAINTY", "ORTHOGONAL_CONTEXT")
            ).status
            is ServiceStatus.AVAILABLE
        )


def test_context_rejections(service_case: ServiceCase) -> None:
    c = service_case
    source, requests = c.fixture.context_cases[0]
    health = next(r for r in requests if r.kind is K.HEALTH)
    with pytest.raises(ContractError, match="historical"):
        ContextRequest(K.HEALTH, health.artifact_id)
    with pytest.raises(ContractError):
        c.publisher.publish(SnapshotPublication(source, "late-meta", 60, (health,)))
    bad = ContextRequest(K.EVENT, health.artifact_id)
    with pytest.raises(ContractError, match="context type"):
        c.publisher.publish(SnapshotPublication(source, "wrong", 120, (bad,)))
    from afre.probabilistic.artifacts import ProbabilisticForecast

    other_source = c.repo.get(ProbabilisticForecast, source).point_forecast_id
    uncertainty = next(r for r in requests if r.kind is K.UNCERTAINTY)
    with pytest.raises(ContractError, match="forecast"):
        c.publisher.publish(SnapshotPublication(other_source, "unrelated", 120, (uncertainty,)))


@pytest.mark.parametrize("index,field", [(1, "event_ids"), (2, "regime_snapshot_id")])
def test_exact_reference_context(service_case: ServiceCase, index: int, field: str) -> None:
    c = service_case
    source_id, _ = c.fixture.context_cases[index]
    raw = c.repo.raw(source_id)
    reference = getattr(raw, field)
    identity = reference[0] if isinstance(reference, tuple) else reference
    kind = K.EVENT if index == 1 else K.REGIME
    snapshot = c.publisher.publish(
        SnapshotPublication(source_id, "reference", 120, (ContextRequest(kind, identity),))
    )
    context = snapshot.contexts[0]
    assert (
        context.artifact_id == identity and context.available_ns <= snapshot.final_available_ns
    )
    assert c.service.get_snapshot(snapshot.fingerprint).value == snapshot

"""Historical evidence binds source/entity; policies fail closed and payloads stay data."""

import ast
import tomllib
from dataclasses import replace
from pathlib import Path

import pytest

from afre.event_conditioned import (
    EventBounds,
    EventModelFamily,
    EventReference,
    EventRelation,
    EventScope,
    EventSubject,
    EventValueRule,
)
from afre.feature_store.models import AvailabilityEvidence, QualifiedHistoricalDelivery
from afre.feature_store.schema import AvailabilityMode, DeliveryEvidenceKind
from afre.schema import ContractError
from examples.event_conditioned_demo import event
from tests.event_conditioned.conftest import Case
from tests.event_conditioned.test_temporal import sample_for


@pytest.mark.parametrize("kind", ["archive", "qualified", "attestor", "entity", "source"])
def test_historical_reconstruction_never_implies_literal_old_receipt(
    case: Case, kind: str
) -> None:
    sample = sample_for(case)
    e = event(sample, "archive", at=60, received=1000)
    evidence = None
    if kind != "archive":
        other = case.repo.get(EventReference, case.fixture.event_ids[0])
        entity = (
            other.subject.security.instrument
            if kind == "entity" and other.subject.security
            else sample.security.instrument
        )
        if kind == "entity" and entity == sample.security.instrument:
            from afre.ids import InstrumentId

            entity = InstrumentId("synthetic", "different")
        evidence = QualifiedHistoricalDelivery(
            e.source.fingerprint
            if kind != "source"
            else replace(
                e.source, provenance=replace(e.source.provenance, artifact_id="other-source")
            ).fingerprint,
            entity,
            DeliveryEvidenceKind.QUALIFIED_CHANNEL_REPLAY,
            60,
            60,
            60,
            999,
            "qualified-archive",
            "immutable-channel",
            "1",
            e.source.provenance,
        )
    clock = AvailabilityEvidence(
        1000,
        1000,
        1000,
        60 if evidence else 1000,
        60,
        60,
        AvailabilityMode.RECONSTRUCTED,
        evidence,
    )
    spec = replace(
        case.fixture.spec,
        approved_delivery_attestors=() if kind == "attestor" else ("qualified-archive",),
    )
    if kind == "source":
        with pytest.raises(ContractError, match="source"):
            replace(e, clocks=clock)
        return
    identity = case.engine.publish_event(replace(e, clocks=clock))
    if kind in ("attestor", "entity"):
        with pytest.raises(ContractError, match="attestor|entity|approved"):
            case.engine.observe(spec, sample.fingerprint, (identity,))
    else:
        observed = case.engine.observe(spec, sample.fingerprint, (identity,))[0]
        assert bool(observed.event_id) == (kind == "qualified")
        persisted = case.repo.get(EventReference, identity)
        assert persisted.clocks.afre_received_ns == 1000
        if evidence:
            assert persisted.clocks.historical_delivery == evidence


@pytest.mark.parametrize(
    "kind",
    [
        "empty",
        "count",
        "threshold",
        "features",
        "reaction",
        "bins",
        "policy",
        "window",
        "delay",
        "tags",
        "subject",
        "scale",
        "surprise",
        "hard-bound",
        "zero-bound",
        "custom",
    ],
)
def test_closed_contracts(case: Case, kind: str) -> None:
    spec = case.fixture.spec
    e = event(sample_for(case), "contract")
    assert e.materiality and e.surprise
    with pytest.raises(ContractError):
        if kind == "empty":
            replace(spec, classes=())
        elif kind == "count":
            replace(spec, minimum_samples=1)
        elif kind == "threshold":
            EventValueRule("materiality", e.materiality.semantic_key, minimum=1.0, maximum=0.0)
        elif kind == "features":
            replace(spec, family=EventModelFamily.MATERIALITY_LINEAR)
        elif kind == "reaction":
            replace(spec, reaction_specs=(case.fixture.upstream.spec.score,))
        elif kind == "bins":
            replace(spec, materiality_bins=(0.5, 0.5))
        elif kind == "policy":
            replace(spec, fitting_policy="learned-selection")
        elif kind == "window":
            replace(spec.window, basis="business-days")
        elif kind == "delay":
            replace(spec.window, relation=EventRelation.POST_EVENT_DELAYED)
        elif kind == "tags":
            replace(e, tags=("a", "a"))
        elif kind == "subject":
            EventSubject(EventScope.MACRO, security=e.subject.security)
        elif kind == "scale":
            replace(e.materiality, value=2.0)
        elif kind == "surprise":
            replace(e.surprise, normalization=0.0)
        elif kind == "hard-bound":
            EventBounds(events=1_000_001)
        elif kind == "zero-bound":
            EventBounds(audit_depth=0)
        else:
            EventSubject(EventScope.CUSTOM)


def test_no_executable_payloads_or_direct_engine_dependency() -> None:
    root = Path(__file__).resolve().parents[2]
    prohibited = {"ame", "eie", "pickle", "joblib", "socket", "subprocess", "importlib"}
    for path in (root / "src/afre/event_conditioned").glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(a.name.split(".")[0] not in prohibited for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in prohibited
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in {"eval", "exec", "__import__", "compile"}
    assert tomllib.loads((root / "pyproject.toml").read_text())["project"]["dependencies"] == []

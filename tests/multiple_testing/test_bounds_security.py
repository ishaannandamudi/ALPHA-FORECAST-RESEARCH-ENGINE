"""Lowered limits, raw-byte admission, lineage bounds and closed dependency boundaries."""

import ast
from dataclasses import replace
from pathlib import Path

import pytest

from afre.multiple_testing import (
    MultipleTestingBounds,
    TrialSpecification,
)
from afre.multiple_testing.lineage import audit_for
from afre.schema import ContractError
from afre.serialization import canonical_json, deserialize
from tests.multiple_testing.conftest import TestingCase as MTCase
from tests.multiple_testing.helpers import analyses, trial


@pytest.mark.parametrize(
    "field",
    [
        "trials",
        "hypotheses",
        "samples",
        "metrics",
        "test_history",
        "selection_events",
        "registry_snapshots",
        "artifacts",
        "serialized_bytes",
        "audit_nodes",
        "audit_depth",
    ],
)
@pytest.mark.parametrize("value", [0, -1, 10**10])
def test_bound_contract_limits(field: str, value: int) -> None:
    with pytest.raises(ContractError):
        replace(MultipleTestingBounds(), **{field: value})


@pytest.mark.parametrize(
    "field", ["trials", "hypotheses", "samples", "metrics", "serialized_bytes"]
)
def test_lowered_registration_bounds(mt_case: MTCase, field: str) -> None:
    mt_case.repo.multiple_testing_bounds = replace(MultipleTestingBounds(), **{field: 1})
    with pytest.raises(ContractError):
        if field == "samples":
            mt_case.engine.plan(mt_case.fixture.plan("phase-5"))
        else:
            mt_case.engine.family(mt_case.fixture.family)


@pytest.mark.parametrize("field", ["trials", "test_history"])
def test_registry_enumeration_bound(mt_case: MTCase, field: str) -> None:
    if field == "test_history":
        for j in range(2):
            p = mt_case.fixture.plan(f"test-{j}")
            mt_case.engine.complete(
                p.fingerprint,
                mt_case.fixture.family.fingerprint,
                100,
                100,
                test_identity=f"distinct-native-history-{j}",
            )
    mt_case.repo.multiple_testing_bounds = replace(MultipleTestingBounds(), **{field: 1})
    with pytest.raises(ContractError):
        mt_case.engine.registry(100, 100)


def test_snapshot_artifact_count_bound(mt_case: MTCase) -> None:
    mt_case.repo.multiple_testing_bounds = replace(
        MultipleTestingBounds(), registry_snapshots=1
    )
    mt_case.engine.registry(100, 100)
    with pytest.raises(ContractError, match="artifact bound"):
        mt_case.engine.registry(101, 101)


def test_plan_structural_choices_and_duplicate_bounds(mt_case: MTCase) -> None:
    p = mt_case.fixture.plan("phase-5")
    for changes in (
        {"source_ids": (*p.source_ids, p.source_ids[0])},
        {"choices": (("duplicate", "a"), ("duplicate", "b"))},
        {"model_spec_ids": tuple(p.dataset_id + str(i) for i in range(33))},
    ):
        with pytest.raises(ContractError):
            replace(p, **changes)


@pytest.mark.parametrize("padding", ["oversized", "noncanonical"])
def test_raw_size_before_decoder(
    mt_case: MTCase, padding: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import afre.multiple_testing.repository as module

    value = mt_case.fixture.plan("phase-5")
    raw = canonical_json(value)
    limit = len(raw.encode()) + 100
    mt_case.repo.multiple_testing_bounds = replace(
        MultipleTestingBounds(), serialized_bytes=limit
    )
    altered = raw + (" " * limit if padding == "oversized" else " ")
    decoded = []

    def observe(payload: str) -> object:
        decoded.append(payload)
        return deserialize(payload)

    monkeypatch.setattr(module, "deserialize", observe)
    with mt_case.repo.transaction():
        mt_case.repo._connection.execute("DROP TRIGGER immutable_mt_artifacts_update")
        mt_case.repo._connection.execute(
            "UPDATE mt_artifacts SET payload=? WHERE fingerprint=?",
            (altered, value.fingerprint),
        )
    with pytest.raises(ContractError):
        mt_case.repo.get(TrialSpecification, value.fingerprint)
    if padding == "oversized":
        assert not decoded


@pytest.mark.parametrize("field", ["audit_nodes", "audit_depth", "serialized_bytes"])
def test_unified_lineage_limits(completed_case: MTCase, field: str) -> None:
    root = analyses(completed_case)[0].fingerprint
    completed_case.repo.multiple_testing_bounds = replace(MultipleTestingBounds(), **{field: 1})
    with pytest.raises(ContractError):
        completed_case.engine.audit(root)


def test_bounded_audit_native_train_truth_and_seal(completed_case: MTCase) -> None:
    t = trial(completed_case, "test-0")
    audit = completed_case.engine.audit(t.fingerprint)
    assert {
        t.fingerprint,
        t.plan_id,
        t.family_id,
        *t.test_seal_ids,
        *[o.truth_id for o in t.observations],
    } <= set(audit.node_ids)
    assert any(i.startswith("afre.m_fit_run:") for i in audit.node_ids)
    assert completed_case.repo.get_any(audit.fingerprint) == audit
    with pytest.raises(ContractError):
        audit_for(completed_case.repo, audit.fingerprint)
    with pytest.raises(ContractError):
        audit_for(completed_case.repo, t.observations[0].source_id)


def test_lineage_cycle_rejected(
    completed_case: MTCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    import afre.multiple_testing.lineage as module

    t = trial(completed_case, "phase-5")
    monkeypatch.setattr(module, "testing_edges", lambda value: (value.fingerprint,))
    with pytest.raises(ContractError, match="cycle"):
        audit_for(completed_case.repo, t.fingerprint)


def test_no_direct_external_engine_or_executable_runtime_imports() -> None:
    root = Path(__file__).resolve().parents[2] / "src/afre/multiple_testing"
    banned = {
        "socket",
        "urllib",
        "requests",
        "httpx",
        "subprocess",
        "pickle",
        "joblib",
        "importlib",
        "numpy",
        "scipy",
        "os",
    }
    imported: set[str] = set()
    for path in root.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            if isinstance(node, ast.ImportFrom):
                name = node.module or ""
                imported.add(name.split(".")[0])
                assert not any(
                    term in name
                    for term in ("portfolio", "execution", "model_selection", "ensemble")
                )
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in {"eval", "exec", "__import__", "compile"}
    assert not imported & banned

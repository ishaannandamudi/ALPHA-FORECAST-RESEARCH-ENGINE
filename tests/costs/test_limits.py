"""Lowerable runtime/read bounds, bounded lineage and no external executable boundary."""

import ast
from dataclasses import replace
from pathlib import Path

import pytest

from afre.costs import CostInputRole, CostResearchBounds, CostSensitivitySpec
from afre.costs.artifacts import CostAwareEvaluation
from afre.costs.lineage import audit_for
from afre.costs.schema import CostComponentType
from afre.schema import Artifact, ContractError
from afre.serialization import canonical_json
from examples.costs_workflow import assess
from tests.costs.conftest import CostCase


@pytest.mark.parametrize("field", ("components", "samples", "serialized_bytes"))
def test_lowered_scenario_read_write_bound(case: CostCase, field: str) -> None:
    case.repo.cost_research_bounds = replace(CostResearchBounds(), **{field: 1})
    with pytest.raises(ContractError, match="bound"):
        case.repo.get(type(case.fixture.scenario), case.fixture.scenario.fingerprint)
    with case.repo.transaction(), pytest.raises(ContractError, match="bound"):
        case.repo.put(case.fixture.scenario)


def test_artifact_family_limit_and_grid_bounds(case: CostCase) -> None:
    base = case.fixture.scenario
    case.repo.cost_research_bounds = replace(CostResearchBounds(), artifacts=1)
    with pytest.raises(ContractError, match="artifact bound"):
        case.engine.declare(replace(base, scenario_id="second"))
    case.repo.cost_research_bounds = replace(CostResearchBounds(), grid_points=1)
    spec = CostSensitivitySpec(
        base.fingerprint, base.components[0].fingerprint, (1.0, 2.0), (), (1.0,), 40
    )
    with pytest.raises(ContractError, match="sensitivity input bounds"):
        case.engine.register_sensitivity(spec)
    impact = next(c for c in base.components if c.component is CostComponentType.MARKET_IMPACT)
    spec = CostSensitivitySpec(
        base.fingerprint, impact.fingerprint, (1.0,), (0.01, 0.1), (1.0,), 40
    )
    case.repo.cost_research_bounds = replace(CostResearchBounds(), participation_rates=1)
    with pytest.raises(ContractError, match="sensitivity input bounds"):
        case.engine.register_sensitivity(spec)


@pytest.mark.parametrize("field", ("audit_nodes", "audit_depth"))
def test_lineage_node_depth_bounds(case: CostCase, field: str) -> None:
    result = assess(case.engine, case.fixture.scenario)[2]
    case.repo.cost_research_bounds = replace(CostResearchBounds(), **{field: 1})
    with pytest.raises(ContractError, match="node/depth bound"):
        audit_for(case.repo, result.fingerprint)


def test_lineage_canonical_byte_budget(case: CostCase) -> None:
    value = next(i for i in case.fixture.inputs if i.role is CostInputRole.MODEL_VALUE)
    case.repo.cost_research_bounds = replace(
        CostResearchBounds(),
        serialized_bytes=len(canonical_json(value).encode())
        + len(canonical_json(value.source).encode())
        - 1,
    )
    with pytest.raises(ContractError, match="lineage byte bound"):
        audit_for(case.repo, value.fingerprint)


def test_lineage_cycle_and_invalid_root(
    case: CostCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    import afre.costs.lineage as module

    value = case.fixture.inputs[0]
    original = module.cost_edges

    def cycle(v: Artifact) -> tuple[str, ...]:
        return (v.fingerprint,) if v == value else original(v)

    monkeypatch.setattr(module, "cost_edges", cycle)
    # Low-level structural projection would catch changed edges first; freeze that lookup
    # to isolate the DFS cycle assertion, without altering persisted SQL.
    getter = case.repo.get_any
    monkeypatch.setattr(
        case.repo, "get_any", lambda i: value if i == value.fingerprint else getter(i)
    )
    with pytest.raises(ContractError, match="cycle"):
        audit_for(case.repo, value.fingerprint)
    with pytest.raises(ContractError, match="composition root"):
        audit_for(case.repo, value.source.fingerprint)


def test_direct_external_dependencies_and_executables_absent() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "afre" / "costs"
    blocked = {
        "ame",
        "mce",
        "eie",
        "options",
        "tca",
        "socket",
        "urllib",
        "http",
        "requests",
        "subprocess",
        "pickle",
        "joblib",
        "importlib",
    }
    for p in root.glob("*.py"):
        tree = ast.parse(p.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(n.name.split(".")[0].lower() not in blocked for n in node.names)
            if isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0].lower() not in blocked
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in {"eval", "exec", "__import__", "open"}
    assert not hasattr(CostAwareEvaluation, "sharpe")


def test_complete_audit_exact_cost_truth_fit_and_cohort(case: CostCase) -> None:
    from afre.costs.artifacts import CostResearchAudit
    from afre.invariance import EnvironmentMembership

    result = assess(case.engine, case.fixture.scenario)[2]
    root = case.engine.breakeven(result.fingerprint, 100)
    audit = case.engine.audit(root.fingerprint)
    assert root.fingerprint in audit.node_ids
    assert result.fingerprint in audit.node_ids
    assert case.fixture.scenario.fingerprint in audit.node_ids
    assert any(i.startswith("afre.target_vintage:") for i in audit.node_ids)
    assert any(i.startswith("afre.m_fit_run:") for i in audit.node_ids)
    assert case.repo.resolve(CostResearchAudit, audit.fingerprint) == audit
    d = case.fixture.upstream.environment_set.definitions[0]
    members = tuple(
        i
        for i in case.fixture.upstream.membership_ids
        if case.repo.get(EnvironmentMembership, i).environment_id == d.fingerprint
    )
    cohort = case.engine.cohort(result.fingerprint, d.fingerprint, members, 100)
    assert d.fingerprint in case.engine.audit(cohort.fingerprint).node_ids
    with case.repo.feature_only(), pytest.raises(ContractError, match="metadata"):
        case.repo.resolve(CostResearchAudit, audit.fingerprint)

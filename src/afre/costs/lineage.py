"""Bounded unified source, scenario, cost, target, cohort and sealed TEST lineage."""

from typing import TYPE_CHECKING

from afre.calibration.artifacts import CalibrationState
from afre.costs.artifacts import (
    BreakEvenCostDiagnostic,
    CostAwareComparison,
    CostAwareEvaluation,
    CostAwareSampleEvaluation,
    CostCohortEvaluation,
    CostComponentEstimate,
    CostResearchAudit,
    CostSensitivityCurve,
    ResearchExposureChange,
    ResearchExposurePath,
    TotalCostEstimate,
)
from afre.costs.cost_inputs import CostInputReference
from afre.costs.definitions import CostScenario, CostSensitivitySpec
from afre.invariance.lineage import invariance_edges
from afre.orthogonalization.lineage import orthogonalization_edges
from afre.probabilistic.artifacts import ProbabilisticModelArtifact
from afre.schema import Artifact, require
from afre.serialization import canonical_json
from afre.statistical_models.artifacts import FittedModelArtifact
from afre.uncertainty.lineage import old_edges, uncertainty_edges

if TYPE_CHECKING:
    from afre.costs.repository import CostResearchRepository


def cost_edges(v: Artifact) -> tuple[str, ...]:
    if isinstance(v, CostInputReference):
        return (
            v.source.fingerprint,
            *(
                (v.clocks.historical_delivery.fingerprint,)
                if v.clocks.historical_delivery
                else ()
            ),
        )
    if isinstance(v, CostScenario):
        return (
            v.target.fingerprint,
            v.fold_id,
            v.exposure_rule.fingerprint,
            *(c.fingerprint for c in v.components),
            *v.source_ids,
            *v.sample_ids,
            *v.uncertainty_ids,
            *(i for b in v.bindings for i in b.input_ids),
            *(
                i
                for a in v.liquidity
                for i in (a.price_input_id, a.notional_input_id, a.volume_input_id)
                if i
            ),
        )
    if isinstance(v, CostSensitivitySpec):
        return v.scenario_id, v.component_id
    if isinstance(v, ResearchExposureChange):
        return v.scenario_id, v.sample_id, v.source_id
    if isinstance(v, ResearchExposurePath):
        return v.scenario_id, *v.change_ids
    if isinstance(v, CostComponentEstimate):
        return v.scenario_id, v.change_id, v.component_id, *v.input_ids, *v.liquidity_input_ids
    if isinstance(v, TotalCostEstimate):
        return v.scenario_id, v.change_id, *v.component_ids
    if isinstance(v, CostAwareSampleEvaluation):
        return (
            v.scenario_id,
            v.change_id,
            v.total_cost_id,
            v.sample_id,
            v.source_id,
            *((v.truth_id,) if v.truth_id else ()),
            *v.uncertainty_ids,
        )
    if isinstance(v, CostAwareEvaluation):
        return (
            v.scenario_id,
            v.path_id,
            *v.sample_evaluation_ids,
            *((v.test_evaluation_id,) if v.test_evaluation_id else ()),
        )
    if isinstance(v, BreakEvenCostDiagnostic):
        return v.evaluation_id, *((v.component_id,) if v.component_id else ())
    if isinstance(v, CostSensitivityCurve):
        return v.evaluation_id, v.spec_id
    if isinstance(v, CostAwareComparison):
        return v.left_id, v.right_id
    if isinstance(v, CostCohortEvaluation):
        return v.evaluation_id, v.environment_id, *v.membership_ids
    if isinstance(v, CostResearchAudit):
        return (v.root_id,)
    return ()


def audit_for(repo: "CostResearchRepository", root_id: str) -> CostResearchAudit:
    require(
        root_id.startswith("afre.cost_") and not root_id.startswith("afre.cost_audit:"),
        "cost research audit composition root required",
    )
    b = repo.cost_research_bounds
    seen: set[str] = set()
    active: set[str] = set()
    size = 0

    def visit(identity: str, depth: int) -> None:
        nonlocal size
        require(identity not in active, "cost research lineage cycle")
        if identity in seen:
            return
        require(
            depth <= b.audit_depth and len(seen) + len(active) < b.audit_nodes,
            "cost research lineage node/depth bound",
        )
        active.add(identity)
        value = repo.get_any(identity)
        repo._validate_links(value)
        edges = (
            cost_edges(value)
            if identity.startswith("afre.cost_")
            else invariance_edges(value)
            if identity.startswith("afre.inv_")
            else orthogonalization_edges(value)
            if identity.startswith("afre.ort_")
            else uncertainty_edges(value)
            if identity.startswith("afre.unc_")
            else old_edges(repo, value)
        )
        for edge in sorted(set(edges)):
            visit(edge, depth + 1)
        if isinstance(
            value, (FittedModelArtifact, ProbabilisticModelArtifact, CalibrationState)
        ):
            table, column = (
                ("m_fits", "artifact_id")
                if isinstance(value, FittedModelArtifact)
                else ("p_fits", "artifact_id")
                if isinstance(value, ProbabilisticModelArtifact)
                else ("c_fits", "state_id")
            )
            runs = repo._connection.execute(
                f"SELECT fingerprint FROM {table} WHERE {column}=?", (identity,)
            ).fetchall()
            require(len(runs) == 1, "cost research lineage requires completed native fit")
            run_id = runs[0][0]
            repo._validate_links(repo.get_any(run_id))
            if run_id not in seen:
                seen.add(run_id)
                size += len(canonical_json(repo.get_any(run_id)).encode())
        active.remove(identity)
        seen.add(identity)
        size += len(canonical_json(value).encode())
        require(size <= b.serialized_bytes, "cost research lineage byte bound")

    visit(root_id, 0)
    return CostResearchAudit(
        root_id,
        tuple(seen),
        (
            "hypothetical-research-evaluation-not-execution-fills-live-PnL-or-capacity",
            "explicit-source-units-applicability-side-round-trip-and-fallback-settings",
            "absolute-exposure-change-turnover-no-implicit-terminal-liquidation",
            "gross-and-net-arithmetic-contributions-kept-separate-no-compounding",
            "historical-causal-versus-ex-post-cost-evidence-distinct-six-clocks-preserved",
            "qualified-historical-delivery-never-pretends-actual-AFRE-ingestion-was-earlier",
            "frozen-scenario-and-supplied-sensitivity-grid-before-held-out-assessment",
            "no-TEST-cost-tuning-model-selection-portfolio-optimization-or-order-actions",
            "exact-PIT-environment-and-uncertainty-evidence-no-automatic-cost-from-variance",
            "bounded-unified-native-TRAIN-source-cost-truth-and-TEST-lineage",
        ),
    )

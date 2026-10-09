"""Bounded combined AFRE0..19 lineage; no executable audit payloads."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from afre.calibration.artifacts import CalibrationState
from afre.costs.lineage import cost_edges
from afre.invariance.lineage import invariance_edges
from afre.multiple_testing.diagnostics import (
    DeflatedPerformanceDiagnostic,
    ResearchOverfittingDiagnostic,
)
from afre.multiple_testing.effects import EffectSizeResult
from afre.multiple_testing.evaluations import AdjustedHypothesisResult, FamilyAnalysis
from afre.multiple_testing.families import FamilyAnalysisSpec, HypothesisFamily
from afre.multiple_testing.hypotheses import HypothesisDefinition
from afre.multiple_testing.pvalues import PValueResult
from afre.multiple_testing.registry import TrialRegistrySnapshot
from afre.multiple_testing.selection_bias import SelectionBiasDiagnostic, SelectionEvent
from afre.multiple_testing.test_reuse import TestReuseDiagnostic
from afre.multiple_testing.trials import ResearchTrial, TrialSpecification
from afre.orthogonalization.lineage import orthogonalization_edges
from afre.probabilistic.artifacts import ProbabilisticModelArtifact
from afre.schema import Artifact, contract, require
from afre.serialization import canonical_json
from afre.statistical_models.artifacts import FittedModelArtifact
from afre.uncertainty.lineage import old_edges, uncertainty_edges

if TYPE_CHECKING:
    from afre.multiple_testing.repository import MultipleTestingRepository


@contract("mt_audit")
@dataclass(frozen=True, slots=True)
class MultipleTestingAudit(Artifact):
    root_id: str
    node_ids: tuple[str, ...]
    limitations: tuple[str, ...]

    def _normalize(self) -> None:
        object.__setattr__(self, "node_ids", tuple(sorted(self.node_ids)))


def testing_edges(v: Artifact) -> tuple[str, ...]:
    if isinstance(v, HypothesisDefinition):
        return v.target_id, v.assumptions.fingerprint
    if isinstance(v, TrialSpecification):
        return (
            v.hypothesis_id,
            v.source_artifact_id,
            v.dataset_id,
            v.fold_id,
            *v.source_ids,
            *v.right_source_ids,
            *v.sample_ids,
            *v.preprocessing_ids,
            *v.model_spec_ids,
            *v.known_trial_ids,
            *v.membership_ids,
            *((v.environment_id,) if v.environment_id else ()),
            *((v.cost_scenario_id,) if v.cost_scenario_id else ()),
        )
    if isinstance(v, HypothesisFamily):
        return v.plan_ids
    if isinstance(v, ResearchTrial):
        return (
            v.plan_id,
            v.family_id,
            v.hypothesis_id,
            *v.native_result_ids,
            *v.test_seal_ids,
            *(o.truth_id for o in v.observations),
            *(o.source_id for o in v.observations),
            *(o.right_source_id for o in v.observations if o.right_source_id),
            *(o.native_evaluation_id for o in v.observations if o.native_evaluation_id),
        )
    if isinstance(v, (PValueResult, EffectSizeResult)):
        return v.trial_id, v.hypothesis_id
    if isinstance(v, FamilyAnalysisSpec):
        return v.family_id, *v.trial_ids
    if isinstance(v, AdjustedHypothesisResult):
        return (
            v.analysis_spec_id,
            v.family_id,
            v.plan_id,
            v.hypothesis_id,
            *((v.trial_id,) if v.trial_id else ()),
            *((v.pvalue_id,) if v.pvalue_id else ()),
            *((v.effect_id,) if v.effect_id else ()),
        )
    if isinstance(v, FamilyAnalysis):
        return v.spec_id, v.family_id, *v.adjusted_ids
    if isinstance(v, TrialRegistrySnapshot):
        return (
            *v.trial_ids,
            *v.plan_ids,
            *v.family_ids,
            *v.selection_event_ids,
            *v.native_test_seal_ids,
        )
    if isinstance(v, TestReuseDiagnostic):
        return v.registry_id, v.policy_id, v.trial_id, *v.scope_trial_ids, *v.untracked_seal_ids
    if isinstance(v, SelectionEvent):
        return v.candidate_trial_ids
    if isinstance(v, SelectionBiasDiagnostic):
        return v.event_id, v.analysis_id, v.registry_id, *v.adjusted_result_ids
    if isinstance(v, (ResearchOverfittingDiagnostic, DeflatedPerformanceDiagnostic)):
        return (v.registry_id,)
    if isinstance(v, MultipleTestingAudit):
        return (v.root_id,)
    return ()


def audit_for(repo: "MultipleTestingRepository", root_id: str) -> MultipleTestingAudit:
    require(
        root_id.startswith("afre.mt_") and not root_id.startswith("afre.mt_audit:"),
        "multiple testing composition audit root",
    )
    b = repo.multiple_testing_bounds
    seen: set[str] = set()
    active: set[str] = set()
    size = 0

    def visit(identity: str, depth: int) -> None:
        nonlocal size
        require(identity not in active, "multiple testing lineage cycle")
        if identity in seen:
            return
        require(
            depth <= b.audit_depth and len(seen) + len(active) < b.audit_nodes,
            "multiple testing audit node/depth bound",
        )
        active.add(identity)
        value = repo.get_any(identity)
        edges = (
            testing_edges(value)
            if identity.startswith("afre.mt_")
            else cost_edges(value)
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
            require(len(runs) == 1, "multiple testing requires completed native fit")
            run_id = runs[0][0]
            run = repo.get_any(run_id)
            repo._validate_links(run)
            if run_id not in seen:
                require(len(seen) + len(active) < b.audit_nodes, "native fit node bound")
                seen.add(run_id)
                size += len(canonical_json(run).encode())
        active.remove(identity)
        seen.add(identity)
        size += len(canonical_json(value).encode())
        require(size <= b.serialized_bytes, "multiple testing audit byte bound")

    visit(root_id, 0)
    return MultipleTestingAudit(
        root_id,
        tuple(seen),
        (
            "conditional-sign-null-and-independence-are-caller-attested",
            "corrections-do-not-remove-leakage-adaptive-data-snooping-or-nonstationarity",
            "p-values-and-effects-remain-separate-no-causality-or-profitability-proof",
            "complete-declared-opportunities-include-failed-and-missing-attempts",
            "native-TEST-seals-reuse-and-unknown-history-remain-visible",
            "no-model-selection-promotion-pruning-portfolio-or-execution",
            "unsupported-Sharpe-deflation-normal-mean-correlation-and-effect-CI",
        ),
    )

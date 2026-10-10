"""Bounded selection lineage with separate numeric witnesses and split metadata."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from afre.costs.lineage import cost_edges
from afre.invariance.lineage import invariance_edges
from afre.multiple_testing.lineage import testing_edges
from afre.orthogonalization.lineage import orthogonalization_edges
from afre.research_datasets.manifests import ResearchDatasetManifest
from afre.research_datasets.samples import ResearchSample, ResearchSelection
from afre.schema import Artifact, contract, require
from afre.selection.definitions import (
    CandidateFamilyPlan,
    CandidateSpec,
    NativeCandidateRecipe,
    SearchSpace,
    SelectionRequest,
)
from afre.selection.guards import read_role
from afre.selection.registry import CandidateRegistrySnapshot
from afre.selection.results import (
    CandidateFitResult,
    CandidateValidationResult,
    SelectionResult,
)
from afre.selection.schema import SelectionReadRole
from afre.serialization import canonical_json
from afre.target_engine.market_data import TargetSourceBuild
from afre.uncertainty.lineage import old_edges, uncertainty_edges

if TYPE_CHECKING:
    from afre.selection.repository import SelectionRepository


@contract("sel_audit")
@dataclass(frozen=True, slots=True)
class SelectionAudit(Artifact):
    root_id: str
    node_ids: tuple[str, ...]
    serialized_bytes: int
    limitations: tuple[str, ...]

    def _normalize(self) -> None:
        object.__setattr__(self, "node_ids", tuple(sorted(self.node_ids)))

    def _validate(self) -> None:
        require(
            len(self.node_ids) == len(set(self.node_ids)) <= 100000
            and self.serialized_bytes >= 0,
            "audit bounds",
        )


def selection_edges(v: Artifact) -> tuple[str, ...]:
    if isinstance(v, SearchSpace):
        return (
            v.target_id,
            v.horizon_id,
            v.dataset_id,
            v.fold_id,
            v.budget.fingerprint,
            *(r.fingerprint for r in v.recipes),
            *v.validation_sample_ids,
            *v.failure_anchor_source_ids,
        )
    if isinstance(v, NativeCandidateRecipe):
        return (
            *v.train_input_ids,
            *v.preprocessing_ids,
            *v.feature_ids,
            *v.orthogonal_feature_ids,
            *v.diagnostic_ids,
            *(i for pair in (*v.train_bindings, *v.validation_bindings) for i in pair),
        )
    if isinstance(v, CandidateSpec):
        return v.search_space_id, v.recipe.fingerprint
    if isinstance(v, SelectionRequest):
        return (v.search_space_id,)
    if isinstance(v, CandidateFamilyPlan):
        return v.request_id, v.search_space_id, *v.candidate_ids
    if isinstance(v, CandidateFitResult):
        return (
            v.candidate_id,
            *v.preprocessing_ids,
            *v.forecast_ids,
            *((v.model_id,) if v.model_id else ()),
        )
    if isinstance(v, CandidateValidationResult):
        return v.candidate_id, v.fit_id, v.trial_id, *(p.truth_id for p in v.pairs)
    if isinstance(v, SelectionResult):
        return (
            v.request_id,
            v.search_space_id,
            v.family_plan_id,
            v.multiple_testing_family_id,
            *v.validation_ids,
            *((v.multiple_testing_event_id,) if v.multiple_testing_event_id else ()),
        )
    if isinstance(v, CandidateRegistrySnapshot):
        return v.selection_id, *(e.validation_id for e in v.entries)
    if isinstance(v, SelectionAudit):
        return (v.root_id,)
    from afre.selection.orthogonal_features import OrthogonalFeatureBinding

    if isinstance(v, OrthogonalFeatureBinding):
        return v.residual_id, v.scalar_id
    from afre.selection.comparisons import CandidateComparison

    if isinstance(v, CandidateComparison):
        return v.left_validation_id, v.right_validation_id
    return ()


def audit_for(repo: "SelectionRepository", root_id: str) -> SelectionAudit:
    root = repo.get_any(root_id)
    require(
        isinstance(root, (SelectionResult, CandidateRegistrySnapshot)), "selection audit root"
    )
    assert isinstance(root, (SelectionResult, CandidateRegistrySnapshot))
    space = repo.get(SearchSpace, root.search_space_id)
    seen: set[str] = set()
    active: set[str] = set()
    size = 0
    from afre.target_engine.definitions import TargetDefinition

    target = repo.get(TargetDefinition, space.target_id)
    embedded = {
        space.horizon_id: target.horizon,
        **{r.native_spec.fingerprint: r.native_spec for r in space.recipes},
    }
    b = repo.selection_bounds

    def visit(identity: str, depth: int) -> None:
        nonlocal size
        require(identity not in active, "selection audit cycle")
        if identity in seen:
            return
        require(
            depth <= b.lineage_depth and len(seen) + len(active) < b.lineage_nodes,
            "selection audit node/depth bound",
        )
        active.add(identity)
        v = embedded[identity] if identity in embedded else repo.get_any(identity)
        size += len(canonical_json(v).encode())
        require(size <= b.payload_bytes, "selection audit byte bound")
        if isinstance(v, ResearchSample):
            # Exact selected truth is reached via validation pair, not every
            # dataset sample's later truth or a global TEST registry.
            edges = tuple(i for i in old_edges(repo, v) if i != v.target_id)
        elif isinstance(v, ResearchDatasetManifest):
            edges = (v.definition_id,)
        elif isinstance(v, ResearchSelection):
            edges = tuple(i for i in old_edges(repo, v) if i != v.request.target_dataset_id)
        elif isinstance(v, TargetSourceBuild):
            edges = (v.source.fingerprint,)

        else:
            edges = (
                selection_edges(v)
                if identity.startswith("afre.sel_")
                else testing_edges(v)
                if identity.startswith("afre.mt_")
                else cost_edges(v)
                if identity.startswith("afre.cost_")
                else invariance_edges(v)
                if identity.startswith("afre.inv_")
                else orthogonalization_edges(v)
                if identity.startswith("afre.ort_")
                else uncertainty_edges(v)
                if identity.startswith("afre.unc_")
                else old_edges(repo, v)
            )
        for i in sorted(set(edges)):
            visit(i, depth + 1)
        active.remove(identity)
        seen.add(identity)

    with read_role(repo, SelectionReadRole.VALIDATION, space):
        visit(root_id, 0)
    return SelectionAudit(
        root_id,
        tuple(seen),
        size,
        (
            "split-geometry-is-metadata;TEST-response-nodes-excluded",
            "validation-selection-does-not-prove-generalization-or-profitability",
        ),
    )

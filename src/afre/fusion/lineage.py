"""Bounded frozen evidence graph; post-hoc truth stays separate from application."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from afre.fusion.artifacts import (
    FrozenFusionTestChoice,
    FusedForecast,
    FusionArtifact,
    FusionObservation,
)
from afre.fusion.definitions import FusionSourceReference, FusionSpec
from afre.fusion.diagnostics import DiversityMatrix, FusionComparison, FusionWeightStability
from afre.fusion.external import ExternalFusionDefinition, ExternalFusionOutput
from afre.fusion.metadata import FusionMetadata
from afre.schema import Artifact, contract, require
from afre.serialization import canonical_json

if TYPE_CHECKING:
    from afre.fusion.repository import FusionRepository


@contract("fus_audit")
@dataclass(frozen=True, slots=True)
class FusionAudit(Artifact):
    root_id: str
    node_ids: tuple[str, ...]
    serialized_bytes: int
    limitations: tuple[str, ...]

    def _normalize(self) -> None:
        object.__setattr__(self, "node_ids", tuple(sorted(self.node_ids)))

    def _validate(self) -> None:
        require(
            self.root_id in self.node_ids
            and len(set(self.node_ids)) == len(self.node_ids)
            and self.serialized_bytes > 0,
            "fusion audit exact root/bounds",
        )


def fusion_edges(v: Artifact) -> tuple[str, ...]:
    if isinstance(v, FusionMetadata):
        return v.forecast_id, *v.diagnostic_ids
    if isinstance(v, FusionSourceReference):
        return v.anchor_output_id, v.artifact_id, v.spec_id, v.target_id
    if isinstance(v, FusionSpec):
        return (
            *v.source_ids,
            v.target_id,
            v.fold_id,
            v.dataset_id,
            *((v.fallback_source_id,) if v.fallback_source_id else ()),
            *((v.source_selection_result_id,) if v.source_selection_result_id else ()),
        )
    if isinstance(v, FusionObservation):
        return v.source_id, v.output_id, v.sample_id
    if isinstance(v, ExternalFusionDefinition):
        return v.target.fingerprint, v.source.fingerprint, *v.base_train_sample_ids
    if isinstance(v, ExternalFusionOutput):
        return v.definition_id, v.sample_id
    if isinstance(v, FusionArtifact):
        return (
            v.spec_id,
            *(i for r in v.rows for i in r.observation_ids),
            *(r.target_id for r in v.rows if r.target_id),
            *(r.sample_id for r in v.rows),
        )
    if isinstance(v, FusedForecast):
        return (
            v.artifact_id,
            v.sample_id,
            *v.observation_ids,
            *((v.fallback_observation_id,) if v.fallback_observation_id else ()),
        )
    if isinstance(v, DiversityMatrix):
        return (*v.source_ids, *v.observation_ids, *v.truth_ids)
    if isinstance(v, FusionComparison):
        return (
            *v.forecast_ids,
            *((v.trial_pool_id,) if v.trial_pool_id else ()),
            *(p.truth_id for p in v.pairs),
            *(
                (v.test_choice_id, v.test_evaluation_id)
                if v.test_choice_id and v.test_evaluation_id
                else ()
            ),
        )
    if isinstance(v, FrozenFusionTestChoice):
        return (v.artifact_id,)
    if isinstance(v, FusionWeightStability):
        return v.artifact_ids
    if isinstance(v, FusionAudit):
        return (v.root_id,)
    from afre.fusion.accounting import FusionTrialPool

    if isinstance(v, FusionTrialPool):
        return v.family_id, *v.spec_ids, *v.plan_ids
    return ()


def audit_for(repo: "FusionRepository", root_id: str) -> FusionAudit:
    from afre.costs.lineage import cost_edges
    from afre.invariance.lineage import invariance_edges
    from afre.multiple_testing.lineage import testing_edges
    from afre.orthogonalization.lineage import orthogonalization_edges
    from afre.research_datasets.manifests import ResearchDatasetManifest
    from afre.research_datasets.samples import ResearchSample, ResearchSelection
    from afre.selection.lineage import selection_edges
    from afre.target_engine.market_data import TargetSourceBuild
    from afre.uncertainty.lineage import old_edges, uncertainty_edges

    seen: set[str] = set()
    active: set[str] = set()
    size = 0
    b = repo.fusion_bounds

    def visit(identity: str, depth: int) -> None:
        nonlocal size
        require(identity not in active, "fusion lineage cycle")
        if identity in seen:
            return
        require(
            depth <= b.lineage_depth and len(active) + len(seen) < b.lineage_nodes,
            "fusion lineage node/depth bound",
        )
        active.add(identity)
        value = repo.get_any(identity)
        size += len(canonical_json(value).encode())
        require(size <= b.payload_bytes, "fusion lineage byte bound")
        if isinstance(value, ResearchSample):
            edges = tuple(i for i in old_edges(repo, value) if i != value.target_id)
        elif isinstance(value, ResearchSelection):
            edges = tuple(
                i for i in old_edges(repo, value) if i != value.request.target_dataset_id
            )
        elif isinstance(value, ResearchDatasetManifest):
            edges = (value.definition_id,)
        elif isinstance(value, TargetSourceBuild):
            edges = (value.source.fingerprint,)
        else:
            edges = (
                fusion_edges(value)
                if identity.startswith("afre.fus_")
                else selection_edges(value)
                if identity.startswith("afre.sel_")
                else testing_edges(value)
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
        for i in sorted(set(edges)):
            visit(i, depth + 1)
        active.remove(identity)
        seen.add(identity)

    visit(root_id, 0)
    return FusionAudit(
        root_id,
        tuple(seen),
        size,
        (
            "TRAIN weights; target-free application; post-hoc truth explicit",
            "diversity is descriptive; no significance or profitability claim",
            "fusion does not select source subsets or trigger model health/promotion",
        ),
    )

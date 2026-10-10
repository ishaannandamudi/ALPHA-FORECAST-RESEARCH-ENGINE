"""Bounded replayable health evidence, native lineage and explicit no-action assertions."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from afre.fusion.lineage import fusion_edges
from afre.health.artifacts import (
    HealthDecayTrend,
    HealthMetric,
    HealthObservation,
    ModelHealthSnapshot,
)
from afre.health.definitions import HealthSpec, MonitoredArtifactReference
from afre.schema import Artifact, contract, require
from afre.serialization import canonical_json

if TYPE_CHECKING:
    from afre.health.repository import HealthRepository


@contract("hlt_audit")
@dataclass(frozen=True, slots=True)
class HealthAudit(Artifact):
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
            and 0 < len(self.node_ids) <= 100000
            and 0 < self.serialized_bytes <= 16 * 1024 * 1024,
            "health audit exact root/nodes/bytes",
        )


def health_edges(value: Artifact) -> tuple[str, ...]:
    if isinstance(value, MonitoredArtifactReference):
        return (
            value.artifact_id,
            value.producer_id,
            value.target_id,
            *((value.anchor_output_id,) if value.anchor_output_id else ()),
        )
    if isinstance(value, HealthSpec):
        return (
            value.reference_id,
            value.target_id,
            value.reference_window.fingerprint,
            value.current_window.fingerprint,
            value.bounds.fingerprint,
            *(r.fingerprint for r in value.requests),
            *(i for _, i in value.rule_bindings),
            *value.reference_observation_ids,
            *value.current_observation_ids,
            *value.comparison_reference_ids,
            *value.membership_ids,
            *value.context_ids,
            *((value.environment_id,) if value.environment_id else ()),
            *((value.test_evaluation_id,) if value.test_evaluation_id else ()),
        )
    if isinstance(value, HealthObservation):
        return (
            value.reference_id,
            value.source_id,
            *((value.sample_id,) if value.sample_id else ()),
        )
    if isinstance(value, HealthMetric):
        return (
            value.spec_id,
            value.request_id,
            *value.reference_observation_ids,
            *value.current_observation_ids,
            *value.truth_ids,
            *((value.rule_id,) if value.rule_id else ()),
        )
    if isinstance(value, ModelHealthSnapshot):
        return (value.spec_id, *value.metric_ids, *value.rule_ids)
    if isinstance(value, HealthDecayTrend):
        return value.metric_ids
    if isinstance(value, HealthAudit):
        return (value.root_id,)
    return ()


def audit_for(repo: "HealthRepository", root_id: str) -> HealthAudit:
    from afre.costs.lineage import cost_edges

    require(
        root_id.startswith("afre.hlt_") and not root_id.startswith("afre.hlt_audit:"),
        "health composition audit root required",
    )
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
    b = repo.health_bounds

    def visit(identity: str, depth: int) -> None:
        nonlocal size
        require(identity not in active, "health lineage cycle")
        if identity in seen:
            return
        require(
            depth <= b.lineage_depth and len(active) + len(seen) < b.lineage_nodes,
            "health lineage node/depth bound",
        )
        active.add(identity)
        value = repo.get_any(identity)
        size += len(canonical_json(value).encode())
        require(size <= b.lineage_bytes, "health lineage byte bound")
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
                health_edges(value)
                if identity.startswith("afre.hlt_")
                else fusion_edges(value)
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
    return HealthAudit(
        root_id,
        tuple(seen),
        size,
        (
            (
                "input/prediction drift separate from truth-gated performance; "
                "exact declared windows/rules"
            ),
            (
                "health states are descriptive; no causal, significance, "
                "profitability or health-confidence claim"
            ),
            (
                "no retraining, recalibration, weight change, replacement, "
                "promotion, retirement, routing or notification"
            ),
        ),
    )

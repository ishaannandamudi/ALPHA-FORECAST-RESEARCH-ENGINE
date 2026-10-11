"""Bounded immutable audit of exact program, participant and native evidence lineage."""

from dataclasses import dataclass, fields
from typing import TYPE_CHECKING

from afre.fusion.lineage import fusion_edges
from afre.health.lineage import health_edges
from afre.schema import Artifact, contract, require
from afre.serialization import canonical_json

if TYPE_CHECKING:
    from afre.challenger.repository import ChallengeRepository


@contract("ch_audit")
@dataclass(frozen=True, slots=True)
class ChallengeAudit(Artifact):
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
            "challenge audit bounds/root",
        )


def challenge_edges(value: Artifact) -> tuple[str, ...]:
    if isinstance(value, ChallengeAudit):
        return (value.root_id,)
    result: set[str] = set()

    def visit(item: object) -> None:
        if isinstance(item, Artifact):
            result.add(item.fingerprint)
        elif isinstance(item, str) and item.startswith("afre."):
            # Horizons are embedded in native target definitions, not separately stored.
            if not item.startswith("afre.horizon:"):
                result.add(item)
        elif isinstance(item, tuple):
            for child in item:
                visit(child)

    for field in fields(value):
        if field.name not in ("law_id", "horizon_id", "security_id"):
            visit(getattr(value, field.name))
    return tuple(sorted(result))


def audit_for(repo: "ChallengeRepository", root_id: str) -> ChallengeAudit:
    from afre.costs.lineage import cost_edges

    require(
        root_id.startswith("afre.ch_") and not root_id.startswith("afre.ch_audit:"),
        "challenge composition audit root required",
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
    b = repo.challenge_bounds

    def visit(identity: str, depth: int) -> None:
        nonlocal size
        require(identity not in active, "challenge lineage cycle")
        if identity in seen:
            return
        require(
            depth <= b.lineage_depth and len(active) + len(seen) < b.lineage_nodes,
            "challenge lineage node/depth bound",
        )
        active.add(identity)
        value = repo.get_any(identity)
        size += len(canonical_json(value).encode())
        require(size <= b.lineage_bytes, "challenge lineage byte bound")
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
                challenge_edges(value)
                if identity.startswith("afre.ch_")
                else health_edges(value)
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
    return ChallengeAudit(
        root_id,
        tuple(seen),
        size,
        (
            (
                "explicit champion/challengers; target-free shadow generation; "
                "exact common sample/truth support and frozen criteria"
            ),
            (
                "health, costs and research history remain separate evidence; "
                "no automatic significance or profitability claim"
            ),
            (
                "MANUAL_ONLY advice; no retraining, recalibration, fusion change, "
                "deployment, champion replacement or rollback action"
            ),
        ),
    )

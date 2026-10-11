"""Bounded raw evidence traversal; TRAIN fit inputs and later truth are opaque leaves."""

import re
from dataclasses import fields
from typing import TYPE_CHECKING

from afre.schema import Artifact, require
from afre.serialization import canonical_json
from afre.service.snapshots import SnapshotLineage

if TYPE_CHECKING:
    from afre.service.repository import ServiceRepository

SKIP_FIELDS = {
    "target_id",
    "target_ids",
    "truth_ids",
    "truth_assignments",
    "rows",
    "train_sample_ids",
    "dataset_id",
    "target_dataset_id",
    "split_id",
    "fold_id",
    "memberships",
    "assignments",
    "evidence_id",
    "common_id",
    "metric_ids",
    "promotion_ids",
    "rollback_ids",
    "comparison_ids",
}
LEAVES = {
    "FittedModelArtifact",
    "ProbabilisticModelArtifact",
    "CalibrationState",
    "GateModelArtifact",
    "FixedGateSpec",
    "LearnedGateSpec",
    "EventConditionedModel",
    "RegimeConditionedModel",
    "NonlinearModelArtifact",
    "SequenceModelArtifact",
    "ProjectionArtifact",
    "FusionArtifact",
    "ForecastUncertaintyDecomposition",
    "ModelHealthSnapshot",
    "ChallengeRun",
    "ChallengeProgram",
    "ResearchInputBuild",
    "ResearchDatasetManifest",
    "ResearchSplit",
    "ModelFitInputs",
    "TrainingDistribution",
    "DesignMatrix",
    "FoldPreprocessingState",
    "UniverseSnapshot",
}


def reference_ids(value: Artifact) -> tuple[str, ...]:
    result: set[str] = set()

    def visit(item: object, reference: bool = False) -> None:
        if isinstance(item, Artifact):
            for f in fields(item):
                if f.name not in SKIP_FIELDS:
                    visit(getattr(item, f.name), f.name.endswith(("_id", "_ids")))
        elif isinstance(item, tuple):
            for child in item:
                visit(child, reference)
        elif (
            reference
            and isinstance(item, str)
            and re.fullmatch(r"afre\.[a-z_]+:1\.0:[0-9a-f]{64}", item)
            and not item.startswith("afre.target_vintage:")
        ):
            result.add(item)

    visit(value)
    return tuple(sorted(result))


def lineage_for(
    repo: "ServiceRepository", root: str, additional: tuple[str, ...]
) -> SnapshotLineage:
    key = (root, tuple(sorted(set(additional))))
    if repo._service_request_depth and key in repo._service_graphs:
        return repo._service_graphs[key]
    result = _lineage_for(repo, root, key[1])
    if repo._service_request_depth:
        repo._service_graphs[key] = result
    return result


def _lineage_for(
    repo: "ServiceRepository", root: str, additional: tuple[str, ...]
) -> SnapshotLineage:
    b = repo.service_bounds
    seen: set[str] = set()
    active: set[str] = set()
    edges: set[tuple[str, str]] = set()
    reconstructed: set[str] = set()
    size = 0

    def walk(identity: str, depth: int) -> None:
        nonlocal size
        require(identity not in active, "service lineage cycle")
        if identity in seen:
            return
        require(
            depth <= b.lineage_depth and len(seen) + len(active) < b.lineage_nodes,
            "service lineage depth/node bound",
        )
        raw = repo.raw(identity)
        size += len(canonical_json(raw).encode())
        require(size <= b.lineage_bytes, "service lineage byte bound")
        active.add(identity)

        # Existing qualified delivery contracts keep actual receipt/ingestion clocks intact.
        def evidence(item: object) -> None:
            if isinstance(item, Artifact):
                if type(item).__name__ == "QualifiedHistoricalDelivery":
                    reconstructed.add(item.fingerprint)
                for f in fields(item):
                    if f.name not in SKIP_FIELDS:
                        evidence(getattr(item, f.name))
            elif isinstance(item, tuple):
                for child in item:
                    evidence(child)

        evidence(raw)
        if type(raw).__name__ not in LEAVES:
            for child in reference_ids(raw):
                # Embedded law/security/horizon contracts are covered by parent's bytes.
                if repo.exists(child):
                    walk(child, depth + 1)
                    edges.add((identity, child))
        active.remove(identity)
        seen.add(identity)

    walk(root, 0)
    for identity in sorted(set(additional)):
        walk(identity, 1)
        if identity != root:
            edges.add((root, identity))
    return SnapshotLineage(root, tuple(seen), tuple(edges), size, tuple(reconstructed))

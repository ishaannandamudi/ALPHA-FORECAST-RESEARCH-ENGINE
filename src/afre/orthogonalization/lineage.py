"""Bounded unified projection/source/TRAIN/evaluation provenance; audit may read later truth."""

from typing import TYPE_CHECKING

from afre.calibration.artifacts import CalibrationState
from afre.orthogonalization.artifacts import (
    AlignedSignalRow,
    OrthogonalizationAudit,
    OrthogonalSignalValue,
    ProjectionArtifact,
    RedundancyMatrix,
)
from afre.orthogonalization.definitions import OrthogonalizationSpec, SignalReference
from afre.orthogonalization.evaluation_artifacts import (
    PartialCorrelation,
    PredictiveModelPair,
    RedundancyEvaluation,
    RedundancyStability,
)
from afre.orthogonalization.signals import GenericSignalSource, SignalObservation
from afre.probabilistic.artifacts import ProbabilisticModelArtifact
from afre.schema import Artifact, require
from afre.serialization import canonical_json
from afre.statistical_models.artifacts import FittedModelArtifact
from afre.uncertainty.lineage import old_edges, uncertainty_edges

if TYPE_CHECKING:
    from afre.orthogonalization.repository import OrthogonalizationRepository


def orthogonalization_edges(v: Artifact) -> tuple[str, ...]:
    if isinstance(v, SignalReference):
        return (v.target.fingerprint,) if v.target else ()
    if isinstance(v, GenericSignalSource):
        return (
            v.reference.fingerprint,
            v.source.fingerprint,
            *(
                (v.clocks.historical_delivery.fingerprint,)
                if v.clocks.historical_delivery
                else ()
            ),
        )
    if isinstance(v, SignalObservation):
        return v.reference_id, v.source_id, v.sample_id
    if isinstance(v, OrthogonalizationSpec):
        return (
            v.candidate.fingerprint,
            *(r.fingerprint for r in v.references),
            v.fold_id,
            v.target.fingerprint,
        )
    if isinstance(v, AlignedSignalRow):
        return v.spec_id, v.sample_id, *v.observation_ids
    if isinstance(v, RedundancyMatrix):
        return v.spec_id, *v.row_ids
    if isinstance(v, ProjectionArtifact):
        return v.spec_id, v.matrix_id, *v.row_ids
    if isinstance(v, OrthogonalSignalValue):
        return v.projection_id, v.row_id, v.sample_id
    if isinstance(v, PredictiveModelPair):
        return v.projection_id, *v.row_ids, *v.target_ids
    if isinstance(v, RedundancyEvaluation):
        return (
            v.projection_id,
            *v.residual_ids,
            *v.target_ids,
            *((v.predictive_pair_id,) if v.predictive_pair_id else ()),
            *((v.test_evaluation_id,) if v.test_evaluation_id else ()),
        )
    if isinstance(v, PartialCorrelation):
        return *v.left_residual_ids, *v.right_residual_ids
    if isinstance(v, RedundancyStability):
        return v.evaluation_ids
    if isinstance(v, OrthogonalizationAudit):
        return (v.root_id,)
    return ()


def audit_for(repo: "OrthogonalizationRepository", root_id: str) -> OrthogonalizationAudit:
    require(
        root_id.startswith("afre.ort_") and not root_id.startswith("afre.ort_audit:"),
        "orthogonal audit composition root required",
    )
    b = repo.orthogonalization_bounds
    seen: set[str] = set()
    active: set[str] = set()
    size = 0

    def visit(identity: str, depth: int) -> None:
        nonlocal size
        require(identity not in active, "orthogonal lineage cycle")
        if identity in seen:
            return
        require(
            depth <= b.audit_depth and len(seen) + len(active) < b.audit_nodes,
            "orthogonal lineage node/depth bound",
        )
        active.add(identity)
        value = repo.get_any(identity)
        repo._validate_links(value)
        edges = (
            orthogonalization_edges(value)
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
            require(len(runs) == 1, "orthogonal lineage requires completed native fit")
            run_id = runs[0][0]
            repo._validate_links(repo.get_any(run_id))
            if run_id not in seen:
                seen.add(run_id)
                size += len(canonical_json(repo.get_any(run_id)).encode())
        active.remove(identity)
        seen.add(identity)
        size += len(canonical_json(value).encode())
        require(size <= b.serialized_bytes, "orthogonal lineage byte bound")

    visit(root_id, 0)
    return OrthogonalizationAudit(
        root_id,
        tuple(seen),
        (
            "exact-candidate-reference-source-version-unit-and-PIT-origin",
            "admitted-TRAIN-only-projection-preprocessing-and-candidate-response",
            "explicit-rank-condition-intercept-and-weighting",
            "target-free-residual-application",
            "heldout-redundancy-partial-and-incremental-evidence-separate",
            "orthogonality-not-independence",
            "no-auto-pruning-or-signal-search",
            "bounded-canonical-semantic-lineage",
        ),
    )

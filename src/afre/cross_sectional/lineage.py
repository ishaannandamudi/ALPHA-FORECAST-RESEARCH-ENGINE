"""One bounded traversal spans rankings and every earlier research layer."""

from typing import TYPE_CHECKING

from afre.calibration.artifacts import CalibrationFitRun, CalibrationState
from afre.calibration.lineage import calibration_edges
from afre.cross_sectional.artifacts import (
    CrossSectionAudit,
    CrossSectionEvaluation,
    CrossSectionObservation,
    CrossSectionRanking,
    CrossSectionTruth,
    ICSeries,
    PeerState,
    RankStability,
    RawScore,
)
from afre.cross_sectional.definitions import CrossSectionIdentity, CrossSectionSpec
from afre.cross_sectional.external import ExternalSignal
from afre.cross_sectional.groups import GroupMembership
from afre.cross_sectional.models import (
    CrossSectionModel,
    CrossSectionModelSpec,
    CrossSectionPrediction,
)
from afre.multihorizon.lineage import multihorizon_edges
from afre.probabilistic.artifacts import ProbabilisticFitRun, ProbabilisticModelArtifact
from afre.probabilistic.lineage import probability_edges
from afre.schema import Artifact, require
from afre.serialization import canonical_json
from afre.statistical_models.artifacts import FittedModelArtifact, ModelFitRun
from afre.statistical_models.lineage import upstream_edges
from afre.statistical_models.validation import model_edges

if TYPE_CHECKING:
    from afre.cross_sectional.repository import CrossSectionRepository


def cross_section_edges(value: Artifact) -> tuple[str, ...]:
    if isinstance(value, CrossSectionIdentity):
        return value.snapshot_id, value.target.fingerprint
    if isinstance(value, CrossSectionSpec):
        return (
            value.identity.fingerprint,
            *((value.score.model_id,) if value.score.model_id else ()),
        )
    if isinstance(value, (ExternalSignal, GroupMembership)):
        return (
            value.source.fingerprint,
            *(
                (value.clocks.historical_delivery.fingerprint,)
                if value.clocks.historical_delivery
                else ()
            ),
        )
    if isinstance(value, CrossSectionObservation):
        return (
            value.spec_id,
            *((value.source_id,) if value.source_id else ()),
            *((value.group_id,) if value.group_id else ()),
        )
    if isinstance(value, RawScore):
        return (value.observation_id,)
    if isinstance(value, PeerState):
        return value.spec_id, *value.raw_ids
    if isinstance(value, CrossSectionRanking):
        return (
            value.spec_id,
            value.normalization_id,
            *((value.group_neutral_id,) if value.group_neutral_id else ()),
            *(i for e in value.entries for i in (e.observation_id, e.raw_id)),
        )
    if isinstance(value, CrossSectionTruth):
        return (
            value.ranking_id,
            *value.test_evaluation_ids,
            *(i for r in value.rows for i in (r.target_id, r.sample_id) if i is not None),
        )
    if isinstance(value, CrossSectionEvaluation):
        return value.ranking_id, value.truth_id
    if isinstance(value, ICSeries):
        return value.evaluation_ids
    if isinstance(value, RankStability):
        return value.previous_id, value.current_id
    if isinstance(value, CrossSectionModelSpec):
        return (value.baseline_model_id,)
    if isinstance(value, CrossSectionModel):
        return value.spec_id, value.baseline_model_id, value.matrix_id
    if isinstance(value, CrossSectionPrediction):
        return value.model_id, value.scaffold_id
    return ()


def lineage_for(repo: "CrossSectionRepository", root_id: str) -> CrossSectionAudit:
    require(
        root_id.startswith("afre.cs_") and not root_id.startswith("afre.cs_audit:"),
        "cross-sectional audit requires cross-sectional root",
    )
    seen: set[str] = set()
    active: set[str] = set()
    size = 0
    b = repo.cross_section_bounds

    def visit(identity: str, depth: int) -> None:
        nonlocal size
        require(identity not in active, "cross-sectional lineage cycle")
        if identity in seen:
            return
        require(
            depth <= b.audit_depth and len(seen) + len(active) < b.audit_nodes,
            "cross-sectional audit depth/node bound",
        )
        active.add(identity)
        value = repo.get_any(identity)
        if identity.startswith(("afre.cs_", "afre.mh_", "afre.c_", "afre.p_", "afre.m_")):
            repo._validate_links(value)
        edges = (
            cross_section_edges(value)
            if identity.startswith("afre.cs_")
            else multihorizon_edges(value)
            if identity.startswith("afre.mh_")
            else calibration_edges(value)
            if identity.startswith("afre.c_")
            else probability_edges(value)
            if identity.startswith("afre.p_")
            else model_edges(value) or upstream_edges(repo, value)
        )
        extras: tuple[str, ...] = ()
        if isinstance(
            value, (CalibrationState, ProbabilisticModelArtifact, FittedModelArtifact)
        ):
            table, column, cls = (
                ("c_fits", "state_id", CalibrationFitRun)
                if isinstance(value, CalibrationState)
                else ("p_fits", "artifact_id", ProbabilisticFitRun)
                if isinstance(value, ProbabilisticModelArtifact)
                else ("m_fits", "artifact_id", ModelFitRun)
            )
            rows = repo._connection.execute(
                f"SELECT fingerprint FROM {table} WHERE {column}=?", (identity,)
            ).fetchall()
            require(len(rows) == 1, "cross-sectional audit requires completed fit")
            run = repo.resolve(cls, rows[0][0])
            repo._validate_links(run)
            extras = (run.fingerprint,)
        for edge in sorted(set(edges)):
            visit(edge, depth + 1)
        for key in (identity, *extras):
            if key not in seen:
                seen.add(key)
                size += len(canonical_json(repo.get_any(key)).encode())
        active.remove(identity)
        require(
            len(seen) <= b.audit_nodes and size <= b.serialized_bytes,
            "cross-sectional audit node/byte bound",
        )

    visit(root_id, 0)
    return CrossSectionAudit(
        root_id,
        tuple(seen),
        (
            "same-origin-full-information-context",
            "exact-PIT-universe-eligibility-grid",
            "PIT-group-taxonomy-and-delivery",
            "explicit-missingness-and-peer-transform",
            "target-free-ranking-application",
            "receipt-aware-external-data-only",
            "exact-later-truth-and-TEST-evidence",
            "bounded-safe-canonical-lineage",
        ),
    )

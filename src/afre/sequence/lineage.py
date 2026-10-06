"""One bounded sequence traversal spans all prior research evidence."""

from typing import TYPE_CHECKING

from afre.calibration.artifacts import CalibrationState
from afre.calibration.lineage import calibration_edges
from afre.cross_sectional.lineage import cross_section_edges
from afre.event_conditioned.lineage import event_edges
from afre.mixture.lineage import mixture_edges
from afre.multihorizon.lineage import multihorizon_edges
from afre.probabilistic.artifacts import ProbabilisticModelArtifact
from afre.probabilistic.lineage import probability_edges
from afre.regime_conditioned.lineage import regime_edges
from afre.schema import require
from afre.serialization import canonical_json
from afre.statistical_models.artifacts import FittedModelArtifact
from afre.statistical_models.lineage import upstream_edges
from afre.statistical_models.validation import model_edges

if TYPE_CHECKING:
    from afre.sequence.repository import SequenceRepository


from afre.nonlinear.lineage import nonlinear_edges
from afre.schema import Artifact
from afre.sequence.artifacts import (
    SequenceAudit,
    SequenceCalibrationAssessment,
    SequenceContribution,
    SequenceCoverage,
    SequenceDataset,
    SequenceEvaluation,
    SequenceEvaluationPair,
    SequenceForecast,
    SequenceModelArtifact,
    SequenceObservation,
    SequenceRankEvaluation,
    SequenceRanking,
    SequenceSnapshot,
    SequenceStability,
    SequenceTrainingRow,
    SequenceTransformArtifact,
)
from afre.sequence.definitions import (
    SequenceFeatureDefinition,
    SequenceModelSpec,
    SequenceWindowSpec,
)


def sequence_edges(value: Artifact) -> tuple[str, ...]:
    if isinstance(value, SequenceFeatureDefinition):
        return (value.source_definition_id,)
    if isinstance(value, SequenceWindowSpec):
        return value.exact_observation_ids
    if isinstance(value, SequenceObservation):
        return value.feature_id, value.source_id
    if isinstance(value, SequenceSnapshot):
        return value.window_id, *value.feature_ids, *value.candidate_ids
    if isinstance(value, SequenceModelSpec):
        return (
            value.target.fingerprint,
            value.fold_id,
            value.window.fingerprint,
            *(f.fingerprint for f in value.features),
        )
    if isinstance(value, SequenceTransformArtifact):
        return value.spec_id, *(i for pair in value.train_bindings for i in pair)
    if isinstance(value, SequenceTrainingRow):
        return value.spec_id, value.sample_id, value.snapshot_id, value.target_id
    if isinstance(value, SequenceDataset):
        return (
            value.spec_id,
            value.transform_id,
            value.fold_id,
            *(r.fingerprint for r in value.rows),
        )
    if isinstance(value, SequenceModelArtifact):
        return value.spec_id, value.dataset_id, value.transform_id
    if isinstance(value, SequenceContribution):
        return value.feature_id, value.observation_id
    if isinstance(value, SequenceForecast):
        return (
            value.model_id,
            value.spec_id,
            value.snapshot_id,
            value.sample_id,
            *((value.probability.fingerprint,) if value.probability else ()),
        )
    if isinstance(value, SequenceEvaluationPair):
        return (
            value.forecast_id,
            value.sample_id,
            value.target_id,
            *((value.baseline_id,) if value.baseline_id else ()),
        )
    if isinstance(value, SequenceEvaluation):
        return (
            *value.forecast_ids,
            *(p.fingerprint for p in value.pairs),
            *((value.test_evaluation_id,) if value.test_evaluation_id else ()),
        )
    if isinstance(value, SequenceStability):
        return value.model_ids
    if isinstance(value, SequenceCoverage):
        return value.snapshot_ids
    if isinstance(value, SequenceCalibrationAssessment):
        return (
            value.forecast_id,
            *value.observation_ids,
            *((value.proposed_state_id,) if value.proposed_state_id else ()),
        )
    if isinstance(value, SequenceRanking):
        return value.ranking_id, *value.forecast_ids, *value.signal_ids
    if isinstance(value, SequenceRankEvaluation):
        return value.ranking_id, value.matched_id, value.cross_section_id
    return ()


def lineage_for(repo: "SequenceRepository", root_id: str) -> SequenceAudit:
    require(
        root_id.startswith("afre.sq_") and not root_id.startswith("afre.sq_audit:"),
        "sequence audit requires composition root",
    )
    seen: set[str] = set()
    active: set[str] = set()
    size = 0
    b = repo.sequence_bounds

    def visit(identity: str, depth: int) -> None:
        nonlocal size
        require(identity not in active, "sequence lineage cycle")
        if identity in seen:
            return
        require(
            depth <= b.audit_depth and len(seen) + len(active) < b.audit_nodes,
            "sequence lineage node/depth bound",
        )
        active.add(identity)
        value = repo.get_any(identity)
        if identity.startswith(
            (
                "afre.sq_",
                "afre.nl_",
                "afre.mix_",
                "afre.rc_",
                "afre.ec_",
                "afre.cs_",
                "afre.mh_",
                "afre.c_",
                "afre.p_",
                "afre.m_",
            )
        ):
            repo._validate_links(value)
        edges = (
            sequence_edges(value)
            if identity.startswith("afre.sq_")
            else nonlinear_edges(value)
            if identity.startswith("afre.nl_")
            else mixture_edges(value)
            if identity.startswith("afre.mix_")
            else regime_edges(value)
            if identity.startswith("afre.rc_")
            else event_edges(value)
            if identity.startswith("afre.ec_")
            else cross_section_edges(value)
            if identity.startswith("afre.cs_")
            else multihorizon_edges(value)
            if identity.startswith("afre.mh_")
            else calibration_edges(value)
            if identity.startswith("afre.c_")
            else probability_edges(value)
            if identity.startswith("afre.p_")
            else model_edges(value) or upstream_edges(repo, value)
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
            rows = repo._connection.execute(
                f"SELECT fingerprint FROM {table} WHERE {column}=?", (identity,)
            ).fetchall()
            require(len(rows) == 1, "sequence lineage completed fit")
            # Completed run links already-admitted inputs; do not recurse back to its model.
            run_id = rows[0][0]
            repo._validate_links(repo.get_any(run_id))
            if run_id not in seen:
                seen.add(run_id)
                size += len(canonical_json(repo.get_any(run_id)).encode())
        active.remove(identity)
        seen.add(identity)
        size += len(canonical_json(value).encode())
        require(
            size <= b.serialized_bytes and len(seen) <= b.audit_nodes,
            "sequence lineage byte/node bound",
        )

    visit(root_id, 0)
    return SequenceAudit(
        root_id,
        tuple(seen),
        (
            "exact-source-revisions-and-causal-cutoff",
            "explicit-windows-order-masks-and-irregular-time",
            "TRAIN-only-normalization-and-readout",
            "target-free-application",
            "bounded-fixed-temporal-dynamics",
            "matched-truth-TEST-and-calibration-boundary",
            "descriptive-diagnostics-no-auto-refit",
            "bounded-unified-lineage",
        ),
    )

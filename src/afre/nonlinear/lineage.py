"""One bounded nonlinear traversal spans all prior research evidence."""

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
    from afre.nonlinear.repository import NonlinearRepository


from afre.nonlinear.artifacts import (
    FittedTransformArtifact,
    InteractionMatrix,
    InteractionStability,
    InteractionTrainingRow,
    InteractionValue,
    NonlinearAudit,
    NonlinearCalibrationAssessment,
    NonlinearEvaluation,
    NonlinearForecast,
    NonlinearInput,
    NonlinearModelArtifact,
    NonlinearProbabilityView,
    NonlinearRankEvaluation,
    NonlinearRanking,
    ScalarInput,
)
from afre.nonlinear.definitions import (
    InteractionDefinition,
    InteractionSet,
    NonlinearModelSpec,
    ScalarFeatureDefinition,
)
from afre.nonlinear.schema import ScalarSourceKind
from afre.schema import Artifact


def nonlinear_edges(value: Artifact) -> tuple[str, ...]:
    if isinstance(value, ScalarFeatureDefinition):
        return (value.source_key[0],) if value.kind is ScalarSourceKind.FEATURE else ()
    if isinstance(value, ScalarInput):
        return value.definition.fingerprint, value.source_id
    if isinstance(value, NonlinearInput):
        return value.sample_id, *(s.fingerprint for s in value.scalars)
    if isinstance(value, InteractionDefinition):
        return tuple(f.fingerprint for f in value.inputs)
    if isinstance(value, InteractionSet):
        return value.target.fingerprint, *(d.fingerprint for d in value.definitions)
    if isinstance(value, NonlinearModelSpec):
        return (
            value.interaction_set.fingerprint,
            value.fold_id,
            *(f.fingerprint for f in value.original_features),
        )
    if isinstance(value, FittedTransformArtifact):
        return value.spec_id, value.definition_id, value.fold_id, *value.train_input_ids
    if isinstance(value, InteractionValue):
        return (
            value.definition_id,
            *value.input_ids,
            *((value.transform_id,) if value.transform_id else ()),
        )
    if isinstance(value, InteractionTrainingRow):
        return (
            value.spec_id,
            value.sample_id,
            value.input_id,
            value.target_id,
            *value.interaction_ids,
        )
    if isinstance(value, InteractionMatrix):
        return (
            value.spec_id,
            value.fold_id,
            *(r.fingerprint for r in value.rows),
            *value.transform_ids,
        )
    if isinstance(value, NonlinearModelArtifact):
        return value.spec_id, value.matrix_id, *value.transform_ids
    if isinstance(value, NonlinearProbabilityView):
        return (value.base_forecast_id,)
    if isinstance(value, NonlinearForecast):
        return (
            value.model_id,
            value.spec_id,
            value.input_id,
            *value.interaction_ids,
            *((value.probability.fingerprint,) if value.probability else ()),
        )
    if isinstance(value, NonlinearEvaluation):
        return (
            *value.forecast_ids,
            *(p.target_id for p in value.pairs),
            *(p.baseline_id for p in value.pairs if p.baseline_id),
            *((value.test_evaluation_id,) if value.test_evaluation_id else ()),
        )
    if isinstance(value, InteractionStability):
        return value.model_ids
    if isinstance(value, NonlinearCalibrationAssessment):
        return (
            value.forecast_id,
            *value.observation_ids,
            *((value.proposed_state_id,) if value.proposed_state_id else ()),
        )
    if isinstance(value, NonlinearRanking):
        return value.ranking_id, *value.forecast_ids, *value.signal_ids
    if isinstance(value, NonlinearRankEvaluation):
        return value.ranking_id, value.matched_id, value.cross_section_id
    return ()


def lineage_for(repo: "NonlinearRepository", root_id: str) -> NonlinearAudit:
    require(
        root_id.startswith("afre.nl_") and not root_id.startswith("afre.nl_audit:"),
        "nonlinear audit requires composition root",
    )
    seen: set[str] = set()
    active: set[str] = set()
    size = 0
    b = repo.nonlinear_bounds

    def visit(identity: str, depth: int) -> None:
        nonlocal size
        require(identity not in active, "nonlinear lineage cycle")
        if identity in seen:
            return
        require(
            depth <= b.audit_depth and len(seen) + len(active) < b.audit_nodes,
            "nonlinear lineage node/depth bound",
        )
        active.add(identity)
        value = repo.get_any(identity)
        if identity.startswith(
            (
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
            nonlinear_edges(value)
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
            require(len(rows) == 1, "nonlinear lineage completed fit")
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
            "nonlinear lineage byte/node bound",
        )

    visit(root_id, 0)
    return NonlinearAudit(
        root_id,
        tuple(seen),
        (
            "explicit-interaction-and-source-identity",
            "receipt-aware-availability",
            "TRAIN-only-knots-scaling-coefficients-and-tree",
            "held-out-target-free-application",
            "exact-linear-contributions-or-tree-path",
            "shape-preserving-probability-location",
            "calibration-does-not-transfer",
            "matched-truth-and-TEST",
            "descriptive-stability-no-pruning",
            "bounded-canonical-lineage",
        ),
    )

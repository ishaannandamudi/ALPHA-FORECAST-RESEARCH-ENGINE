"""One bounded traversal spans expert/gate evidence and every earlier research phase."""

from typing import TYPE_CHECKING

from afre.calibration.artifacts import CalibrationState
from afre.calibration.lineage import calibration_edges
from afre.cross_sectional.lineage import cross_section_edges
from afre.event_conditioned.lineage import event_edges
from afre.multihorizon.lineage import multihorizon_edges
from afre.probabilistic.artifacts import ProbabilisticModelArtifact
from afre.probabilistic.lineage import probability_edges
from afre.schema import require
from afre.serialization import canonical_json
from afre.statistical_models.artifacts import FittedModelArtifact
from afre.statistical_models.lineage import upstream_edges
from afre.statistical_models.validation import model_edges

if TYPE_CHECKING:
    from afre.mixture.repository import MixtureRepository


from afre.mixture.artifacts import (
    GateDriftDiagnostic,
    GateModelArtifact,
    GateTrainingRow,
    MixtureAudit,
    MixtureCalibrationAssessment,
    MixtureComponent,
    MixtureDiagnostics,
    MixtureDistribution,
    MixtureEvaluation,
    MixtureForecast,
    MixtureRankEvaluation,
    MixtureRanking,
    MixtureRequest,
)
from afre.mixture.definitions import ExpertSet, FixedGateSpec, LearnedGateSpec
from afre.mixture.experts import (
    ExpertForecastBinding,
    ExpertReference,
    ExternalExpertForecast,
    GatingFeatureReference,
)
from afre.regime_conditioned.lineage import regime_edges
from afre.schema import Artifact


def mixture_edges(value: Artifact) -> tuple[str, ...]:
    if isinstance(value, ExpertReference):
        return (
            value.source.fingerprint,
            value.target.fingerprint,
            *(() if value.kind.value.startswith("external_") else (value.model_id,)),
        )
    if isinstance(value, ExternalExpertForecast):
        return (
            value.expert.fingerprint,
            value.source.fingerprint,
            *(
                (value.clocks.historical_delivery.fingerprint,)
                if value.clocks.historical_delivery
                else ()
            ),
        )
    if isinstance(value, ExpertForecastBinding):
        return value.expert_id, value.forecast_id
    if isinstance(value, GatingFeatureReference):
        return (value.source_id,)
    if isinstance(value, ExpertSet):
        return value.target.fingerprint, *value.expert_ids
    if isinstance(value, FixedGateSpec):
        return (value.expert_set.fingerprint,)
    if isinstance(value, LearnedGateSpec):
        return value.expert_set.fingerprint, value.fold_id
    if isinstance(value, GateTrainingRow):
        return (
            value.spec_id,
            value.sample_id,
            *value.binding_ids,
            *value.feature_ids,
            value.target_id,
        )
    if isinstance(value, GateModelArtifact):
        return value.spec_id, *(r.fingerprint for r in value.rows)
    if isinstance(value, MixtureRequest):
        return (
            value.expert_set_id,
            value.gate_id,
            value.fold_id,
            value.sample_id,
            *(b for _, b in value.expert_inputs if b),
            *value.gating_feature_ids,
        )
    if isinstance(value, MixtureComponent):
        return value.expert_id, value.binding_id
    if isinstance(value, MixtureDistribution):
        return tuple(c.fingerprint for c in value.components)
    if isinstance(value, MixtureForecast):
        return value.request.fingerprint, *(
            (value.distribution.fingerprint,) if value.distribution else ()
        )
    if isinstance(value, MixtureEvaluation):
        return (
            *value.forecast_ids,
            *(p.target_id for p in value.pairs),
            *((value.test_evaluation_id,) if value.test_evaluation_id else ()),
        )
    if isinstance(value, MixtureDiagnostics):
        return (value.evaluation_id,)
    if isinstance(value, GateDriftDiagnostic):
        return value.reference_diagnostics_id, value.current_diagnostics_id
    if isinstance(value, MixtureCalibrationAssessment):
        return (
            value.forecast_id,
            *value.observation_ids,
            *(
                (value.proposed_component_state_id,)
                if value.proposed_component_state_id
                else ()
            ),
        )
    if isinstance(value, MixtureRanking):
        return value.ranking_id, *value.forecast_ids, *value.signal_ids
    if isinstance(value, MixtureRankEvaluation):
        return (
            value.mixture_ranking_id,
            value.matched_evaluation_id,
            value.cross_section_evaluation_id,
        )
    return ()


def lineage_for(repo: "MixtureRepository", root_id: str) -> MixtureAudit:
    require(
        root_id.startswith("afre.mix_") and not root_id.startswith("afre.mix_audit:"),
        "mixture audit requires composition root",
    )
    seen: set[str] = set()
    active: set[str] = set()
    size = 0
    b = repo.mixture_bounds

    def visit(identity: str, depth: int) -> None:
        nonlocal size
        require(identity not in active, "mixture lineage cycle")
        if identity in seen:
            return
        require(
            depth <= b.audit_depth and len(seen) + len(active) < b.audit_nodes,
            "mixture lineage node/depth bound",
        )
        active.add(identity)
        value = repo.get_any(identity)
        if identity.startswith(
            (
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
            mixture_edges(value)
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
            require(len(rows) == 1, "mixture lineage completed fit")
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
            "mixture lineage byte/node bound",
        )

    visit(root_id, 0)
    return MixtureAudit(
        root_id,
        tuple(seen),
        (
            "exact-independent-expert-identity",
            "target-horizon-origin-compatibility",
            "receipt-aware-availability",
            "TRAIN-only-causal-gating",
            "explicit-missingness-and-fallback",
            "exact-contribution-accounting",
            "finite-component-probability-law",
            "calibration-does-not-transfer",
            "target-free-application",
            "matched-truth-and-TEST",
            "descriptive-drift-no-refit",
            "bounded-canonical-lineage",
        ),
    )

"""One bounded traversal spans event evidence, conditioned effects and earlier research."""

from typing import TYPE_CHECKING

from afre.calibration.artifacts import CalibrationState
from afre.calibration.lineage import calibration_edges
from afre.cross_sectional.lineage import cross_section_edges
from afre.event_conditioned.lineage import event_edges
from afre.multihorizon.lineage import multihorizon_edges
from afre.probabilistic.artifacts import ProbabilisticModelArtifact
from afre.probabilistic.lineage import probability_edges
from afre.regime_conditioned.artifacts import (
    RegimeAudit,
    RegimeCalibrationAssessment,
    RegimeConditionedEvaluation,
    RegimeConditionedForecast,
    RegimeConditionedModel,
    RegimeConditionedSample,
    RegimeDriftDiagnostic,
    RegimeMatchSet,
    RegimeRankEvaluation,
    RegimeRanking,
    RegimeTransition,
)
from afre.regime_conditioned.definitions import RegimeConditioningSpec
from afre.regime_conditioned.regimes import (
    RegimeProviderReference,
    RegimeSnapshot,
    RegimeTaxonomy,
)
from afre.schema import Artifact, require
from afre.serialization import canonical_json
from afre.statistical_models.artifacts import FittedModelArtifact
from afre.statistical_models.lineage import upstream_edges
from afre.statistical_models.validation import model_edges

if TYPE_CHECKING:
    from afre.regime_conditioned.repository import RegimeRepository


def regime_edges(value: Artifact) -> tuple[str, ...]:
    if isinstance(value, RegimeProviderReference):
        return (value.source.fingerprint,)
    if isinstance(value, RegimeTaxonomy):
        return (value.provider.fingerprint,)
    if isinstance(value, RegimeSnapshot):
        return (
            value.taxonomy.fingerprint,
            value.subject.fingerprint,
            value.membership.fingerprint,
            value.source.fingerprint,
            *(
                (value.clocks.historical_delivery.fingerprint,)
                if value.clocks.historical_delivery
                else ()
            ),
            *((value.subject.group_policy.fingerprint,) if value.subject.group_policy else ()),
            *(
                (value.subject.universe_definition_id,)
                if value.subject.universe_definition_id
                else ()
            ),
        )
    if isinstance(value, RegimeConditioningSpec):
        return (
            value.base_model_id,
            value.target.fingerprint,
            value.taxonomy_id,
            *((value.event_model_id,) if value.event_model_id else ()),
        )
    if isinstance(value, RegimeMatchSet):
        return value.spec_id, value.sample_id, *value.candidate_ids, *value.mapping_ids
    if isinstance(value, RegimeConditionedSample):
        return (
            value.matches_id,
            value.sample_id,
            value.universe_snapshot_id,
            *value.transition_ids,
        )
    if isinstance(value, RegimeTransition):
        return value.previous_id, value.current_id, value.taxonomy_id
    if isinstance(value, RegimeConditionedModel):
        return value.spec_id, value.matrix_id, *value.observation_ids
    if isinstance(value, RegimeConditionedForecast):
        return (
            value.spec_id,
            value.model_id,
            value.observation_id,
            value.base_forecast_id,
            *((value.base_probability_id,) if value.base_probability_id else ()),
        )
    if isinstance(value, RegimeConditionedEvaluation):
        return (
            *value.forecast_ids,
            *(p.target_id for p in value.pairs),
            *((value.test_evaluation_id,) if value.test_evaluation_id else ()),
        )
    if isinstance(value, RegimeCalibrationAssessment):
        return (
            value.forecast_id,
            *value.observation_forecast_ids,
            *((value.proposed_global_state_id,) if value.proposed_global_state_id else ()),
        )
    if isinstance(value, RegimeDriftDiagnostic):
        return value.reference_evaluation_id, value.current_evaluation_id
    if isinstance(value, RegimeRanking):
        return value.ranking_id, *value.forecast_ids, *value.signal_ids
    if isinstance(value, RegimeRankEvaluation):
        return (
            value.regime_ranking_id,
            value.matched_evaluation_id,
            value.cross_section_evaluation_id,
        )
    return ()


def lineage_for(repo: "RegimeRepository", root_id: str) -> RegimeAudit:
    require(
        root_id.startswith("afre.rc_") and not root_id.startswith("afre.rc_audit:"),
        "regime audit requires event root",
    )
    seen: set[str] = set()
    active: set[str] = set()
    size = 0
    b = repo.regime_bounds

    def visit(identity: str, depth: int) -> None:
        nonlocal size
        require(identity not in active, "regime lineage cycle")
        if identity in seen:
            return
        require(
            depth <= b.audit_depth and len(seen) + len(active) < b.audit_nodes,
            "regime lineage node/depth bound",
        )
        active.add(identity)
        value = repo.get_any(identity)
        if identity.startswith(
            ("afre.rc_", "afre.ec_", "afre.cs_", "afre.mh_", "afre.c_", "afre.p_", "afre.m_")
        ):
            repo._validate_links(value)
        edges = (
            regime_edges(value)
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
            require(len(rows) == 1, "regime lineage completed fit")
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
            "regime lineage byte/node bound",
        )

    visit(root_id, 0)
    return RegimeAudit(
        root_id,
        tuple(seen),
        (
            "provider-neutral-taxonomy-and-source",
            "six-clocks-filtered-causal-state",
            "exact-hard-or-ordered-soft-membership",
            "PIT-subject-and-staleness",
            "supplied-causal-history-and-elapsed-duration",
            "admitted-TRAIN-only",
            "explicit-fallback-and-calibration",
            "target-free-application",
            "matched-truth-and-TEST",
            "descriptive-drift-no-refit",
            "bounded-canonical-lineage",
        ),
    )

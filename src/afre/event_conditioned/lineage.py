"""One bounded traversal spans event evidence, conditioned effects and earlier research."""

from typing import TYPE_CHECKING

from afre.calibration.artifacts import CalibrationState
from afre.calibration.lineage import calibration_edges
from afre.cross_sectional.lineage import cross_section_edges
from afre.event_conditioned.artifacts import (
    EventAudit,
    EventCalibrationAssessment,
    EventConditionedEvaluation,
    EventConditionedForecast,
    EventConditionedModel,
    EventConditionedObservation,
    EventMatchSet,
    EventRankEvaluation,
    EventRanking,
)
from afre.event_conditioned.definitions import EventConditioningSpec, EventWindowSpec
from afre.event_conditioned.events import (
    EventReference,
    EventSubject,
    EventSurprise,
    EventValue,
)
from afre.multihorizon.lineage import multihorizon_edges
from afre.probabilistic.artifacts import ProbabilisticModelArtifact
from afre.probabilistic.lineage import probability_edges
from afre.schema import Artifact, require
from afre.serialization import canonical_json
from afre.statistical_models.artifacts import FittedModelArtifact
from afre.statistical_models.lineage import upstream_edges
from afre.statistical_models.validation import model_edges

if TYPE_CHECKING:
    from afre.event_conditioned.repository import EventRepository


def event_edges(value: Artifact) -> tuple[str, ...]:
    if isinstance(value, (EventValue, EventReference)):
        return (
            value.source.fingerprint,
            *((value.subject.fingerprint,) if isinstance(value, EventReference) else ()),
            *(
                (value.clocks.historical_delivery.fingerprint,)
                if value.clocks.historical_delivery
                else ()
            ),
            *(
                (
                    attr.fingerprint
                    for attr in (value.materiality, value.novelty, value.surprise)
                    if attr is not None
                )
                if isinstance(value, EventReference)
                else ()
            ),
        )
    if isinstance(value, EventSurprise):
        return value.actual.fingerprint, value.expected.fingerprint
    if isinstance(value, EventSubject):
        return (
            *((value.group_policy.fingerprint,) if value.group_policy else ()),
            *((value.universe_definition_id,) if value.universe_definition_id else ()),
        )
    if isinstance(value, EventWindowSpec):
        return (value.target.fingerprint,)
    if isinstance(value, EventConditioningSpec):
        return (
            value.base_model_id,
            value.window.fingerprint,
            *(r.fingerprint for r in value.value_rules),
            *(r.fingerprint for r in value.reaction_specs),
        )
    if isinstance(value, EventMatchSet):
        return (
            value.spec_id,
            value.sample_id,
            *value.event_ids,
            *value.reaction_ids,
            *value.mapping_ids,
        )
    if isinstance(value, EventConditionedObservation):
        return value.matches_id, value.sample_id, value.snapshot_id
    if isinstance(value, EventConditionedModel):
        return value.spec_id, value.matrix_id, *value.observation_ids
    if isinstance(value, EventConditionedForecast):
        return (
            value.spec_id,
            value.model_id,
            value.observation_id,
            value.base_forecast_id,
            *((value.base_probability_id,) if value.base_probability_id else ()),
        )
    if isinstance(value, EventConditionedEvaluation):
        return (
            *value.forecast_ids,
            *(p.target_id for p in value.pairs),
            *((value.test_evaluation_id,) if value.test_evaluation_id else ()),
        )
    if isinstance(value, EventCalibrationAssessment):
        return value.forecast_id, *value.observation_forecast_ids
    if isinstance(value, EventRanking):
        return value.ranking_id, *value.forecast_ids, *value.signal_ids
    if isinstance(value, EventRankEvaluation):
        return (
            value.event_ranking_id,
            value.matched_evaluation_id,
            value.cross_section_evaluation_id,
        )
    return ()


def lineage_for(repo: "EventRepository", root_id: str) -> EventAudit:
    require(
        root_id.startswith("afre.ec_") and not root_id.startswith("afre.ec_audit:"),
        "event audit requires event root",
    )
    seen: set[str] = set()
    active: set[str] = set()
    size = 0
    b = repo.event_bounds

    def visit(identity: str, depth: int) -> None:
        nonlocal size
        require(identity not in active, "event lineage cycle")
        if identity in seen:
            return
        require(
            depth <= b.audit_depth and len(seen) + len(active) < b.audit_nodes,
            "event lineage node/depth bound",
        )
        active.add(identity)
        value = repo.get_any(identity)
        if identity.startswith(
            ("afre.ec_", "afre.cs_", "afre.mh_", "afre.c_", "afre.p_", "afre.m_")
        ):
            repo._validate_links(value)
        edges = (
            event_edges(value)
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
            require(len(rows) == 1, "event lineage completed fit")
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
            "event lineage byte/node bound",
        )

    visit(root_id, 0)
    return EventAudit(
        root_id,
        tuple(seen),
        (
            "exact-event-vintage-and-six-clocks",
            "PIT-subject-and-window",
            "independent-reaction-availability",
            "explicit-overlap-policy",
            "admitted-TRAIN-only",
            "target-free-application",
            "matched-truth-and-TEST",
            "bounded-canonical-lineage",
        ),
    )

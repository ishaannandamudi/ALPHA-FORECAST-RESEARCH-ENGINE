"""Explicit allocation and output bounds for every event research operation."""

from afre.event_conditioned.artifacts import (
    EventAudit,
    EventConditionedEvaluation,
    EventConditionedForecast,
    EventConditionedModel,
    EventMatchSet,
    EventRanking,
)
from afre.event_conditioned.definitions import EventConditioningSpec
from afre.event_conditioned.schema import EventBounds
from afre.schema import Artifact, require
from afre.serialization import canonical_json


def check_event_bounds(value: Artifact, bounds: EventBounds) -> None:
    if isinstance(value, EventMatchSet):
        require(
            len(value.event_ids) <= bounds.events
            and len(value.mapping_ids) <= bounds.events
            and len(value.distances) <= bounds.matches_per_sample
            and len(value.selected_ids) <= bounds.matches_per_sample
            and len(value.reaction_ids) <= bounds.reaction_features * bounds.matches_per_sample,
            "event matching bound",
        )
    elif isinstance(value, EventConditioningSpec):
        require(len(value.reaction_specs) <= bounds.reaction_features, "event feature bound")
    elif isinstance(value, EventConditionedModel):
        require(len(value.observation_ids) <= bounds.samples, "event model sample bound")
    elif isinstance(value, EventConditionedForecast):
        require(len(value.reaction_ids) <= bounds.reaction_features, "event reaction bound")
    elif isinstance(value, EventConditionedEvaluation):
        require(
            len(value.forecast_ids) <= bounds.samples and len(value.groups) <= bounds.groups,
            "event evaluation bound",
        )
    elif isinstance(value, EventRanking):
        require(len(value.forecast_ids) <= bounds.samples, "event rank bound")
    elif isinstance(value, EventAudit):
        require(len(value.evidence_ids) <= bounds.audit_nodes, "event audit node bound")
    require(len(canonical_json(value).encode()) <= bounds.serialized_bytes, "event byte bound")

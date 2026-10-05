"""Explicit signed temporal distances; equality at the availability cutoff is causal."""

from afre.event_conditioned.definitions import EventWindowSpec
from afre.event_conditioned.events import EventReference
from afre.event_conditioned.schema import EventAnchor, EventRelation


def event_anchor(event: EventReference, window: EventWindowSpec) -> int | None:
    return (
        event.occurrence_ns
        if window.anchor is EventAnchor.OCCURRENCE
        else event.clocks.upstream_publication_ns
        if window.anchor is EventAnchor.PUBLICATION
        else event.clocks.final_available_ns
    )


def window_distance(
    event: EventReference, window: EventWindowSpec, origin_ns: int
) -> int | None:
    anchor = event_anchor(event, window)
    if anchor is None:
        return None
    distance = origin_ns - anchor
    relation = window.relation
    if relation is EventRelation.AT_EVENT:
        return 0 if distance == 0 else None
    if relation is EventRelation.PRE_EVENT:
        return (
            distance
            if distance < 0
            and (
                distance >= -window.pre_lookback_ns
                if window.include_maximum
                else distance > -window.pre_lookback_ns
            )
            else None
        )
    if distance <= 0:
        return None
    lower = (
        distance >= window.post_minimum_delay_ns
        if window.include_minimum
        else distance > window.post_minimum_delay_ns
    )
    upper = (
        distance <= window.post_maximum_age_ns
        if window.include_maximum
        else distance < window.post_maximum_age_ns
    )
    return distance if lower and upper else None

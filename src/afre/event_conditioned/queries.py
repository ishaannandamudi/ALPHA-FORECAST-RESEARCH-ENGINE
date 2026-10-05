"""Bounded indexed event history; explicit IDs freeze corrections when ambiguous."""

from typing import TYPE_CHECKING

from afre.event_conditioned.events import EventReference
from afre.schema import require

if TYPE_CHECKING:
    from afre.event_conditioned.repository import EventRepository


def event_as_of(
    repo: "EventRepository", provider: str, event_id: str, cutoff_ns: int
) -> EventReference | None:
    rows = repo._connection.execute(
        (
            "SELECT fingerprint FROM ec_records WHERE event_id=? AND available_ns<=? "
            "ORDER BY available_ns DESC,fingerprint LIMIT ?"
        ),
        (event_id, cutoff_ns, repo.event_bounds.events + 1),
    ).fetchall()
    require(len(rows) <= repo.event_bounds.events, "event history query bound")
    events = tuple(
        e for row in rows if (e := repo.resolve(EventReference, row[0])).provider == provider
    )
    if not events:
        return None
    require(
        sum(e.clocks.final_available_ns == events[0].clocks.final_available_ns for e in events)
        == 1,
        "ambiguous event revision; pin explicit reference",
    )
    return events[0]

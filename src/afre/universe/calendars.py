"""Supplied neutral exchange sessions; no target data or implicit calendars."""

from dataclasses import dataclass

from afre.schema import Artifact, contract, require
from afre.time import TimeRange
from afre.universe.evidence import UniverseEvidence


@contract("u_session")
@dataclass(frozen=True, slots=True)
class UniverseSession(Artifact):
    session_id: str
    period: TimeRange
    extended: bool = False


@contract("u_calendar")
@dataclass(frozen=True, slots=True)
class UniverseCalendar(Artifact):
    calendar_id: str
    version: str
    venue: str
    timezone_label: str
    sessions: tuple[UniverseSession, ...]
    evidence: UniverseEvidence

    def _normalize(self) -> None:
        self.ordered("sessions", "session_id")
        object.__setattr__(
            self, "sessions", tuple(sorted(self.sessions, key=lambda x: x.period.start_ns))
        )

    def _validate(self) -> None:
        require(
            bool(self.sessions)
            and all(
                a.period.end_ns <= b.period.start_ns
                for a, b in zip(self.sessions, self.sessions[1:], strict=False)
            ),
            "empty/overlapping universe calendar",
        )

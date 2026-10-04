"""Explicit supplied UTC session schedule; never infer sessions from elapsed days."""

from dataclasses import dataclass

from afre.feature_store.models import AvailabilityEvidence
from afre.lineage import ProvenanceRef
from afre.schema import Artifact, contract, require
from afre.time import TimeRange


@contract("target_session")
@dataclass(frozen=True, slots=True)
class TargetSession(Artifact):
    session_id: str
    period: TimeRange
    extended: bool = False


@contract("target_calendar")
@dataclass(frozen=True, slots=True)
class TargetCalendar(Artifact):
    calendar_id: str
    version: str
    timezone_label: str
    sessions: tuple[TargetSession, ...]
    clocks: AvailabilityEvidence
    source: ProvenanceRef

    def _normalize(self) -> None:
        self.ordered("sessions", "session_id")
        object.__setattr__(
            self,
            "sessions",
            tuple(sorted(self.sessions, key=lambda item: item.period.start_ns)),
        )

    def _validate(self) -> None:
        require(bool(self.sessions), "empty target calendar")
        require(
            all(
                a.period.end_ns <= b.period.start_ns
                for a, b in zip(self.sessions, self.sessions[1:], strict=False)
            ),
            "overlapping target sessions",
        )
        require(self.clocks.historical_delivery is None, "calendar backdating unsupported")

    def expected_closes(
        self, start_ns: int, end_ns: int, interval_ns: int, extended: bool, limit: int
    ) -> tuple[int, ...]:
        values: list[int] = []
        for session in self.sessions:
            if session.extended and not extended:
                continue
            begin = max(1, (start_ns - session.period.start_ns) // interval_ns + 1)
            count = (session.period.end_ns - session.period.start_ns) // interval_ns
            last = min(count, (end_ns - session.period.start_ns) // interval_ns)
            require(
                len(values) + max(0, last - begin + 1) <= limit,
                "path observation bound exceeded",
            )
            values.extend(
                session.period.start_ns + index * interval_ns
                for index in range(begin, last + 1)
            )
        return tuple(values)

"""Declared UTC valid-time windows; availability is a separate cutoff."""

from dataclasses import dataclass

from afre.schema import Artifact, contract, require


@contract("hlt_window")
@dataclass(frozen=True, slots=True)
class MonitoringWindow(Artifact):
    label: str
    start_ns: int
    end_ns: int
    evaluation_cutoff_ns: int
    minimum_count: int
    include_start: bool = True
    include_end: bool = False
    semantics: str = "origin-valid-time-UTC-v1"

    def _validate(self) -> None:
        require(
            self.start_ns < self.end_ns <= self.evaluation_cutoff_ns, "health window clocks"
        )
        require(1 <= self.minimum_count <= 2000, "health window minimum")
        require(self.semantics == "origin-valid-time-UTC-v1", "health window semantics")

    def contains(self, at_ns: int) -> bool:
        return (at_ns > self.start_ns or self.include_start and at_ns == self.start_ns) and (
            at_ns < self.end_ns or self.include_end and at_ns == self.end_ns
        )


def overlap(left: MonitoringWindow, right: MonitoringWindow) -> bool:
    return max(left.start_ns, right.start_ns) < min(left.end_ns, right.end_ns) or (
        left.end_ns == right.start_ns and left.include_end and right.include_start
    )

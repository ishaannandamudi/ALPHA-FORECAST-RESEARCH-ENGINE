"""Declared fixed evaluation boundaries and a later truth cutoff."""

from dataclasses import dataclass

from afre.schema import Artifact, contract, require


@contract("ch_window")
@dataclass(frozen=True, slots=True)
class ChallengeWindow(Artifact):
    start_ns: int
    end_ns: int
    cutoff_ns: int
    include_start: bool = True
    include_end: bool = False

    def _validate(self) -> None:
        require(self.start_ns < self.end_ns <= self.cutoff_ns, "challenge window clocks")

    def contains(self, at: int) -> bool:
        return (at >= self.start_ns if self.include_start else at > self.start_ns) and (
            at <= self.end_ns if self.include_end else at < self.end_ns
        )

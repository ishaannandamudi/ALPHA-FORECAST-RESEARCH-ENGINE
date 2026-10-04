"""Explicit endpoint inclusion and sorted interval unions; no all-pairs overlap."""

from bisect import bisect_right
from dataclasses import dataclass

from afre.schema import Artifact, contract, require


@contract("r_information_interval")
@dataclass(frozen=True, slots=True)
class SampleInformationInterval(Artifact):
    start_ns: int
    end_ns: int
    left_closed: bool = False
    right_closed: bool = True

    def _validate(self) -> None:
        require(
            self.start_ns < self.end_ns
            or (self.start_ns == self.end_ns and self.left_closed and self.right_closed),
            "empty information interval",
        )

    def overlaps(self, other: "SampleInformationInterval") -> bool:
        if self.end_ns < other.start_ns or other.end_ns < self.start_ns:
            return False
        if self.end_ns == other.start_ns:
            return self.right_closed and other.left_closed
        if other.end_ns == self.start_ns:
            return other.right_closed and self.left_closed
        return True


class IntervalIndex:
    def __init__(self, values: tuple[SampleInformationInterval, ...]) -> None:
        merged: list[SampleInformationInterval] = []
        for value in sorted(values, key=lambda x: (x.start_ns, not x.left_closed, x.end_ns)):
            if merged and (
                merged[-1].end_ns > value.start_ns
                or (
                    merged[-1].end_ns == value.start_ns
                    and (merged[-1].right_closed or value.left_closed)
                )
            ):
                old = merged[-1]
                merged[-1] = SampleInformationInterval(
                    old.start_ns,
                    max(old.end_ns, value.end_ns),
                    old.left_closed or (value.start_ns == old.start_ns and value.left_closed),
                    (old.right_closed if old.end_ns > value.end_ns else value.right_closed)
                    if old.end_ns != value.end_ns
                    else old.right_closed or value.right_closed,
                )
            else:
                merged.append(value)
        self.values = tuple(merged)
        self.starts = tuple(value.start_ns for value in merged)
        self.comparisons = 0

    def overlaps(self, value: SampleInformationInterval) -> bool:
        index = bisect_right(self.starts, value.end_ns) - 1
        for candidate in (index, index - 1):
            if candidate >= 0:
                self.comparisons += 1
                if self.values[candidate].overlaps(value):
                    return True
        return False

"""Whole-repository snapshots pin chronology and keep unsuccessful opportunities."""

from dataclasses import dataclass

from afre.multiple_testing.schema import ids
from afre.schema import Artifact, contract, require


@contract("mt_registry")
@dataclass(frozen=True, slots=True)
class TrialRegistrySnapshot(Artifact):
    trial_ids: tuple[str, ...]
    plan_ids: tuple[str, ...]
    family_ids: tuple[str, ...]
    selection_event_ids: tuple[str, ...]
    native_test_seal_ids: tuple[str, ...]
    chronology: tuple[tuple[int, str], ...]
    completion_cutoff_ns: int
    available_ns: int
    scope: str = "all-visible-registered-opportunities-no-subset-v1"

    def _normalize(self) -> None:
        ids(
            self,
            "trial_ids",
            "plan_ids",
            "family_ids",
            "selection_event_ids",
            "native_test_seal_ids",
        )
        require(
            len({i for _, i in self.chronology}) == len(self.chronology),
            "registry chronology duplicates",
        )
        object.__setattr__(self, "chronology", tuple(sorted(self.chronology)))

    def _validate(self) -> None:
        require(
            self.completion_cutoff_ns <= self.available_ns
            and self.scope == "all-visible-registered-opportunities-no-subset-v1",
            "registry scope/cutoff",
        )
        require(
            set(i for _, i in self.chronology) == set(self.trial_ids)
            and len(self.trial_ids) <= 2000
            and len(self.plan_ids) <= 2000
            and len(self.family_ids) <= 2000
            and len(self.selection_event_ids) <= 256
            and len(self.native_test_seal_ids) <= 2000,
            "registry bounds/chronology coverage",
        )

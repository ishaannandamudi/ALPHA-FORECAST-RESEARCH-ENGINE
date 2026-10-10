"""Append-only exact search registry, never a global TEST-sensitive registry."""

from dataclasses import dataclass

from afre.ids import validate_fingerprint
from afre.schema import Artifact, contract, require
from afre.selection.schema import CandidateStatus


@contract("sel_registry_entry")
@dataclass(frozen=True, slots=True)
class CandidateRegistryEntry(Artifact):
    candidate_id: str
    fit_id: str
    model_id: str | None
    validation_id: str
    trial_id: str
    status: CandidateStatus

    def _validate(self) -> None:
        for i in (
            self.candidate_id,
            self.fit_id,
            self.model_id,
            self.validation_id,
            self.trial_id,
        ):
            if i:
                validate_fingerprint(i)


@contract("sel_registry")
@dataclass(frozen=True, slots=True)
class CandidateRegistrySnapshot(Artifact):
    search_space_id: str
    selection_id: str
    entries: tuple[CandidateRegistryEntry, ...]
    completion_cutoff_ns: int

    def _normalize(self) -> None:
        self.ordered("entries", "candidate_id")

    def _validate(self) -> None:
        validate_fingerprint(self.search_space_id)
        validate_fingerprint(self.selection_id)
        require(1 <= len(self.entries) <= 128, "registry entry bound")

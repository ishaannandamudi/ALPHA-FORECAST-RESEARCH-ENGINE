"""Explicit frozen participant identity; designation never selects or fits a model."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from afre.challenger.schema import ParticipantRole
from afre.health.definitions import MonitoredArtifactReference
from afre.health.sources import reference_for
from afre.ids import validate_fingerprint
from afre.research_datasets.splits import FoldDefinition
from afre.schema import Artifact, contract, require
from afre.selection.results import SelectionResult

if TYPE_CHECKING:
    from afre.challenger.repository import ChallengeRepository


@contract("ch_participant")
@dataclass(frozen=True, slots=True)
class ParticipantReference(Artifact):
    name: str
    role: ParticipantRole
    reference: MonitoredArtifactReference
    dataset_id: str
    fold_id: str
    selection_result_id: str | None = None
    fusion_provenance_id: str | None = None
    version: str = "1.0"

    def _validate(self) -> None:
        validate_fingerprint(self.dataset_id, "r_dataset")
        validate_fingerprint(self.fold_id, "r_fold")
        require(self.version == "1.0", "challenge participant schema")
        for identity in (self.selection_result_id, self.fusion_provenance_id):
            if identity is not None:
                validate_fingerprint(identity)


def participant_for(
    repo: "ChallengeRepository",
    name: str,
    role: ParticipantRole,
    source_id: str,
    anchor_id: str | None = None,
    selection_id: str | None = None,
) -> ParticipantReference:
    ref = reference_for(repo, source_id, anchor_id)
    require(
        ref.output_semantics.startswith(("native:", "frozen-fusion:")),
        "challenge participants must be frozen predictive or orthogonal artifacts",
    )
    if ref.artifact_type == "SelectionResult":
        selection_id = source_id
    if selection_id:
        result = repo.get(SelectionResult, selection_id)
        require(
            result.selected_model_id == ref.producer_id,
            "challenge exact selected-model provenance",
        )
    fusion = ref.producer_id if ref.producer_id.startswith("afre.fus_artifact:") else None
    require(ref.fold_id is not None, "participant needs native research fold")
    assert ref.fold_id is not None
    fold = repo.resolve(FoldDefinition, ref.fold_id)
    return ParticipantReference(
        name, role, ref, fold.dataset_id, ref.fold_id, selection_id, fusion
    )

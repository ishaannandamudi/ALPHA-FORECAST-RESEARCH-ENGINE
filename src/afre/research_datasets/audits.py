"""Typed contamination evidence and bounded lineage summaries."""

from dataclasses import dataclass

from afre.ids import validate_fingerprint
from afre.research_datasets.schema import Partition, SampleState
from afre.schema import Artifact, contract, require


@contract("r_contamination_audit")
@dataclass(frozen=True, slots=True)
class ContaminationAudit(Artifact):
    dataset_id: str
    fold_id: str | None
    sample_counts: tuple[tuple[SampleState, int], ...]
    partition_counts: tuple[tuple[Partition, int], ...]
    exclusion_ids: tuple[str, ...]
    lineage_ids: tuple[str, ...]
    checks: tuple[str, ...]
    preprocessing_state_ids: tuple[str, ...] = ()

    def _normalize(self) -> None:
        for name in ("exclusion_ids", "lineage_ids", "checks", "preprocessing_state_ids"):
            values = getattr(self, name)
            require(len(set(values)) == len(values), "duplicate contamination audit evidence")
            object.__setattr__(self, name, tuple(sorted(values)))
        for name in ("sample_counts", "partition_counts"):
            values = getattr(self, name)
            require(
                len({x[0] for x in values}) == len(values) and all(x[1] >= 0 for x in values),
                "invalid audit counts",
            )
            object.__setattr__(self, name, tuple(sorted(values, key=lambda x: x[0].value)))

    def _validate(self) -> None:
        validate_fingerprint(self.dataset_id, "r_dataset")
        if self.fold_id is not None:
            validate_fingerprint(self.fold_id, "r_fold")
        for identity in self.preprocessing_state_ids:
            validate_fingerprint(identity, "r_preprocessing_state")
        for identity in (*self.exclusion_ids, *self.lineage_ids):
            validate_fingerprint(identity)


@contract("r_sample_audit")
@dataclass(frozen=True, slots=True)
class SampleContaminationAudit(Artifact):
    dataset_id: str
    sample_id: str
    fold_id: str | None
    state: SampleState
    partition: Partition | None
    evidence_ids: tuple[str, ...]
    checks: tuple[str, ...]

    def _normalize(self) -> None:
        for name in ("evidence_ids", "checks"):
            values = getattr(self, name)
            require(len(set(values)) == len(values), "duplicate sample audit evidence")
            object.__setattr__(self, name, tuple(sorted(values)))

    def _validate(self) -> None:
        validate_fingerprint(self.dataset_id, "r_dataset")
        validate_fingerprint(self.sample_id, "r_sample")
        require((self.fold_id is None) == (self.partition is None), "partial sample audit fold")
        if self.fold_id is not None:
            validate_fingerprint(self.fold_id, "r_fold")
        for identity in self.evidence_ids:
            validate_fingerprint(identity)

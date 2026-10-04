"""Compact dataset manifests pin exact selections, columns and all failed cells."""

from dataclasses import dataclass

from afre.features import ValueType
from afre.ids import validate_fingerprint
from afre.research_datasets.schema import BUILDER_VERSION, ColumnRole, DatasetCompleteness
from afre.schema import Artifact, contract, require
from afre.version import ENGINE_VERSION


@contract("r_column")
@dataclass(frozen=True, slots=True)
class DatasetColumn(Artifact):
    name: str
    role: ColumnRole
    value_type: ValueType
    definition_id: str | None

    def _validate(self) -> None:
        if self.role is ColumnRole.FEATURE:
            require(self.definition_id is not None, "feature column requires definition")
            assert self.definition_id is not None
            validate_fingerprint(self.definition_id, "feature_definition")
            require(
                not self.name.startswith(("target.", "label.")),
                "target cannot become feature column",
            )
        elif self.role is ColumnRole.TARGET:
            require(self.definition_id is not None, "target column requires definition")
            assert self.definition_id is not None
            validate_fingerprint(self.definition_id, "target_definition")


@contract("r_columns")
@dataclass(frozen=True, slots=True)
class DatasetColumnManifest(Artifact):
    columns: tuple[DatasetColumn, ...]

    def _normalize(self) -> None:
        self.ordered("columns", "name")

    def _validate(self) -> None:
        require(bool(self.columns), "empty dataset column manifest")


@contract("r_input_build")
@dataclass(frozen=True, slots=True)
class ResearchInputBuild(Artifact):
    definition_id: str
    selection_ids: tuple[str, ...]
    processing_cutoff_ns: int
    constructed_ns: int

    def _normalize(self) -> None:
        require(
            bool(self.selection_ids)
            and len(set(self.selection_ids)) == len(self.selection_ids),
            "empty/duplicate research input selections",
        )
        object.__setattr__(self, "selection_ids", tuple(sorted(self.selection_ids)))

    def _validate(self) -> None:
        validate_fingerprint(self.definition_id, "r_dataset_definition")
        require(
            self.constructed_ns >= self.processing_cutoff_ns,
            "research build before processing cutoff",
        )
        for identity in self.selection_ids:
            validate_fingerprint(identity, "r_selection")


@contract("r_dataset")
@dataclass(frozen=True, slots=True)
class ResearchDatasetManifest(Artifact):
    definition_id: str
    input_build_id: str
    columns: DatasetColumnManifest
    sample_ids: tuple[str, ...]
    completeness: DatasetCompleteness
    processing_cutoff_ns: int
    constructed_ns: int
    builder_version: str = BUILDER_VERSION
    engine_version: str = ENGINE_VERSION

    def _validate(self) -> None:
        validate_fingerprint(self.definition_id, "r_dataset_definition")
        validate_fingerprint(self.input_build_id, "r_input_build")
        require(
            bool(self.sample_ids) and len(set(self.sample_ids)) == len(self.sample_ids),
            "empty/duplicate dataset samples",
        )
        require(
            self.constructed_ns >= self.processing_cutoff_ns,
            "dataset constructed before processing cutoff",
        )
        for identity in self.sample_ids:
            validate_fingerprint(identity, "r_sample")

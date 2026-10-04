"""Explicit, data-only provenance and immutable scalar parameters."""

from dataclasses import dataclass

from afre.ids import validate_digest, validate_fingerprint
from afre.schema import Artifact, contract, require

Scalar = str | int | float | bool


@contract("parameter")
@dataclass(frozen=True, slots=True)
class Parameter(Artifact):
    name: str
    value: Scalar


@contract("provenance")
@dataclass(frozen=True, slots=True)
class ProvenanceRef(Artifact):
    system: str
    artifact_id: str
    source_version: str
    payload_sha256: str

    def _validate(self) -> None:
        validate_digest(self.payload_sha256)


@contract("feature_dependency")
@dataclass(frozen=True, slots=True)
class FeatureDependency(Artifact):
    definition_id: str
    feature_id: str
    available_ns: int

    def _validate(self) -> None:
        validate_fingerprint(self.definition_id, "feature_definition")
        validate_fingerprint(self.feature_id, "feature_value")


@contract("reconstruction_proof")
@dataclass(frozen=True, slots=True)
class ReconstructionProof(Artifact):
    evidence: ProvenanceRef
    historical_computation_available_ns: int
    reconstructed_ns: int

    def _validate(self) -> None:
        require(
            self.historical_computation_available_ns <= self.reconstructed_ns,
            "reconstruction precedes historical computation",
        )


@contract("feature_lineage")
@dataclass(frozen=True, slots=True)
class FeatureLineage(Artifact):
    upstream: tuple[ProvenanceRef, ...]
    dependencies: tuple[FeatureDependency, ...]
    transformation_version: str
    parameters: tuple[Parameter, ...]
    build_context: str
    code_version: str
    computation_available_ns: int | None = None
    reconstruction: ReconstructionProof | None = None

    def _normalize(self) -> None:
        self.ordered("upstream", "fingerprint")
        self.ordered("dependencies", "definition_id")
        self.ordered("parameters", "name")

    def _validate(self) -> None:
        require(bool(self.upstream) or bool(self.dependencies), "lineage requires provenance")
        for source in self.upstream:
            require(
                not source.artifact_id.startswith(("afre.target_row:", "afre.target_spec:")),
                "target artifacts cannot be feature provenance",
            )
        if self.dependencies:
            require(self.computation_available_ns is not None, "computation clock required")
        if self.reconstruction is not None:
            require(
                self.computation_available_ns == self.reconstruction.reconstructed_ns,
                "reconstruction clock mismatch",
            )

    @property
    def availability_floor_ns(self) -> int:
        computation = self.computation_available_ns or 0
        if self.reconstruction is not None:
            computation = self.reconstruction.historical_computation_available_ns
        return max((computation, *(item.available_ns for item in self.dependencies)))

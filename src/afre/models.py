"""Model specification and safe artifact metadata, never model training/loading."""

from dataclasses import dataclass
from enum import Enum

from afre.features import FeatureSet
from afre.ids import validate_digest, validate_fingerprint
from afre.lineage import Parameter
from afre.schema import Artifact, contract, enum, require
from afre.targets import TargetSpec


@contract("training_policy")
@dataclass(frozen=True, slots=True)
class TrainingPolicy(Artifact):
    name: str
    version: str
    parameters: tuple[Parameter, ...]

    def _normalize(self) -> None:
        self.ordered("parameters", "name")


@contract("model_spec")
@dataclass(frozen=True, slots=True)
class ModelSpec(Artifact):
    family: str
    hyperparameters: tuple[Parameter, ...]
    feature_set: FeatureSet
    target: TargetSpec
    training_policy: TrainingPolicy
    random_seed: int
    implementation_version: str

    def _normalize(self) -> None:
        self.ordered("hyperparameters", "name")

    def _validate(self) -> None:
        require(0 <= self.random_seed < 2**64, "seed outside uint64")


@enum
class ModelArtifactFormat(Enum):
    CANONICAL_JSON = "canonical_json"
    SAFETENSORS = "safetensors"
    ONNX = "onnx"


@contract("model_artifact")
@dataclass(frozen=True, slots=True)
class ModelArtifact(Artifact):
    spec: ModelSpec
    training_dataset_id: str
    fit_cutoff_ns: int
    artifact_sha256: str
    format: ModelArtifactFormat
    metric_ids: tuple[str, ...]
    created_available_ns: int

    def _normalize(self) -> None:
        object.__setattr__(self, "metric_ids", tuple(sorted(self.metric_ids)))

    def _validate(self) -> None:
        validate_fingerprint(self.training_dataset_id, "dataset_manifest")
        validate_digest(self.artifact_sha256)
        require(
            self.created_available_ns >= self.fit_cutoff_ns, "model created before fit cutoff"
        )
        require(
            len(set(self.metric_ids)) == len(self.metric_ids), "duplicate metric references"
        )
        for metric in self.metric_ids:
            validate_fingerprint(metric, "metric_record")

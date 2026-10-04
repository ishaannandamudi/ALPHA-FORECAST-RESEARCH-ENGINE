"""Reproducible experiment specifications and immutable result revisions."""

from dataclasses import dataclass
from enum import Enum

from afre.datasets import DatasetManifest
from afre.evaluation import CostPolicy, EvaluationPolicy, MetricRecord, SplitPolicy
from afre.ids import validate_fingerprint
from afre.models import ModelSpec
from afre.schema import Artifact, contract, enum, require


@contract("experiment_spec")
@dataclass(frozen=True, slots=True)
class ExperimentSpec(Artifact):
    name: str
    dataset: DatasetManifest
    model: ModelSpec
    split: SplitPolicy
    evaluation: EvaluationPolicy
    costs: CostPolicy
    random_seed: int
    code_version: str

    def _validate(self) -> None:
        require(
            self.model.feature_set == self.dataset.feature_set, "model/dataset feature mismatch"
        )
        require(self.model.target in self.dataset.targets, "model/dataset target mismatch")
        require(self.random_seed == self.model.random_seed, "experiment/model seed mismatch")
        require(
            self.dataset.origins.start_ns <= self.split.training.start_ns
            and self.split.test.end_ns <= self.dataset.origins.end_ns,
            "split outside dataset range",
        )


@enum
class ExperimentStatus(Enum):
    PLANNED = "planned"
    COMPLETED = "completed"
    FAILED = "failed"


@contract("experiment_result")
@dataclass(frozen=True, slots=True)
class ExperimentResult(Artifact):
    spec: ExperimentSpec
    status: ExperimentStatus
    input_ids: tuple[str, ...]
    metrics: tuple[MetricRecord, ...]
    model_artifact_id: str | None
    created_available_ns: int
    failure_reason: str | None = None

    def _normalize(self) -> None:
        self.ordered("metrics", "fingerprint")
        object.__setattr__(self, "input_ids", tuple(sorted(self.input_ids)))

    def _validate(self) -> None:
        require(
            bool(self.input_ids) and len(set(self.input_ids)) == len(self.input_ids),
            "empty or duplicate result inputs",
        )
        for item in self.input_ids:
            validate_fingerprint(item)
        require(self.spec.dataset.fingerprint in self.input_ids, "dataset lineage missing")
        if self.model_artifact_id is not None:
            validate_fingerprint(self.model_artifact_id, "model_artifact")
        if self.status is ExperimentStatus.COMPLETED:
            require(
                self.model_artifact_id is not None, "completed result requires model artifact"
            )
            require(
                self.created_available_ns >= self.spec.split.evaluation_cutoff_ns,
                "completed result before evaluation cutoff",
            )
        require(
            (self.failure_reason is not None) == (self.status is ExperimentStatus.FAILED),
            "failed status requires exactly one failure reason",
        )
        for metric in self.metrics:
            require(metric.name in self.spec.evaluation.metrics, "undeclared metric")
            require(
                metric.origins.start_ns >= self.spec.split.validation.start_ns
                and metric.origins.end_ns <= self.spec.split.test.end_ns,
                "metric range outside evaluation",
            )
            require(
                metric.origins.end_ns <= self.created_available_ns,
                "metric unavailable at result creation",
            )

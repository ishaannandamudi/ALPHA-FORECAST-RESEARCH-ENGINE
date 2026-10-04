"""Evaluation and split policy metadata; no splitter or metric engine."""

from dataclasses import dataclass

from afre.lineage import Parameter
from afre.schema import Artifact, contract, require
from afre.time import TimeRange


@contract("split_policy")
@dataclass(frozen=True, slots=True)
class SplitPolicy(Artifact):
    training: TimeRange
    validation: TimeRange
    test: TimeRange
    training_cutoff_ns: int
    evaluation_cutoff_ns: int
    purge_overlapping_labels: bool
    embargo_ns: int
    implementation_version: str

    def _validate(self) -> None:
        require(
            self.training.end_ns <= self.training_cutoff_ns < self.validation.start_ns,
            "training cutoff must precede validation origins",
        )
        require(
            self.validation.end_ns + self.embargo_ns <= self.test.start_ns,
            "split overlap or embargo violation",
        )
        require(
            self.training_cutoff_ns + self.embargo_ns < self.validation.start_ns,
            "training embargo violation",
        )
        require(
            self.evaluation_cutoff_ns >= self.test.end_ns, "evaluation cutoff before test end"
        )
        require(self.purge_overlapping_labels, "overlapping labels must be purged later")


@contract("evaluation_policy")
@dataclass(frozen=True, slots=True)
class EvaluationPolicy(Artifact):
    name: str
    version: str
    metrics: tuple[str, ...]

    def _normalize(self) -> None:
        object.__setattr__(self, "metrics", tuple(sorted(self.metrics)))

    def _validate(self) -> None:
        require(
            bool(self.metrics) and len(set(self.metrics)) == len(self.metrics),
            "empty or duplicate evaluation metrics",
        )


@contract("cost_policy")
@dataclass(frozen=True, slots=True)
class CostPolicy(Artifact):
    name: str
    version: str
    parameters: tuple[Parameter, ...]

    def _normalize(self) -> None:
        self.ordered("parameters", "name")


@contract("metric_record")
@dataclass(frozen=True, slots=True)
class MetricRecord(Artifact):
    name: str
    implementation_version: str
    value: float
    sample_count: int
    origins: TimeRange

    def _validate(self) -> None:
        require(self.sample_count > 0, "metric requires observations")

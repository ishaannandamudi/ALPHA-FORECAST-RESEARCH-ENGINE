"""Supplied learned-state contracts; no fold fitting or global statistics."""

from dataclasses import dataclass
from enum import Enum

from afre.feature_store.models import RegisteredFeatureDefinition
from afre.ids import validate_fingerprint
from afre.lineage import Parameter
from afre.schema import Artifact, contract, enum, require


@enum
class NormalizationMethod(Enum):
    NONE = "none"
    STANDARDIZE = "standardize"
    ROBUST_STANDARDIZE = "robust_standardize"
    MINMAX = "minmax"
    RANK = "rank"
    WINSORIZE = "winsorize"


@contract("fs_normalization_spec")
@dataclass(frozen=True, slots=True)
class NormalizationSpec(Artifact):
    feature: RegisteredFeatureDefinition
    method: NormalizationMethod
    implementation_version: str


@contract("fs_normalization_state")
@dataclass(frozen=True, slots=True)
class NormalizationState(Artifact):
    spec: NormalizationSpec
    fit_sample_ids: tuple[str, ...]
    fit_cutoff_ns: int
    available_ns: int
    parameters: tuple[Parameter, ...]
    source_dataset_id: str

    def _normalize(self) -> None:
        self.ordered("parameters", "name")
        require(
            len(set(self.fit_sample_ids)) == len(self.fit_sample_ids),
            "duplicate fit observations",
        )
        object.__setattr__(self, "fit_sample_ids", tuple(sorted(self.fit_sample_ids)))

    def _validate(self) -> None:
        require(
            self.available_ns >= self.fit_cutoff_ns, "normalization available before fit cutoff"
        )
        require(bool(self.fit_sample_ids), "normalization requires exact fit sample")
        for identity in self.fit_sample_ids:
            validate_fingerprint(identity, "fs_vintage")
        require(
            self.source_dataset_id in self.spec.feature.source_dataset_ids,
            "normalization source dataset mismatch",
        )
        params = {item.name: item.value for item in self.parameters}
        if self.spec.method is NormalizationMethod.STANDARDIZE:
            require(set(params) == {"mean", "stddev"}, "standardization needs mean/stddev")
            require(
                all(type(value) in (int, float) for value in params.values()),
                "normalization statistics must be numeric",
            )
            require(float(params["stddev"]) > 0, "positive standard deviation required")
        elif self.spec.method is NormalizationMethod.NONE:
            require(not params, "NONE normalization has no learned parameters")
        else:
            require(bool(params), "learned normalization state requires supplied parameters")

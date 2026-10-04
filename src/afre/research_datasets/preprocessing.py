"""Train-only simple statistics using AFRE-1 normalization artifacts."""

import math
from dataclasses import dataclass
from statistics import fmean, median, pstdev

from afre.feature_store.normalization import (
    NormalizationMethod,
    NormalizationSpec,
    NormalizationState,
)
from afre.ids import validate_fingerprint
from afre.lineage import Parameter
from afre.research_datasets.schema import (
    PREPROCESSING_VERSION,
    PreprocessingScope,
    PurgeScope,
    ZeroScaleRule,
)
from afre.schema import Artifact, contract, require
from afre.time import validate_timestamp


@contract("r_preprocessing_spec")
@dataclass(frozen=True, slots=True)
class FoldPreprocessingSpec(Artifact):
    normalization: NormalizationSpec
    zero_scale: ZeroScaleRule = ZeroScaleRule.FAIL
    lower_quantile: float = 0.05
    upper_quantile: float = 0.95
    implementation_version: str = PREPROCESSING_VERSION
    scope: PreprocessingScope = PreprocessingScope.TRAIN_PARTITION
    group_scope: PurgeScope | None = None

    def _validate(self) -> None:
        require(
            self.normalization.method is not NormalizationMethod.RANK
            or self.scope is not PreprocessingScope.TRAIN_PARTITION,
            "cross-sectional rank fitting is deferred",
        )
        require(
            self.normalization.feature.definition.value_type.value in ("number", "integer"),
            "numeric preprocessing feature required",
        )
        require(0 <= self.lower_quantile < self.upper_quantile <= 1, "invalid winsor quantiles")
        require(
            (self.group_scope is not None)
            == (self.scope is PreprocessingScope.WITHIN_ORIGIN_GROUP),
            "within-origin group preprocessing requires exact group scope",
        )
        require(
            self.group_scope is None
            or self.group_scope in (PurgeScope.ISSUER, PurgeScope.SECTOR, PurgeScope.MARKET),
            "unsupported preprocessing group scope",
        )
        require(
            self.implementation_version == PREPROCESSING_VERSION,
            "unsupported preprocessing version",
        )


@contract("r_preprocessing_state")
@dataclass(frozen=True, slots=True)
class FoldPreprocessingState(Artifact):
    dataset_id: str
    fold_id: str
    spec: FoldPreprocessingSpec
    normalization: NormalizationState
    fit_sample_ids: tuple[str, ...]
    skipped_sample_ids: tuple[str, ...]

    def _normalize(self) -> None:
        for name in ("fit_sample_ids", "skipped_sample_ids"):
            values = getattr(self, name)
            require(len(set(values)) == len(values), "duplicate preprocessing sample")
            object.__setattr__(self, name, tuple(sorted(values)))

    def _validate(self) -> None:
        validate_fingerprint(self.dataset_id, "r_dataset")
        validate_fingerprint(self.fold_id, "r_fold")
        require(bool(self.fit_sample_ids), "empty preprocessing fit")
        require(
            not set(self.fit_sample_ids) & set(self.skipped_sample_ids), "fit/skipped overlap"
        )
        require(
            self.normalization.spec == self.spec.normalization, "normalization spec mismatch"
        )
        for identity in (*self.fit_sample_ids, *self.skipped_sample_ids):
            validate_fingerprint(identity, "r_sample")


def quantile(values: tuple[float, ...], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low = math.floor(position)
    high = math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def fit_parameters(
    spec: FoldPreprocessingSpec, values: tuple[float, ...]
) -> tuple[Parameter, ...]:
    require(
        spec.scope is PreprocessingScope.TRAIN_PARTITION,
        "within-origin/group preprocessing is prepared and deferred",
    )
    require(
        bool(values) and all(math.isfinite(value) for value in values), "invalid fit values"
    )
    method = spec.normalization.method
    if method is NormalizationMethod.NONE:
        params: dict[str, float] = {}
    elif method is NormalizationMethod.STANDARDIZE:
        params = {"mean": fmean(values), "stddev": pstdev(values)}
    elif method is NormalizationMethod.ROBUST_STANDARDIZE:
        params = {
            "median": median(values),
            "iqr": quantile(values, 0.75) - quantile(values, 0.25),
        }
    elif method is NormalizationMethod.MINMAX:
        params = {"minimum": min(values), "range": max(values) - min(values)}
    else:
        require(method is NormalizationMethod.WINSORIZE, "unsupported normalization method")
        params = {
            "lower": quantile(values, spec.lower_quantile),
            "upper": quantile(values, spec.upper_quantile),
        }
    for name in ("stddev", "iqr", "range"):
        if name in params and params[name] == 0:
            require(spec.zero_scale is ZeroScaleRule.UNIT_SCALE, "zero preprocessing scale")
            params[name] = 1.0
    return tuple(Parameter(name, value) for name, value in sorted(params.items()))


def apply_state(
    state: FoldPreprocessingState, value: float | None, application_ns: int
) -> float | None:
    validate_timestamp(application_ns)
    require(
        application_ns >= state.normalization.available_ns,
        "preprocessing applied before availability",
    )
    if value is None:
        return None
    params = {
        parameter.name: float(parameter.value) for parameter in state.normalization.parameters
    }
    method = state.normalization.spec.method
    if method is NormalizationMethod.NONE:
        return value
    if method is NormalizationMethod.STANDARDIZE:
        return (value - params["mean"]) / params["stddev"]
    if method is NormalizationMethod.ROBUST_STANDARDIZE:
        return (value - params["median"]) / params["iqr"]
    if method is NormalizationMethod.MINMAX:
        return (value - params["minimum"]) / params["range"]
    return min(params["upper"], max(params["lower"], value))

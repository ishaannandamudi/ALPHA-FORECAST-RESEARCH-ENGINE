"""Identity-bearing reservations and fixed calibration parameters; no selection."""

from dataclasses import dataclass

from afre.calibration.schema import (
    IMPLEMENTATION_VERSION,
    CalibrationMethod,
    CalibrationPartitionPolicy,
    DriftMetric,
    EmptyBinPolicy,
    ExtrapolationPolicy,
    TiePolicy,
)
from afre.ids import validate_fingerprint
from afre.probabilistic.definitions import (
    QuantileDefinition,
    QuantileInterval,
    ThresholdDefinition,
)
from afre.schema import Artifact, contract, require
from afre.statistical_models.artifacts import unique_ids
from afre.target_engine.definitions import TargetDefinition
from afre.time import TimeRange


@contract("c_partition")
@dataclass(frozen=True, slots=True)
class CalibrationPartition(Artifact):
    policy: CalibrationPartitionPolicy
    fold_id: str
    reserved_sample_ids: tuple[str, ...]
    origin_range: TimeRange
    rolling_count: int | None = None
    strict_disjoint: bool = True
    window_basis: str = "last-n-resolved-origin-security-sample-v1"

    def _normalize(self) -> None:
        object.__setattr__(self, "reserved_sample_ids", tuple(sorted(self.reserved_sample_ids)))

    def _validate(self) -> None:
        validate_fingerprint(self.fold_id, "r_fold")
        unique_ids(self.reserved_sample_ids, "r_sample")
        require(bool(self.reserved_sample_ids), "explicit calibration reservation required")
        require(self.strict_disjoint, "only strict disjoint calibration is supported")
        require(
            (self.rolling_count is not None)
            == (self.policy is CalibrationPartitionPolicy.ROLLING_PAST),
            "rolling window/policy mismatch",
        )
        require(self.rolling_count is None or self.rolling_count > 0, "positive rolling window")
        require(
            self.window_basis == "last-n-resolved-origin-security-sample-v1",
            "unknown window basis",
        )


@contract("c_bins")
@dataclass(frozen=True, slots=True)
class CalibrationBinDefinition(Artifact):
    edges: tuple[float, ...] = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
    minimum_count: int = 1
    empty_policy: EmptyBinPolicy = EmptyBinPolicy.RAW
    convention: str = "left-closed-right-open-last-closed-empirical-rate-v1"

    def _validate(self) -> None:
        require(
            2 <= len(self.edges) <= 257
            and self.edges[0] == 0.0
            and self.edges[-1] == 1.0
            and all(a < b for a, b in zip(self.edges, self.edges[1:], strict=False)),
            "bin edges must increase from zero to one",
        )
        require(self.minimum_count > 0, "positive bin minimum")
        require(
            self.convention == "left-closed-right-open-last-closed-empirical-rate-v1",
            "unknown bins",
        )


@contract("c_spec")
@dataclass(frozen=True, slots=True)
class CalibrationSpec(Artifact):
    raw_model_id: str
    raw_spec_id: str
    target: TargetDefinition
    method: CalibrationMethod
    partition: CalibrationPartition
    cutoff_ns: int
    minimum_samples: int
    events: ThresholdDefinition
    quantiles: QuantileDefinition
    bins: CalibrationBinDefinition = CalibrationBinDefinition()
    interval: QuantileInterval | None = None
    miscoverage_alpha: float | None = None
    tie_policy: TiePolicy = TiePolicy.AGGREGATE_EQUAL_INPUT
    extrapolation_policy: ExtrapolationPolicy = ExtrapolationPolicy.CLAMP_EDGE
    interpolation_version: str = "linear-between-block-edges-v1"
    quantile_estimator: str = "type7-residual-q-v1"
    conformal_estimator: str = "ceil-n-plus-one-decimal-alpha-v1"
    implementation_version: str = IMPLEMENTATION_VERSION
    random_seed: int = 0

    def _validate(self) -> None:
        validate_fingerprint(self.raw_model_id, "p_artifact")
        validate_fingerprint(self.raw_spec_id, "p_spec")
        require(self.minimum_samples > 0, "positive calibration minimum")
        require(0 <= self.random_seed < 2**64, "calibration seed outside uint64")
        conformal = self.method in (
            CalibrationMethod.CONFORMAL_ABSOLUTE_RESIDUAL,
            CalibrationMethod.ROLLING_CONFORMAL,
        )
        require((self.miscoverage_alpha is not None) == conformal, "alpha/method mismatch")
        if conformal:
            alpha = self.miscoverage_alpha
            assert alpha is not None
            require(
                0 < alpha < 1 and self.interval is not None, "conformal alpha/interval invalid"
            )
            assert self.interval is not None
            require(
                self.interval.lower == alpha / 2 and self.interval.upper == 1 - alpha / 2,
                "conformal central interval/alpha mismatch",
            )
        if self.interval is not None:
            require(
                {self.interval.lower, self.interval.upper} <= set(self.quantiles.levels),
                "interval levels missing",
            )
        require(
            self.method
            not in (
                CalibrationMethod.BINNED_PROBABILITY,
                CalibrationMethod.ISOTONIC_PROBABILITY,
            )
            or bool(self.events.requests),
            "probability method needs explicit events",
        )
        require(
            self.method is not CalibrationMethod.ROLLING_CONFORMAL
            or self.partition.policy is CalibrationPartitionPolicy.ROLLING_PAST,
            "rolling conformal requires rolling past reservation",
        )
        require(
            self.implementation_version == IMPLEMENTATION_VERSION
            and self.interpolation_version == "linear-between-block-edges-v1"
            and self.quantile_estimator == "type7-residual-q-v1"
            and self.conformal_estimator == "ceil-n-plus-one-decimal-alpha-v1",
            "unknown calibration implementation",
        )


@contract("c_request")
@dataclass(frozen=True, slots=True)
class CalibrationRequest(Artifact):
    raw_forecast_id: str
    target_id: str

    def _validate(self) -> None:
        validate_fingerprint(self.raw_forecast_id, "p_forecast")
        validate_fingerprint(self.target_id, "target_vintage")


@contract("c_drift_spec")
@dataclass(frozen=True, slots=True)
class CalibrationDriftSpec(Artifact):
    window_evaluations: int
    minimum_pairs: int
    metric: DriftMetric
    threshold: float
    implementation_version: str = "fixed-evaluation-window-v1"

    def _validate(self) -> None:
        require(
            self.window_evaluations > 0 and self.minimum_pairs > 0 and self.threshold >= 0,
            "invalid drift parameters",
        )
        require(
            self.implementation_version == "fixed-evaluation-window-v1", "unknown drift version"
        )

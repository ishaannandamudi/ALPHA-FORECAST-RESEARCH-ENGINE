"""Label contracts only; target construction is deferred to AFRE-2."""

from dataclasses import dataclass
from enum import Enum

from afre.features import DataQuality
from afre.forecast import ForecastOrigin
from afre.horizons import ForecastHorizon, HorizonBasis
from afre.ids import InstrumentId, validate_fingerprint
from afre.schema import Artifact, contract, enum, require
from afre.time import TimeRange, validate_timestamp


@enum
class TargetType(Enum):
    SIMPLE_RETURN = "simple_return"
    LOG_RETURN = "log_return"
    RESIDUAL_RETURN = "residual_return"
    ABSOLUTE_RETURN = "absolute_return"
    REALIZED_VOLATILITY = "realized_volatility"
    DOWNSIDE_RETURN = "downside_return"
    MAX_ADVERSE_EXCURSION = "max_adverse_excursion"
    MAX_FAVORABLE_EXCURSION = "max_favorable_excursion"


@enum
class TargetWindowConvention(Enum):
    AFTER_ORIGIN_THROUGH_ENDPOINT = "(origin, endpoint]"


@contract("target_spec")
@dataclass(frozen=True, slots=True)
class TargetSpec(Artifact):
    target_type: TargetType
    horizon: ForecastHorizon
    unit: str
    implementation_version: str
    benchmark: InstrumentId | None = None
    window_convention: TargetWindowConvention = (
        TargetWindowConvention.AFTER_ORIGIN_THROUGH_ENDPOINT
    )

    def _validate(self) -> None:
        require(
            (self.benchmark is not None) == (self.target_type is TargetType.RESIDUAL_RETURN),
            "benchmark required only for residual return",
        )


@contract("target_row")
@dataclass(frozen=True, slots=True)
class ForecastTargetRow(Artifact):
    origin: ForecastOrigin
    target: TargetSpec
    window: TimeRange
    value: float | int | None
    available_ns: int
    market_dataset_id: str
    quality: DataQuality
    endpoint_evidence_id: str | None = None

    def _validate(self) -> None:
        require(
            self.window.start_ns == self.origin.timestamp_ns, "target window origin mismatch"
        )
        require(self.available_ns >= self.window.end_ns, "target unavailable before completion")
        validate_fingerprint(self.market_dataset_id)
        if self.target.horizon.basis is HorizonBasis.ELAPSED_TIME:
            require(
                self.window.end_ns
                == self.origin.timestamp_ns + (self.target.horizon.duration_ns or 0),
                "target endpoint mismatch",
            )
        else:
            require(
                self.endpoint_evidence_id is not None, "resolved endpoint evidence required"
            )
        if self.endpoint_evidence_id is not None:
            validate_fingerprint(self.endpoint_evidence_id)
        require(
            (self.value is not None) == (self.quality is not DataQuality.INVALID),
            "target value/quality mismatch",
        )

    def eligible_at(self, training_cutoff_ns: int) -> bool:
        validate_timestamp(training_cutoff_ns)
        return (
            self.origin.timestamp_ns < training_cutoff_ns
            and self.available_ns <= training_cutoff_ns
            and self.window.end_ns <= training_cutoff_ns
            and self.value is not None
            and self.quality is DataQuality.VERIFIED
        )

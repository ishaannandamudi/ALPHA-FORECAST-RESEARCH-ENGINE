"""Supplied immutable methods, assumptions and exact source identities; no selection."""

from dataclasses import dataclass

from afre.ids import validate_fingerprint
from afre.schema import Artifact, contract, require
from afre.statistical_models.artifacts import unique_ids
from afre.target_engine.definitions import TargetDefinition
from afre.uncertainty.schema import (
    UNCERTAINTY_IMPLEMENTATION,
    ClosurePolicy,
    CovarianceAssumption,
    UncertaintyMeasure,
    UncertaintyType,
)


@contract("unc_request")
@dataclass(frozen=True, slots=True)
class UncertaintyRequest(Artifact):
    component: UncertaintyType
    measure: UncertaintyMeasure = UncertaintyMeasure.VARIANCE


@contract("unc_parameter_spec")
@dataclass(frozen=True, slots=True)
class ParameterUncertaintySpec(Artifact):
    model_id: str
    assumption: CovarianceAssumption
    minimum_samples: int = 3
    tolerance: float = 1e-10
    condition_limit: float = 1e10
    seed: int = 0
    implementation_version: str = "pivoted-QR-OLS-covariance-v1"

    def _validate(self) -> None:
        validate_fingerprint(self.model_id)
        require(
            self.model_id.startswith(("afre.m_artifact:", "afre.nl_model:", "afre.sq_model:")),
            "parameter method requires an existing fitted linear/tree artifact",
        )
        require(
            3 <= self.minimum_samples <= 2000
            and 0 < self.tolerance <= 1e-6
            and 1 <= self.condition_limit <= 1e12
            and self.seed >= 0,
            "parameter numerical/count policy",
        )
        require(
            self.implementation_version == "pivoted-QR-OLS-covariance-v1",
            "unsupported parameter estimator",
        )


@contract("unc_spec")
@dataclass(frozen=True, slots=True)
class UncertaintySpec(Artifact):
    target: TargetDefinition
    forecast_id: str
    requests: tuple[UncertaintyRequest, ...]
    closure: ClosurePolicy = ClosurePolicy.NON_ADDITIVE_DIAGNOSTICS_ONLY
    covariance_id: str | None = None
    alternative_forecast_ids: tuple[str, ...] = ()
    interval_levels: tuple[float, float] = (0.05, 0.95)
    minimum_count: int = 2
    tolerance: float = 1e-10
    seed: int = 0
    calibration_policy: str = "source-state-only-no-fit-v1"
    identifiability_policy: str = "explicit-assumptions-no-invented-attribution-v1"
    implementation_version: str = UNCERTAINTY_IMPLEMENTATION

    def _normalize(self) -> None:
        require(
            len({r.component for r in self.requests}) == len(self.requests),
            "one measure per uncertainty category",
        )
        object.__setattr__(
            self, "requests", tuple(sorted(self.requests, key=lambda r: r.component.value))
        )
        unique_ids(self.alternative_forecast_ids)
        object.__setattr__(
            self, "alternative_forecast_ids", tuple(sorted(self.alternative_forecast_ids))
        )

    def _validate(self) -> None:
        validate_fingerprint(self.forecast_id)
        require(
            bool(self.requests)
            and len(self.requests) <= 16
            and UncertaintyType.TOTAL_PREDICTIVE in {r.component for r in self.requests},
            "uncertainty requires total and bounded explicit components",
        )
        if self.covariance_id:
            validate_fingerprint(self.covariance_id, "unc_covariance")
        require(
            0 < self.interval_levels[0] < self.interval_levels[1] < 1
            and 2 <= self.minimum_count <= 2000
            and 0 < self.tolerance <= 1e-6
            and len(self.alternative_forecast_ids) <= 32
            and self.seed >= 0,
            "uncertainty numerical/interval/count policy",
        )
        require(
            self.closure is not ClosurePolicy.APPROXIMATE_ADDITIVE,
            "approximate additive methods are unsupported",
        )
        require(
            self.calibration_policy == "source-state-only-no-fit-v1"
            and self.identifiability_policy == "explicit-assumptions-no-invented-attribution-v1"
            and self.implementation_version == UNCERTAINTY_IMPLEMENTATION,
            "unsupported uncertainty policy/version",
        )

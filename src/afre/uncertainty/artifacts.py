"""Immutable evidence, components, exact closure and descriptive metadata."""

from dataclasses import dataclass

from afre.forecast import ForecastOrigin
from afre.ids import validate_fingerprint
from afre.research_datasets.schema import Partition
from afre.schema import Artifact, contract, require
from afre.statistical_models.artifacts import unique_ids
from afre.statistical_models.linear_algebra import finite, total
from afre.uncertainty.schema import (
    ClosurePolicy,
    IdentifiabilityStatus,
    UncertaintyMeasure,
    UncertaintyType,
)

VALUE_STATUSES = (
    IdentifiabilityStatus.IDENTIFIED,
    IdentifiabilityStatus.PARTIALLY_IDENTIFIED,
    IdentifiabilityStatus.PROXY_ONLY,
)


@contract("unc_covariance")
@dataclass(frozen=True, slots=True)
class ParameterCovariance(Artifact):
    spec_id: str
    model_id: str
    target_id: str
    horizon_id: str
    fold_id: str
    matrix_id: str
    train_sample_ids: tuple[str, ...]
    status: IdentifiabilityStatus
    reason: str
    covariance: tuple[tuple[float, ...], ...]
    residual_variance: float | None
    residual_sum_squares: float | None
    degrees_of_freedom: int
    design_rank: int
    intercept_included: bool
    condition_proxy: float | None
    cutoff_ns: int
    computed_ns: int
    available_ns: int

    def _normalize(self) -> None:
        unique_ids(self.train_sample_ids, "r_sample")
        object.__setattr__(self, "train_sample_ids", tuple(sorted(self.train_sample_ids)))

    def _validate(self) -> None:
        for identity, domain in (
            (self.spec_id, "unc_parameter_spec"),
            (self.target_id, "target_definition"),
            (self.fold_id, "r_fold"),
        ):
            validate_fingerprint(identity, domain)
        validate_fingerprint(self.model_id)
        validate_fingerprint(self.matrix_id)
        validate_fingerprint(self.horizon_id)
        require(
            self.available_ns >= self.computed_ns >= self.cutoff_ns,
            "parameter actual computation clocks",
        )
        present = self.status is IdentifiabilityStatus.PARTIALLY_IDENTIFIED
        require(
            bool(self.covariance) == present
            and (self.residual_variance is not None) == present,
            "covariance value/status mismatch",
        )
        require(
            self.degrees_of_freedom >= 0 and self.design_rank >= 0,
            "negative covariance degrees/rank",
        )
        if present:
            assert self.residual_variance is not None and self.residual_sum_squares is not None
            n = len(self.covariance)
            require(
                n == self.design_rank
                and 0 < n <= 17
                and self.degrees_of_freedom > 0
                and self.degrees_of_freedom == len(self.train_sample_ids) - n
                and self.residual_variance >= 0
                and self.residual_sum_squares >= 0
                and self.residual_variance
                == self.residual_sum_squares / self.degrees_of_freedom
                and self.condition_proxy is not None
                and self.condition_proxy >= 1,
                "covariance estimator dimensions/denominator",
            )
            require(
                all(len(r) == n for r in self.covariance)
                and all(self.covariance[i][i] >= 0 for i in range(n))
                and all(
                    self.covariance[i][j] == self.covariance[j][i]
                    for i in range(n)
                    for j in range(n)
                ),
                "covariance symmetry/shape/diagonal",
            )
        else:
            require(
                self.residual_sum_squares is None and self.condition_proxy is None,
                "unavailable estimator cannot retain numerical claims",
            )


@contract("unc_component")
@dataclass(frozen=True, slots=True)
class UncertaintyComponent(Artifact):
    spec_id: str
    component: UncertaintyType
    measure: UncertaintyMeasure
    value: float | None
    units: str
    status: IdentifiabilityStatus
    method: str
    reason: str
    source_ids: tuple[str, ...]
    sample_ids: tuple[str, ...]
    additive: bool
    available_ns: int

    def _normalize(self) -> None:
        for name in ("source_ids", "sample_ids"):
            unique_ids(getattr(self, name))
            object.__setattr__(self, name, tuple(sorted(getattr(self, name))))

    def _validate(self) -> None:
        validate_fingerprint(self.spec_id, "unc_spec")
        require(
            (self.value is not None) == (self.status in VALUE_STATUSES),
            "component value/identifiability mismatch",
        )
        require(self.value is None or self.value >= 0, "negative uncertainty component")
        require(
            not self.additive
            or self.measure is UncertaintyMeasure.VARIANCE
            and self.status is IdentifiabilityStatus.IDENTIFIED
            and self.method
            in (
                "finite-mixture-within-v1",
                "finite-mixture-between-v1",
                "finite-mixture-unattributed-v1",
            )
            and self.component
            in (
                UncertaintyType.WITHIN_EXPERT_PREDICTIVE,
                UncertaintyType.EXPERT_DISAGREEMENT,
                UncertaintyType.RESIDUAL_UNATTRIBUTED,
            ),
            "only declared finite-mixture identity terms are additive",
        )


@contract("unc_interval")
@dataclass(frozen=True, slots=True)
class UncertaintyInterval(Artifact):
    spec_id: str
    forecast_id: str
    levels: tuple[float, float]
    lower: float | None
    upper: float | None
    width: float | None
    status: IdentifiabilityStatus
    semantics: str
    available_ns: int

    def _validate(self) -> None:
        validate_fingerprint(self.spec_id, "unc_spec")
        validate_fingerprint(self.forecast_id)
        present = self.status is IdentifiabilityStatus.IDENTIFIED
        require(
            all((v is not None) == present for v in (self.lower, self.upper, self.width))
            and 0 < self.levels[0] < self.levels[1] < 1,
            "interval value/status/levels",
        )
        if present:
            assert self.lower is not None and self.upper is not None
            require(
                self.lower <= self.upper and self.width == self.upper - self.lower,
                "interval width arithmetic",
            )


@contract("unc_decomposition")
@dataclass(frozen=True, slots=True)
class ForecastUncertaintyDecomposition(Artifact):
    spec_id: str
    forecast_id: str
    origin: ForecastOrigin
    target_id: str
    horizon_id: str
    sample_id: str
    fold_id: str
    partition: Partition
    components: tuple[UncertaintyComponent, ...]
    interval_id: str
    closure: ClosurePolicy
    identity: str
    total_variance: float | None
    closure_error: float | None
    shares: tuple[tuple[UncertaintyType, float | None], ...]
    quality_states: tuple[str, ...]
    computed_ns: int
    available_ns: int

    def _normalize(self) -> None:
        require(
            len({c.component for c in self.components}) == len(self.components),
            "duplicate decomposition component",
        )
        object.__setattr__(
            self, "components", tuple(sorted(self.components, key=lambda c: c.component.value))
        )
        object.__setattr__(self, "shares", tuple(sorted(self.shares, key=lambda c: c[0].value)))
        object.__setattr__(self, "quality_states", tuple(sorted(set(self.quality_states))))

    def _validate(self) -> None:
        for identity, domain in (
            (self.spec_id, "unc_spec"),
            (self.target_id, "target_definition"),
            (self.sample_id, "r_sample"),
            (self.fold_id, "r_fold"),
            (self.interval_id, "unc_interval"),
        ):
            validate_fingerprint(identity, domain)
        validate_fingerprint(self.forecast_id)
        validate_fingerprint(self.horizon_id)
        require(
            bool(self.components)
            and len(self.components) <= 16
            and all(
                c.spec_id == self.spec_id and c.available_ns <= self.available_ns
                for c in self.components
            ),
            "decomposition component linkage",
        )
        require(
            self.origin.timestamp_ns
            <= self.computed_ns
            <= self.available_ns
            <= self.origin.availability_cutoff_ns,
            "uncertainty not historically available",
        )
        require(
            self.partition in (Partition.VALIDATION, Partition.TEST),
            "uncertainty requires held-out forecast application",
        )
        additive = tuple(c for c in self.components if c.additive)
        if self.closure is ClosurePolicy.EXACT_ADDITIVE:
            require(
                self.identity == "finite-mixture-within-plus-between-v1"
                and self.total_variance is not None
                and self.total_variance >= 0
                and self.closure_error is not None
                and bool(additive),
                "exact decomposition identity/total",
            )
            assert self.total_variance is not None
            error = finite(
                self.total_variance - total([c.value for c in additive if c.value is not None])
            )
            require(self.closure_error == error, "closure error arithmetic")
            require(
                tuple(t for t, _ in self.shares) == tuple(c.component for c in additive)
                and all(
                    s
                    == (
                        c.value / self.total_variance
                        if self.total_variance > 0 and c.value is not None
                        else None
                    )
                    for (_, s), c in zip(self.shares, additive, strict=True)
                ),
                "component share arithmetic/zero total",
            )
        else:
            require(
                self.closure is ClosurePolicy.NON_ADDITIVE_DIAGNOSTICS_ONLY
                and not additive
                and self.closure_error is None
                and not self.shares,
                "non-additive diagnostics cannot claim closure/shares",
            )


@contract("unc_audit")
@dataclass(frozen=True, slots=True)
class UncertaintyAudit(Artifact):
    root_id: str
    node_ids: tuple[str, ...]
    assertions: tuple[str, ...]

    def _normalize(self) -> None:
        unique_ids(self.node_ids)
        object.__setattr__(self, "node_ids", tuple(sorted(self.node_ids)))

    def _validate(self) -> None:
        validate_fingerprint(self.root_id)
        require(
            self.root_id in self.node_ids and bool(self.assertions), "audit root/assertions"
        )

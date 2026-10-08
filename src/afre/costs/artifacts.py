"""Separate immutable hypothetical exposures, costs and later gross/net diagnostics."""

from dataclasses import dataclass

from afre.costs.schema import CostQuality, CostResultState, CostTiming, CostUnit, ids
from afre.forecast import ForecastOrigin
from afre.ids import validate_fingerprint
from afre.schema import Artifact, contract, require


@contract("cost_exposure_change")
@dataclass(frozen=True, slots=True)
class ResearchExposureChange(Artifact):
    scenario_id: str
    sample_id: str
    source_id: str
    origin: ForecastOrigin
    previous_sample_id: str | None
    prior_exposure: float
    exposure: float
    trade_delta: float
    constructed_ns: int
    available_ns: int

    def _validate(self) -> None:
        validate_fingerprint(self.scenario_id, "cost_scenario")
        validate_fingerprint(self.sample_id, "r_sample")
        validate_fingerprint(self.source_id)
        require(
            self.trade_delta == self.exposure - self.prior_exposure
            and self.constructed_ns <= self.available_ns,
            "exposure delta/actual clocks",
        )


@contract("cost_exposure_path")
@dataclass(frozen=True, slots=True)
class ResearchExposurePath(Artifact):
    scenario_id: str
    change_ids: tuple[str, ...]
    constructed_ns: int
    available_ns: int

    def _normalize(self) -> None:
        ids(self, "change_ids")

    def _validate(self) -> None:
        require(
            1 <= len(self.change_ids) <= 2000 and self.constructed_ns <= self.available_ns,
            "bounded actual exposure path",
        )


@contract("cost_component_estimate")
@dataclass(frozen=True, slots=True)
class CostComponentEstimate(Artifact):
    scenario_id: str
    change_id: str
    component_id: str
    input_ids: tuple[str, ...]
    liquidity_input_ids: tuple[str, ...]
    rate: float | None
    rate_unit: CostUnit
    unit_conversion_factor: float | None
    participation: float | None
    traded_quantity: float | None
    amount: float | None
    amount_unit: CostUnit
    quality: CostQuality
    reason: str
    used_fallback: bool
    timing: CostTiming
    constructed_ns: int
    available_ns: int

    def _normalize(self) -> None:
        ids(self, "input_ids", "liquidity_input_ids")

    def _validate(self) -> None:
        require(self.amount_unit is CostUnit.RETURN_FRACTION, "cost total contribution unit")
        require(
            all(
                v is None or v >= 0
                for v in (
                    self.rate,
                    self.unit_conversion_factor,
                    self.participation,
                    self.traded_quantity,
                    self.amount,
                )
            ),
            "nonnegative cost estimate",
        )
        require(
            (self.amount is not None)
            == (self.quality in (CostQuality.VALID, CostQuality.DEGRADED)),
            "component quality/amount",
        )
        require(self.constructed_ns <= self.available_ns, "component actual availability")


@contract("cost_total")
@dataclass(frozen=True, slots=True)
class TotalCostEstimate(Artifact):
    scenario_id: str
    change_id: str
    component_ids: tuple[str, ...]
    exposure: float
    trade_delta: float
    amount: float | None
    unit: CostUnit
    state: CostResultState
    reason: str
    timing: CostTiming
    constructed_ns: int
    available_ns: int

    def _normalize(self) -> None:
        ids(self, "component_ids")

    def _validate(self) -> None:
        require(
            1 <= len(self.component_ids) <= 12 and self.unit is CostUnit.RETURN_FRACTION,
            "compatible bounded total costs",
        )
        require(
            (self.amount is not None) == (self.state is CostResultState.AVAILABLE),
            "total cost state",
        )
        require(self.amount is None or self.amount >= 0, "total cost nonnegative")
        require(self.constructed_ns <= self.available_ns, "total actual clocks")


@contract("cost_sample_evaluation")
@dataclass(frozen=True, slots=True)
class CostAwareSampleEvaluation(Artifact):
    scenario_id: str
    change_id: str
    total_cost_id: str
    sample_id: str
    origin: ForecastOrigin
    target_id: str
    horizon_id: str
    source_id: str
    truth_id: str | None
    gross_contribution: float | None
    total_cost: float | None
    net_contribution: float | None
    state: CostResultState
    reason: str
    uncertainty_ids: tuple[str, ...]
    evaluation_cutoff_ns: int
    available_ns: int

    def _normalize(self) -> None:
        ids(self, "uncertainty_ids")

    def _validate(self) -> None:
        require(
            (self.net_contribution is not None) == (self.state is CostResultState.AVAILABLE),
            "sample cost-aware state",
        )
        if self.net_contribution is not None:
            require(
                self.gross_contribution is not None
                and self.total_cost is not None
                and self.net_contribution == self.gross_contribution - self.total_cost,
                "gross/net separation arithmetic",
            )
        require(self.evaluation_cutoff_ns <= self.available_ns, "later evaluation clocks")


@contract("cost_evaluation")
@dataclass(frozen=True, slots=True)
class CostAwareEvaluation(Artifact):
    scenario_id: str
    path_id: str
    sample_evaluation_ids: tuple[str, ...]
    included_sample_ids: tuple[str, ...]
    exclusions: tuple[tuple[str, str], ...]
    eligible_count: int
    sample_count: int
    gross_sum: float | None
    total_cost_sum: float | None
    net_sum: float | None
    gross_mean: float | None
    mean_cost: float | None
    net_mean: float | None
    all_truth_gross_sum: float | None
    turnover: float
    path_turnover: float
    average_cost_per_turnover_unit: float | None
    gross_positive_fraction: float | None
    net_positive_fraction: float | None
    cost_to_gross_ratio: float | None
    edge_survival_fraction: float | None
    state: CostResultState
    reason: str
    timing: CostTiming
    test_evaluation_id: str | None
    evaluation_cutoff_ns: int
    available_ns: int

    def _normalize(self) -> None:
        ids(self, "sample_evaluation_ids", "included_sample_ids")
        object.__setattr__(self, "exclusions", tuple(sorted(self.exclusions)))

    def _validate(self) -> None:
        require(
            0
            <= self.sample_count
            <= self.eligible_count
            == len(self.sample_evaluation_ids)
            <= 2000,
            "cost evaluation counts",
        )
        require(
            len(self.included_sample_ids) == self.sample_count
            and len(self.exclusions) + self.sample_count == self.eligible_count,
            "cost inclusion/exclusion accounting",
        )
        require(
            0 <= self.turnover <= self.path_turnover, "explicit included/full-path turnover"
        )
        require(self.evaluation_cutoff_ns <= self.available_ns, "evaluation actual clocks")


@contract("cost_breakeven")
@dataclass(frozen=True, slots=True)
class BreakEvenCostDiagnostic(Artifact):
    evaluation_id: str
    component_id: str | None
    budget_return_fraction: float | None
    threshold: float | None
    threshold_unit: CostUnit
    turnover_denominator: float
    state: CostResultState
    reason: str
    available_ns: int

    def _validate(self) -> None:
        require(
            self.turnover_denominator >= 0 and (self.threshold is None or self.threshold >= 0),
            "break-even denominator/nonnegative threshold",
        )


@contract("cost_curve_point")
@dataclass(frozen=True, slots=True)
class CostSensitivityPoint(Artifact):
    rate: float
    participation: float | None
    turnover_multiplier: float
    cost_sum: float | None
    net_sum: float | None
    net_mean: float | None
    state: CostResultState
    reason: str


@contract("cost_sensitivity")
@dataclass(frozen=True, slots=True)
class CostSensitivityCurve(Artifact):
    evaluation_id: str
    spec_id: str
    points: tuple[CostSensitivityPoint, ...]
    available_ns: int

    def _normalize(self) -> None:
        self.ordered("points", "fingerprint")

    def _validate(self) -> None:
        require(1 <= len(self.points) <= 64, "bounded supplied cost curve")


@contract("cost_comparison")
@dataclass(frozen=True, slots=True)
class CostAwareComparison(Artifact):
    left_id: str
    right_id: str
    sample_ids: tuple[str, ...]
    gross_delta: float | None
    net_delta: float | None
    turnover_delta: float | None
    state: CostResultState
    reason: str
    available_ns: int

    def _normalize(self) -> None:
        ids(self, "sample_ids")


@contract("cost_cohort")
@dataclass(frozen=True, slots=True)
class CostCohortEvaluation(Artifact):
    evaluation_id: str
    environment_id: str
    membership_ids: tuple[str, ...]
    weighted_samples: tuple[tuple[str, float], ...]
    eligible_count: int
    included_count: int
    effective_count: float
    gross_mean: float | None
    mean_cost: float | None
    net_mean: float | None
    weighted_turnover: float
    state: CostResultState
    reason: str
    available_ns: int

    def _normalize(self) -> None:
        ids(self, "membership_ids")
        object.__setattr__(self, "weighted_samples", tuple(sorted(self.weighted_samples)))


@contract("cost_audit")
@dataclass(frozen=True, slots=True)
class CostResearchAudit(Artifact):
    root_id: str
    node_ids: tuple[str, ...]
    notes: tuple[str, ...]

    def _normalize(self) -> None:
        ids(self, "node_ids")

    def _validate(self) -> None:
        require(
            self.root_id in self.node_ids and len(self.node_ids) <= 100_000,
            "cost audit root/nodes",
        )

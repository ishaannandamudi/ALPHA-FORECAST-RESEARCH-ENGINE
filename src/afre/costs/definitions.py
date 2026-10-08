"""Predeclared cost assumptions and simple bounded research exposure mappings."""

from dataclasses import dataclass

from afre.costs.schema import (
    COST_IMPLEMENTATION,
    CostBasis,
    CostComponentType,
    CostMissingPolicy,
    CostModel,
    CostTiming,
    CostUnit,
    InitialExposurePolicy,
    ResearchExposureMode,
    SpreadMeaning,
    ids,
)
from afre.ids import validate_fingerprint
from afre.schema import Artifact, contract, require
from afre.target_engine.definitions import TargetDefinition
from afre.targets import TargetType


@contract("cost_exposure_rule")
@dataclass(frozen=True, slots=True)
class ResearchExposureRule(Artifact):
    mode: ResearchExposureMode
    minimum_exposure: float
    maximum_exposure: float
    amplitude: float
    threshold: float
    scalar_exposure: float
    initial_policy: InitialExposurePolicy
    initial_exposure: float
    declared_ns: int
    mapping_version: str = "strict-threshold-sign-fixed-scalar-v1"

    def _validate(self) -> None:
        require(
            -100 <= self.minimum_exposure <= 0 <= self.maximum_exposure <= 100
            and self.minimum_exposure < self.maximum_exposure,
            "explicit bounded exposure range",
        )
        require(
            self.minimum_exposure <= self.initial_exposure <= self.maximum_exposure
            and (
                self.initial_policy is not InitialExposurePolicy.ZERO
                or self.initial_exposure == 0
            ),
            "explicit initial exposure",
        )
        require(
            0 < self.amplitude <= 100 and self.threshold >= 0, "exposure amplitude/threshold"
        )
        require(
            self.mode is ResearchExposureMode.THRESHOLD_SIGN or self.threshold == 0,
            "threshold only for threshold mapping",
        )
        require(
            self.mode is ResearchExposureMode.DECLARED_SCALAR_EXPOSURE
            or self.scalar_exposure == 0,
            "scalar only for scalar mapping",
        )
        if self.mode in (ResearchExposureMode.SIGN, ResearchExposureMode.THRESHOLD_SIGN):
            require(
                self.minimum_exposure <= -self.amplitude
                and self.amplitude <= self.maximum_exposure,
                "sign mapping bounded",
            )
        if self.mode is ResearchExposureMode.DECLARED_SCALAR_EXPOSURE:
            require(
                self.minimum_exposure <= self.scalar_exposure <= self.maximum_exposure,
                "scalar mapping bounded",
            )
        if self.mode is ResearchExposureMode.FIXED_UNIT_NOTIONAL:
            require(self.maximum_exposure >= 1, "fixed unit exposure bounded")
        require(
            self.mapping_version == "strict-threshold-sign-fixed-scalar-v1",
            "closed exposure mapping",
        )


@contract("cost_component_spec")
@dataclass(frozen=True, slots=True)
class CostComponentSpec(Artifact):
    name: str
    component: CostComponentType
    model: CostModel
    version: str
    unit: CostUnit
    basis: CostBasis
    spread_meaning: SpreadMeaning
    covers: tuple[CostComponentType, ...]
    declared_ns: int
    fixed_value: float | None = None
    fallback_value: float | None = None
    provider: str = "AFRE-declared"
    provider_version: str = "1"
    provider_schema: str = "1.0"
    venue: str | None = None
    applicability: str = "each-absolute-exposure-change-v1"

    def _normalize(self) -> None:
        require(len(set(self.covers)) == len(self.covers), "duplicate embedded cost categories")
        object.__setattr__(self, "covers", tuple(sorted(self.covers, key=lambda c: c.value)))

    def _validate(self) -> None:
        require(
            self.component is not CostComponentType.BORROW_COST
            and CostComponentType.BORROW_COST not in self.covers,
            "borrow carrying-cost model unsupported",
        )
        require(
            self.component in self.covers and self.unit is not CostUnit.UNIT_QUANTITY,
            "component coverage/rate unit",
        )
        require(self.fixed_value is None or self.fixed_value >= 0, "fixed cost magnitude")
        require(
            self.fallback_value is None or self.fallback_value >= 0, "fallback cost magnitude"
        )
        require(
            (self.fixed_value is not None)
            == (self.model in (CostModel.FIXED_RATE, CostModel.FIXED_HALF_SPREAD)),
            "explicit fixed rate shape",
        )
        require(
            (self.component is CostComponentType.SPREAD)
            == (self.spread_meaning is not SpreadMeaning.NOT_SPREAD),
            "spread semantics shape",
        )
        if self.model is CostModel.FIXED_HALF_SPREAD:
            require(
                self.component is CostComponentType.SPREAD
                and self.spread_meaning is SpreadMeaning.HALF_SPREAD,
                "fixed half-spread meaning",
            )
        if self.model is CostModel.OBSERVED_BID_ASK_SPREAD:
            require(
                self.component is CostComponentType.SPREAD
                and self.unit is CostUnit.PRICE
                and self.spread_meaning is SpreadMeaning.FULL_SPREAD,
                "observed full bid/ask spread",
            )
        if self.model in (CostModel.LINEAR_PARTICIPATION, CostModel.SQRT_PARTICIPATION):
            require(
                self.component in (CostComponentType.SLIPPAGE, CostComponentType.MARKET_IMPACT)
                and self.unit is CostUnit.BASIS_POINTS
                and self.basis is not CostBasis.PER_TRADE,
                "participation coefficient units/model",
            )
        if self.basis is CostBasis.PER_TRADE:
            require(
                self.unit is CostUnit.CURRENCY_TOTAL,
                "flat per-trade fee requires explicit currency total",
            )
        if self.component is CostComponentType.SPREAD:
            require(
                self.basis is CostBasis.PER_SIDE_PER_TURNOVER,
                "spread side and round-trip conversion cannot double halve",
            )
        require(
            self.applicability == "each-absolute-exposure-change-v1",
            "closed cost applicability",
        )


@contract("cost_binding")
@dataclass(frozen=True, slots=True)
class CostInputBinding(Artifact):
    sample_id: str
    component_id: str
    input_ids: tuple[str, ...]

    def _normalize(self) -> None:
        ids(self, "input_ids")

    def _validate(self) -> None:
        validate_fingerprint(self.sample_id, "r_sample")
        validate_fingerprint(self.component_id, "cost_component_spec")
        require(len(self.input_ids) <= 2, "bounded exact cost inputs")


@contract("cost_liquidity")
@dataclass(frozen=True, slots=True)
class ResearchLiquidityAssumption(Artifact):
    sample_id: str
    price_input_id: str
    notional_input_id: str
    volume_input_id: str | None

    def _validate(self) -> None:
        validate_fingerprint(self.sample_id, "r_sample")
        for identity in (self.price_input_id, self.notional_input_id, self.volume_input_id):
            if identity:
                validate_fingerprint(identity, "cost_input")


@contract("cost_scenario")
@dataclass(frozen=True, slots=True)
class CostScenario(Artifact):
    scenario_id: str
    target: TargetDefinition
    fold_id: str
    source_ids: tuple[str, ...]
    sample_ids: tuple[str, ...]
    exposure_rule: ResearchExposureRule
    components: tuple[CostComponentSpec, ...]
    bindings: tuple[CostInputBinding, ...]
    liquidity: tuple[ResearchLiquidityAssumption, ...]
    timing: CostTiming
    missing_policy: CostMissingPolicy
    currency: str
    signal_unit: str
    maximum_participation: float
    maximum_input_age_ns: int
    declared_ns: int
    minimum_count: int = 1
    allow_degraded: bool = False
    approved_delivery_attestors: tuple[str, ...] = ()
    uncertainty_ids: tuple[str, ...] = ()
    implementation_version: str = COST_IMPLEMENTATION
    turnover_convention: str = "absolute-exposure-change-units-no-terminal-liquidation-v1"
    contribution_convention: str = (
        "arithmetic-exposure-times-simple-target-return-no-compounding-v1"
    )

    def _normalize(self) -> None:
        ids(self, "source_ids", "sample_ids", "uncertainty_ids")
        for n in ("components", "bindings", "liquidity"):
            self.ordered(n, "fingerprint")
        require(
            len(set(self.approved_delivery_attestors)) == len(self.approved_delivery_attestors),
            "duplicate cost attestors",
        )
        object.__setattr__(
            self, "approved_delivery_attestors", tuple(sorted(self.approved_delivery_attestors))
        )

    def _validate(self) -> None:
        validate_fingerprint(self.fold_id, "r_fold")
        require(
            self.target.target_type is TargetType.SIMPLE_RETURN,
            "gross research contribution requires simple return target",
        )
        require(
            1 <= len(self.components) <= 12
            and 1 <= len(self.sample_ids) == len(self.source_ids) <= 2000,
            "scenario component/source/sample bounds",
        )
        require(len(self.uncertainty_ids) <= len(self.sample_ids), "uncertainty metadata bound")
        require(
            len({c.name for c in self.components}) == len(self.components),
            "unique component names",
        )
        covered = tuple(t for c in self.components for t in c.covers)
        require(len(covered) == len(set(covered)), "double-counted embedded cost category")
        require(
            self.exposure_rule.declared_ns <= self.declared_ns
            and all(c.declared_ns <= self.declared_ns for c in self.components),
            "cost settings declaration chronology",
        )
        require(
            0 < self.maximum_participation <= 1 and self.minimum_count >= 1,
            "participation/minimum count",
        )
        require(
            self.missing_policy is CostMissingPolicy.DECLARED_FALLBACK
            or all(c.fallback_value is None for c in self.components),
            "fallback only under declared fallback policy",
        )
        require(
            {(b.sample_id, b.component_id) for b in self.bindings}
            == {(s, c.fingerprint) for s in self.sample_ids for c in self.components}
            and len(self.bindings) == len(self.sample_ids) * len(self.components),
            "complete exact input binding grid",
        )
        require(
            {a.sample_id for a in self.liquidity} == set(self.sample_ids)
            and len(self.liquidity) == len(self.sample_ids),
            "one explicit liquidity reference per sample",
        )
        require(
            self.implementation_version == COST_IMPLEMENTATION
            and self.turnover_convention
            == "absolute-exposure-change-units-no-terminal-liquidation-v1"
            and self.contribution_convention
            == "arithmetic-exposure-times-simple-target-return-no-compounding-v1",
            "closed research cost conventions",
        )


@contract("cost_sensitivity_spec")
@dataclass(frozen=True, slots=True)
class CostSensitivitySpec(Artifact):
    scenario_id: str
    component_id: str
    rates: tuple[float, ...]
    participation_rates: tuple[float, ...]
    turnover_multipliers: tuple[float, ...]
    declared_ns: int
    convention: str = "gross-held-fixed-cost-intensity-sensitivity-no-optimization-v1"

    def _normalize(self) -> None:
        for n in ("rates", "participation_rates", "turnover_multipliers"):
            v = getattr(self, n)
            require(len(v) == len(set(v)), "duplicate sensitivity level")
            object.__setattr__(self, n, tuple(sorted(v)))

    def _validate(self) -> None:
        validate_fingerprint(self.scenario_id, "cost_scenario")
        validate_fingerprint(self.component_id, "cost_component_spec")
        require(
            bool(self.rates) and all(r >= 0 for r in self.rates),
            "explicit nonnegative rate grid",
        )
        require(
            len(self.participation_rates) <= 32
            and all(0 <= p <= 1 for p in self.participation_rates),
            "participation grid bound",
        )
        require(
            bool(self.turnover_multipliers)
            and all(0 < m <= 10 for m in self.turnover_multipliers),
            "bounded intensity grid",
        )
        require(
            len(self.rates)
            * max(1, len(self.participation_rates))
            * len(self.turnover_multipliers)
            <= 64,
            "sensitivity grid explosion",
        )
        require(
            self.convention == "gross-held-fixed-cost-intensity-sensitivity-no-optimization-v1",
            "closed sensitivity convention",
        )

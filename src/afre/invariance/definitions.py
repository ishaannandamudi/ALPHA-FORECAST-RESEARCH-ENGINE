"""Predeclared partitions and analysis settings, independent of held-out outcomes."""

from dataclasses import dataclass

from afre.cross_sectional.definitions import GroupPolicy
from afre.cross_sectional.schema import GroupType
from afre.event_conditioned.definitions import EventValueRule, EventWindowSpec
from afre.event_conditioned.schema import EventClass
from afre.ids import validate_fingerprint
from afre.invariance.schema import (
    INVARIANCE_IMPLEMENTATION,
    EnvironmentKind,
    EnvironmentRule,
    SampleIntersectionPolicy,
    StabilityMetricName,
    StabilitySampleMode,
    StabilityWeighting,
    canonical_ids,
)
from afre.regime_conditioned.schema import RegimeMembershipKind
from afre.schema import Artifact, contract, require
from afre.target_engine.definitions import TargetDefinition
from afre.uncertainty.schema import UncertaintyType


@contract("inv_window")
@dataclass(frozen=True, slots=True)
class StabilityTimeWindow(Artifact):
    start_ns: int
    end_ns: int
    include_start: bool = True
    include_end: bool = False
    minimum_count: int = 2
    calendar: str = "elapsed-UTC-no-session-inference-v1"

    def _validate(self) -> None:
        require(self.start_ns < self.end_ns and self.minimum_count >= 1, "window bounds/count")
        require(self.calendar == "elapsed-UTC-no-session-inference-v1", "window calendar")

    def contains(self, at_ns: int) -> bool:
        return (at_ns > self.start_ns or self.include_start and at_ns == self.start_ns) and (
            at_ns < self.end_ns or self.include_end and at_ns == self.end_ns
        )


@contract("inv_environment")
@dataclass(frozen=True, slots=True)
class EnvironmentDefinition(Artifact):
    environment_id: str
    kind: EnvironmentKind
    label: str
    version: str
    provider: str
    rule: EnvironmentRule
    target: TargetDefinition
    declared_ns: int
    minimum_count: int = 2
    window: StabilityTimeWindow | None = None
    taxonomy_id: str | None = None
    state_label: str | None = None
    membership_kind: RegimeMembershipKind | None = None
    maximum_age_ns: int = 0
    event_window: EventWindowSpec | None = None
    event_classes: tuple[EventClass, ...] = ()
    event_value_rules: tuple[EventValueRule, ...] = ()
    group_policy: GroupPolicy | None = None
    group_id: str | None = None
    universe_definition_id: str | None = None
    quality_label: str | None = None
    neutral_label: str | None = None
    component_ids: tuple[str, ...] = ()
    approved_delivery_attestors: tuple[str, ...] = ()
    validity_policy: str = "origin-time-explicit-rule-v1"
    availability_policy: str = "qualified-source-evidence-at-origin-actual-construction-v1"

    def _normalize(self) -> None:
        canonical_ids(self, "component_ids")
        for name in ("event_classes", "approved_delivery_attestors"):
            values = getattr(self, name)
            require(len(set(values)) == len(values), "duplicate environment criterion")
            object.__setattr__(
                self, name, tuple(sorted(values, key=lambda v: getattr(v, "value", v)))
            )
        self.ordered("event_value_rules", "key")

    def _validate(self) -> None:
        rules = {
            EnvironmentRule.TIME: (EnvironmentKind.TIME_WINDOW,),
            EnvironmentRule.REGIME_STATE: (EnvironmentKind.REGIME,),
            EnvironmentRule.EVENT_COHORT: (EnvironmentKind.EVENT,),
            EnvironmentRule.GROUP: (EnvironmentKind.SECTOR, EnvironmentKind.INDUSTRY),
            EnvironmentRule.UNIVERSE: (EnvironmentKind.UNIVERSE,),
            EnvironmentRule.QUALITY: (EnvironmentKind.DATA_QUALITY,),
            EnvironmentRule.LABEL: (EnvironmentKind.CUSTOM, EnvironmentKind.MARKET_STATE),
            EnvironmentRule.COMPOUND: (EnvironmentKind.CUSTOM,),
        }
        require(
            self.kind in rules[self.rule] and self.minimum_count >= 1, "environment kind/count"
        )
        shape = (
            self.window is not None,
            self.taxonomy_id is not None
            and self.state_label is not None
            and self.membership_kind is not None,
            self.event_window is not None and bool(self.event_classes),
            self.group_policy is not None and self.group_id is not None,
            self.universe_definition_id is not None,
            self.quality_label is not None,
            self.neutral_label is not None,
            bool(self.component_ids),
        )
        order = tuple(rules)
        require(
            shape == tuple(self.rule is r for r in order), "environment matching-rule shape"
        )
        require(
            (self.taxonomy_id is None)
            == (self.state_label is None)
            == (self.membership_kind is None),
            "regime selector shape",
        )
        require((self.group_policy is None) == (self.group_id is None), "group selector shape")
        if self.group_policy:
            expected = (
                GroupType.SECTOR if self.kind is EnvironmentKind.SECTOR else GroupType.INDUSTRY
            )
            require(
                self.group_policy.group_type is expected
                and self.provider == self.group_policy.provider,
                "group taxonomy/provider",
            )
        if self.event_window:
            require(self.event_window.target == self.target, "event target/horizon")
        require(
            not self.event_value_rules or self.rule is EnvironmentRule.EVENT_COHORT,
            "event-only attributes",
        )
        require(
            not self.component_ids or len(self.component_ids) == 2, "explicit two-way compound"
        )
        for identity in (self.taxonomy_id, self.universe_definition_id):
            if identity:
                validate_fingerprint(identity)
        require(
            self.validity_policy == "origin-time-explicit-rule-v1"
            and self.availability_policy
            == "qualified-source-evidence-at-origin-actual-construction-v1",
            "environment temporal policy",
        )


@contract("inv_environment_set")
@dataclass(frozen=True, slots=True)
class EnvironmentSet(Artifact):
    definitions: tuple[EnvironmentDefinition, ...]
    declared_ns: int

    def _normalize(self) -> None:
        self.ordered("definitions", "fingerprint")

    def _validate(self) -> None:
        require(
            1 <= len(self.definitions) <= 32
            and len({d.environment_id for d in self.definitions}) == len(self.definitions),
            "environment set bound/unique names",
        )
        require(
            len({d.target.fingerprint for d in self.definitions}) == 1
            and all(d.declared_ns <= self.declared_ns for d in self.definitions),
            "environment set target/declaration",
        )
        ids = {d.fingerprint for d in self.definitions}
        require(
            all(
                set(d.component_ids) <= ids and d.fingerprint not in d.component_ids
                for d in self.definitions
            ),
            "compound exact declared components",
        )
        bases = {d.fingerprint: d for d in self.definitions}
        for d in self.definitions:
            if d.component_ids:
                kinds = {bases[i].kind for i in d.component_ids}
                require(
                    kinds
                    in (
                        {EnvironmentKind.EVENT, EnvironmentKind.REGIME},
                        {EnvironmentKind.SECTOR, EnvironmentKind.REGIME},
                    )
                    and all(not bases[i].component_ids for i in d.component_ids),
                    "supported bounded compound kinds",
                )


@contract("inv_spec")
@dataclass(frozen=True, slots=True)
class StabilityAnalysisSpec(Artifact):
    target: TargetDefinition
    fold_id: str
    environment_set_id: str
    sample_ids: tuple[str, ...]
    forecast_ids: tuple[str, ...]
    metrics: tuple[StabilityMetricName, ...]
    declared_ns: int
    baseline_environment_id: str | None = None
    feature_reference_ids: tuple[str, ...] = ()
    uncertainty_ids: tuple[str, ...] = ()
    share_component: UncertaintyType = UncertaintyType.EXPERT_DISAGREEMENT
    intersection: SampleIntersectionPolicy = SampleIntersectionPolicy.PER_ENVIRONMENT_NATIVE
    weighting: StabilityWeighting = StabilityWeighting.HARD_ONLY
    sample_mode: StabilitySampleMode = StabilitySampleMode.TEMPORAL_PANEL
    minimum_count: int = 2
    interval_levels: tuple[float, float] = (0.1, 0.9)
    pinball_level: float = 0.5
    threshold: float = 0.0
    top_k: int = 2
    reliability_edges: tuple[float, ...] = (0.0, 0.25, 0.5, 0.75, 1.0)
    quantile_levels: tuple[float, ...] = (0.1, 0.5, 0.9)
    tolerance: float = 1e-12
    seed: int = 0
    drift_policy: str = "separate-input-shift-and-error-delta-v1"
    implementation_version: str = INVARIANCE_IMPLEMENTATION

    def _normalize(self) -> None:
        canonical_ids(
            self, "sample_ids", "forecast_ids", "feature_reference_ids", "uncertainty_ids"
        )
        require(len(self.metrics) == len(set(self.metrics)), "duplicate stability metric")
        object.__setattr__(self, "metrics", tuple(sorted(self.metrics, key=lambda m: m.value)))

    def _validate(self) -> None:
        validate_fingerprint(self.fold_id, "r_fold")
        validate_fingerprint(self.environment_set_id, "inv_environment_set")
        if self.baseline_environment_id:
            validate_fingerprint(self.baseline_environment_id, "inv_environment")
        require(
            0 < len(self.sample_ids) <= 2000
            and 0 < len(self.forecast_ids) <= 2000
            and 0 < len(self.metrics) <= 24
            and len(self.feature_reference_ids) <= 16
            and len(self.uncertainty_ids) <= 2000
            and self.minimum_count >= 1,
            "analysis input bounds/count",
        )
        require(
            0 < self.interval_levels[0] < self.interval_levels[1] < 1
            and 0 < self.pinball_level < 1,
            "score levels",
        )
        require(
            len(self.reliability_edges) <= 17
            and self.reliability_edges[0] == 0
            and self.reliability_edges[-1] == 1
            and tuple(sorted(set(self.reliability_edges))) == self.reliability_edges,
            "declared reliability bins",
        )
        require(
            0 < len(self.quantile_levels) <= 16
            and tuple(sorted(set(self.quantile_levels))) == self.quantile_levels
            and all(0 <= q <= 1 for q in self.quantile_levels),
            "Type7 quantile levels",
        )
        require(
            1 <= self.top_k <= 2000
            and 0 < self.tolerance < 1
            and 0 <= self.seed < 2**32
            and self.drift_policy == "separate-input-shift-and-error-delta-v1"
            and self.implementation_version == INVARIANCE_IMPLEMENTATION,
            "analysis numerical/version policy",
        )

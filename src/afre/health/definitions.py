"""Identity-bearing artifact references, diagnostic requests and explicit health rules."""

from dataclasses import dataclass

from afre.health.schema import (
    IMPLEMENTATION,
    PRECEDENCE,
    HealthBounds,
    HealthDiagnostic,
    HealthDirection,
    HealthIntersection,
    HealthPairKey,
    HealthStatistic,
    HealthStatus,
    ids,
)
from afre.health.windows import MonitoringWindow, overlap
from afre.ids import validate_fingerprint
from afre.schema import Artifact, contract, require


@contract("hlt_reference")
@dataclass(frozen=True, slots=True)
class MonitoredArtifactReference(Artifact):
    artifact_id: str
    artifact_type: str
    producer_id: str
    target_id: str
    horizon_id: str
    unit: str
    output_semantics: str
    available_ns: int
    fold_id: str | None = None
    dataset_id: str | None = None
    version: str = "1.0"
    source_version: str = "1.0"
    anchor_output_id: str | None = None

    def _validate(self) -> None:
        for identity in (
            self.artifact_id,
            self.producer_id,
            self.target_id,
            self.horizon_id,
            self.fold_id,
            self.dataset_id,
            self.anchor_output_id,
        ):
            if identity is not None:
                validate_fingerprint(identity)
        require(self.version == "1.0", "native public health reference version")


@contract("hlt_request")
@dataclass(frozen=True, slots=True)
class HealthDiagnosticRequest(Artifact):
    kind: HealthDiagnostic
    column: str
    minimum_count: int
    quantile_level: float = 0.5
    threshold: float = 0.0
    interval_levels: tuple[float, float] = (0.05, 0.95)
    reliability_edges: tuple[float, ...] = (0.0, 0.5, 1.0)
    top_k: int = 1
    tolerance: float = 1e-12

    def _validate(self) -> None:
        require(1 <= self.minimum_count <= 2000 and 1 <= self.top_k <= 2000, "health support")
        require(0 <= self.quantile_level <= 1 and self.tolerance > 0, "health numerical policy")
        require(0 < self.interval_levels[0] < self.interval_levels[1] < 1, "health intervals")
        require(
            2 <= len(self.reliability_edges) <= 65
            and self.reliability_edges[0] == 0
            and self.reliability_edges[-1] == 1
            and all(
                a < b
                for a, b in zip(
                    self.reliability_edges, self.reliability_edges[1:], strict=False
                )
            ),
            "health reliability bins",
        )


@contract("hlt_rule")
@dataclass(frozen=True, slots=True)
class HealthRule(Artifact):
    label: str
    kind: HealthDiagnostic
    direction: HealthDirection
    statistic: HealthStatistic
    minimum_count: int
    warning: float
    degraded: float
    declared_ns: int
    warning_upper: float | None = None
    degraded_upper: float | None = None
    implementation_version: str = "inclusive-severity-boundaries-v1"

    def _validate(self) -> None:
        require(1 <= self.minimum_count <= 2000, "health rule support")
        require(
            self.implementation_version == "inclusive-severity-boundaries-v1",
            "health rule version",
        )
        if self.direction is HealthDirection.TWO_SIDED_RANGE:
            require(
                self.warning_upper is not None and self.degraded_upper is not None,
                "two-sided rule requires both explicit upper boundaries",
            )
            assert self.warning_upper is not None and self.degraded_upper is not None
            require(
                self.degraded <= self.warning <= self.warning_upper <= self.degraded_upper,
                "nested health ranges",
            )
        else:
            require(
                self.warning_upper is None and self.degraded_upper is None,
                "one-sided rule shape",
            )
            require(
                self.degraded <= self.warning
                if self.direction is HealthDirection.LOWER_WORSE
                else self.degraded >= self.warning,
                "ordered health severity boundaries",
            )
            if self.direction is HealthDirection.ABSOLUTE_CHANGE_WORSE:
                require(self.warning >= 0, "absolute health boundaries nonnegative")


@contract("hlt_spec")
@dataclass(frozen=True, slots=True)
class HealthSpec(Artifact):
    label: str
    reference_id: str
    target_id: str
    horizon_id: str
    reference_window: MonitoringWindow
    current_window: MonitoringWindow
    requests: tuple[HealthDiagnosticRequest, ...]
    rule_bindings: tuple[tuple[str, str], ...]
    reference_observation_ids: tuple[str, ...]
    current_observation_ids: tuple[str, ...]
    minimum_count: int
    declared_ns: int
    comparison_reference_ids: tuple[str, ...] = ()
    intersection: HealthIntersection = HealthIntersection.NATIVE_PER_WINDOW
    pair_key: HealthPairKey = HealthPairKey.SAMPLE
    allow_overlap: bool = False
    predeclared: bool = True
    environment_id: str | None = None
    membership_ids: tuple[str, ...] = ()
    context_ids: tuple[str, ...] = ()
    context_records: tuple[tuple[str, str, int, str], ...] = ()
    test_evaluation_id: str | None = None
    precedence: tuple[HealthStatus, ...] = PRECEDENCE
    aggregation: str = "WORST_STATUS"
    bounds: HealthBounds = HealthBounds()
    seed: int = 0
    implementation_version: str = IMPLEMENTATION

    def _normalize(self) -> None:
        self.ordered("requests", "fingerprint")
        ids(
            self,
            "reference_observation_ids",
            "current_observation_ids",
            "comparison_reference_ids",
            "membership_ids",
            "context_ids",
        )
        object.__setattr__(self, "rule_bindings", tuple(sorted(self.rule_bindings)))
        object.__setattr__(self, "context_records", tuple(sorted(self.context_records)))

    def _validate(self) -> None:
        for identity in (
            self.reference_id,
            self.target_id,
            self.horizon_id,
            self.environment_id,
            self.test_evaluation_id,
        ):
            if identity is not None:
                validate_fingerprint(identity)
        require(
            1 <= len(self.requests) <= self.bounds.metrics and self.minimum_count >= 1,
            "health spec metric/support bound",
        )
        require(
            max(len(self.reference_observation_ids), len(self.current_observation_ids))
            <= self.bounds.samples
            and len(self.comparison_reference_ids) < self.bounds.sources
            and len(self.membership_ids) <= 2 * self.bounds.samples
            and len(self.context_ids) <= self.bounds.sources,
            "health spec row/source bound",
        )
        require(
            self.bounds.windows >= 2 and self.reference_id not in self.comparison_reference_ids,
            "health window/source bounds and unique primary reference",
        )
        require(
            self.reference_window.start_ns <= self.current_window.start_ns
            and (self.allow_overlap or not overlap(self.reference_window, self.current_window)),
            "health windows order/explicit overlap",
        )
        require(
            not self.predeclared or self.declared_ns <= self.current_window.start_ns,
            "health rules/spec predeclared before current-window outcomes",
        )
        require(
            self.test_evaluation_id is None or self.predeclared,
            "TEST health requires predeclared rules",
        )
        require(
            len({i for i, _ in self.rule_bindings}) == len(self.rule_bindings)
            and {i for i, _ in self.rule_bindings} <= {r.fingerprint for r in self.requests},
            "health exact request/rule bindings",
        )
        for _, identity in self.rule_bindings:
            validate_fingerprint(identity, HealthRule.domain)
        require(
            (self.environment_id is None) == (not self.membership_ids), "health cohort shape"
        )
        require(
            tuple(r[0] for r in self.context_records) == self.context_ids,
            "health exact native context certificates",
        )
        require(
            self.precedence == PRECEDENCE and self.aggregation == "WORST_STATUS",
            "explicit supported health aggregation",
        )
        require(
            self.implementation_version == IMPLEMENTATION and 0 <= self.seed < 2**63,
            "health implementation/seed",
        )

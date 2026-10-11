"""Immutable evidence and advisory results, with one common sample/truth support."""

from dataclasses import dataclass

from afre.challenger.schema import (
    ChallengeMetric,
    ChallengeStatus,
    PromotionOutcome,
    RollbackOutcome,
    ShadowMode,
    ids,
)
from afre.ids import validate_fingerprint
from afre.research_datasets.schema import Partition
from afre.schema import Artifact, contract, require


@contract("ch_shadow")
@dataclass(frozen=True, slots=True)
class ShadowForecast(Artifact):
    program_id: str
    participant_id: str
    source_id: str
    sample_id: str
    security_id: str
    origin_ns: int
    target_id: str
    horizon_id: str
    unit: str
    value: float | None
    law_id: str | None
    partition: Partition
    source_available_ns: int
    computed_ns: int
    available_ns: int
    mode: ShadowMode
    quality: tuple[str, ...]

    def _normalize(self) -> None:
        object.__setattr__(self, "quality", tuple(sorted(set(self.quality))))

    def _validate(self) -> None:
        ids(self)
        for identity in (
            self.program_id,
            self.participant_id,
            self.source_id,
            self.sample_id,
            self.security_id,
            self.target_id,
            self.horizon_id,
            self.law_id,
        ):
            if identity is not None:
                validate_fingerprint(identity)
        require(
            self.available_ns >= max(self.source_available_ns, self.computed_ns),
            "shadow honest construction availability",
        )
        require(self.source_available_ns <= self.origin_ns, "shadow causal native source")
        require(
            self.mode is not ShadowMode.RECORDED_CAUSAL or self.available_ns <= self.origin_ns,
            "shadow received/computed after origin",
        )


@contract("ch_evidence")
@dataclass(frozen=True, slots=True)
class EvaluationEvidence(Artifact):
    program_id: str
    shadow_ids: tuple[str, ...]
    truth_assignments: tuple[tuple[str, str], ...]
    available_ns: int
    test_evaluation_id: str | None = None
    health_bindings: tuple[tuple[str, str], ...] = ()
    cost_bindings: tuple[tuple[str, str], ...] = ()
    breakeven_bindings: tuple[tuple[str, str], ...] = ()
    context_records: tuple[tuple[str, str, int, str], ...] = ()

    def _normalize(self) -> None:
        ids(self, "shadow_ids")
        for name in (
            "truth_assignments",
            "health_bindings",
            "cost_bindings",
            "breakeven_bindings",
            "context_records",
        ):
            object.__setattr__(self, name, tuple(sorted(getattr(self, name))))

    def _validate(self) -> None:
        validate_fingerprint(self.program_id, "ch_program")
        if self.test_evaluation_id is not None:
            validate_fingerprint(self.test_evaluation_id, "r_test_evaluation")
        require(
            len(self.shadow_ids) <= 34000 and len(self.truth_assignments) <= 2000,
            "evaluation evidence bounds",
        )
        for name in (
            "truth_assignments",
            "health_bindings",
            "cost_bindings",
            "breakeven_bindings",
        ):
            values = getattr(self, name)
            require(len({r[0] for r in values}) == len(values), "ambiguous evidence binding")
            for a, b in values:
                validate_fingerprint(a)
                validate_fingerprint(b)
        require(
            len(self.context_records) <= 32
            and len({r[0] for r in self.context_records}) == len(self.context_records),
            "evaluation context bound/duplicates",
        )


@contract("ch_common")
@dataclass(frozen=True, slots=True)
class CommonMatchedEvidence(Artifact):
    program_id: str
    evidence_id: str
    assignments: tuple[tuple[str, str], ...]
    shadow_ids: tuple[str, ...]
    exclusions: tuple[tuple[str, str], ...]
    status: ChallengeStatus
    reason: str
    cutoff_ns: int
    available_ns: int

    def _normalize(self) -> None:
        ids(self, "shadow_ids")
        object.__setattr__(self, "assignments", tuple(sorted(self.assignments)))
        object.__setattr__(self, "exclusions", tuple(sorted(self.exclusions)))

    def _validate(self) -> None:
        validate_fingerprint(self.program_id, "ch_program")
        validate_fingerprint(self.evidence_id, "ch_evidence")
        require(
            len(self.assignments) <= 2000 and len(self.exclusions) <= 36000,
            "common matching bound",
        )
        require(self.cutoff_ns <= self.available_ns, "matching later evaluation clock")


@contract("ch_metric")
@dataclass(frozen=True, slots=True)
class ParticipantMetricResult(Artifact):
    program_id: str
    participant_id: str
    request_id: str
    common_id: str
    kind: ChallengeMetric
    target_id: str
    horizon_id: str
    unit: str
    count: int
    value: float | None
    status: ChallengeStatus
    reason: str
    sample_ids: tuple[str, ...]
    truth_ids: tuple[str, ...]
    cutoff_ns: int
    available_ns: int
    orientation: str
    details: tuple[tuple[str, float], ...] = ()

    def _normalize(self) -> None:
        ids(self, "sample_ids", "truth_ids")
        object.__setattr__(self, "details", tuple(sorted(self.details)))

    def _validate(self) -> None:
        require(
            0 <= self.count <= 2000 and self.count == len(self.sample_ids),
            "metric exact common support count",
        )
        require(
            self.cutoff_ns <= self.available_ns and len(self.details) <= 2000,
            "metric clock/detail bound",
        )
        require(
            (self.status is ChallengeStatus.AVAILABLE) == (self.value is not None),
            "metric unavailable values explicit",
        )


@contract("ch_comparison")
@dataclass(frozen=True, slots=True)
class ChallengerComparison(Artifact):
    program_id: str
    champion_id: str
    challenger_id: str
    request_id: str
    champion_metric_id: str
    challenger_metric_id: str
    common_id: str
    delta: float | None
    oriented_improvement: float | None
    status: ChallengeStatus
    orientation: str
    available_ns: int


@contract("ch_promotion")
@dataclass(frozen=True, slots=True)
class PromotionAssessment(Artifact):
    program_id: str
    challenger_id: str
    evidence_id: str
    comparison_ids: tuple[str, ...]
    criterion_results: tuple[tuple[str, bool | None, str], ...]
    outcome: PromotionOutcome
    available_ns: int
    action: str = "MANUAL_ONLY"

    def _normalize(self) -> None:
        ids(self, "comparison_ids")
        object.__setattr__(self, "criterion_results", tuple(sorted(self.criterion_results)))

    def _validate(self) -> None:
        require(
            self.action == "MANUAL_ONLY" and 1 <= len(self.criterion_results) <= 32,
            "promotion advisory boundary/criteria",
        )


@contract("ch_rollback")
@dataclass(frozen=True, slots=True)
class RollbackAssessment(Artifact):
    program_id: str
    champion_id: str
    evidence_id: str
    criterion_id: str
    current_metric_id: str
    baseline_metric_id: str
    deterioration: float | None
    outcome: RollbackOutcome
    available_ns: int
    reason: str
    action: str = "MANUAL_ONLY"

    def _validate(self) -> None:
        require(self.action == "MANUAL_ONLY", "rollback advisory boundary")


@contract("ch_run")
@dataclass(frozen=True, slots=True)
class ChallengeRun(Artifact):
    program_id: str
    champion_id: str
    challenger_ids: tuple[str, ...]
    evidence_id: str
    common_id: str
    metric_ids: tuple[str, ...]
    comparison_ids: tuple[str, ...]
    promotion_ids: tuple[str, ...]
    rollback_ids: tuple[str, ...]
    cutoff_ns: int
    available_ns: int
    action: str = "MANUAL_ONLY"

    def _normalize(self) -> None:
        ids(
            self,
            "challenger_ids",
            "metric_ids",
            "comparison_ids",
            "promotion_ids",
            "rollback_ids",
        )

    def _validate(self) -> None:
        require(
            self.action == "MANUAL_ONLY" and self.cutoff_ns <= self.available_ns,
            "run manual boundary and clock",
        )
        require(
            len(self.metric_ids) <= 544 and len(self.comparison_ids) <= 512, "run result bounds"
        )

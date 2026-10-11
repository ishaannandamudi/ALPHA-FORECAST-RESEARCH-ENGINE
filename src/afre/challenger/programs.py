"""Frozen explicit common-evidence programs; no discovery, search or serving state."""

from dataclasses import dataclass

from afre.challenger.schema import (
    IMPLEMENTATION,
    ChallengeBounds,
    ChallengeMatching,
    ChallengeMetric,
    ChallengeTestPolicy,
    CriteriaPolicy,
    ShadowMode,
    ids,
)
from afre.challenger.windows import ChallengeWindow
from afre.ids import validate_fingerprint
from afre.schema import Artifact, contract, require


@contract("ch_request")
@dataclass(frozen=True, slots=True)
class ChallengeMetricRequest(Artifact):
    kind: ChallengeMetric
    minimum_count: int
    threshold: float = 0.0
    quantile_level: float = 0.5
    interval_levels: tuple[float, float] = (0.05, 0.95)
    top_k: int = 1
    cross_section_minimum: int = 2

    def _validate(self) -> None:
        require(
            1 <= self.minimum_count <= 2000 and 1 <= self.top_k <= 2000,
            "challenge metric support",
        )
        require(
            0 < self.quantile_level < 1
            and 0 < self.interval_levels[0] < self.interval_levels[1] < 1,
            "challenge explicit probabilistic levels",
        )
        require(2 <= self.cross_section_minimum <= 2000, "challenge cross-section support")


@contract("ch_program")
@dataclass(frozen=True, slots=True)
class ChallengeProgram(Artifact):
    name: str
    champion_id: str
    challenger_ids: tuple[str, ...]
    target_id: str
    horizon_id: str
    unit: str
    dataset_id: str
    fold_id: str
    window: ChallengeWindow
    minimum_count: int
    requests: tuple[ChallengeMetricRequest, ...]
    promotion_criterion_ids: tuple[str, ...]
    rollback_criterion_ids: tuple[str, ...]
    test_policy: ChallengeTestPolicy
    declared_ns: int
    matching: ChallengeMatching = ChallengeMatching.COMMON_INTERSECTION
    criteria_policy: CriteriaPolicy = CriteriaPolicy.ALL_REQUIRED
    shadow_mode: ShadowMode = ShadowMode.RECORDED_CAUSAL
    predeclared: bool = True
    health_participant_ids: tuple[str, ...] = ()
    cost_plan_id: str | None = None
    environment_id: str | None = None
    membership_ids: tuple[str, ...] = ()
    context_records: tuple[tuple[str, str, int, str], ...] = ()
    uncertainty_ids: tuple[str, ...] = ()
    bounds: ChallengeBounds = ChallengeBounds()
    seed: int = 0
    implementation_version: str = IMPLEMENTATION

    def _normalize(self) -> None:
        ids(
            self,
            "challenger_ids",
            "promotion_criterion_ids",
            "rollback_criterion_ids",
            "health_participant_ids",
            "membership_ids",
            "uncertainty_ids",
        )
        self.ordered("requests", "fingerprint")
        object.__setattr__(self, "context_records", tuple(sorted(self.context_records)))

    def _validate(self) -> None:
        for identity in (
            self.champion_id,
            self.target_id,
            self.horizon_id,
            self.dataset_id,
            self.fold_id,
            self.cost_plan_id,
            self.environment_id,
        ):
            if identity is not None:
                validate_fingerprint(identity)
        require(
            1 <= len(self.challenger_ids) <= self.bounds.challengers
            and self.champion_id not in self.challenger_ids,
            "explicit champion/challengers",
        )
        require(
            1 <= self.minimum_count <= self.bounds.samples
            and 1 <= len(self.requests) <= self.bounds.metrics
            and len(self.requests) * len(self.challenger_ids) <= self.bounds.comparisons,
            "challenge support/metric/comparison bounds",
        )
        require(
            1 <= len(self.promotion_criterion_ids) <= self.bounds.criteria
            and len(self.rollback_criterion_ids) <= self.bounds.criteria,
            "challenge explicit criteria bounds",
        )
        require(
            not self.predeclared or self.declared_ns <= self.window.start_ns,
            "challenge declaration before evaluation outcomes",
        )
        require(
            self.test_policy is not ChallengeTestPolicy.SEALED_TEST or self.predeclared,
            "TEST requires predeclared challenge",
        )
        require(
            set(self.health_participant_ids) <= {self.champion_id, *self.challenger_ids},
            "health context only exact declared participants",
        )
        require(
            (self.environment_id is None) == (not self.membership_ids),
            "challenge explicit cohort shape",
        )
        require(
            len(self.membership_ids) <= self.bounds.samples
            and len(self.context_records) <= 32
            and len(self.uncertainty_ids) <= self.bounds.samples,
            "challenge context bounds",
        )
        require(
            len({r[0] for r in self.context_records}) == len(self.context_records),
            "duplicate challenge native context",
        )
        require(
            self.implementation_version == IMPLEMENTATION and 0 <= self.seed < 2**63,
            "challenge implementation/seed",
        )

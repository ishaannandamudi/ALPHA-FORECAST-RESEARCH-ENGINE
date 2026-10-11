"""Identity-bearing advisory thresholds; no hidden severity or deployment predicates."""

from dataclasses import dataclass

from afre.challenger.schema import ChallengeDirection, ids
from afre.health.schema import HealthStatus
from afre.ids import validate_fingerprint
from afre.schema import Artifact, contract, require


@contract("ch_promotion_criterion")
@dataclass(frozen=True, slots=True)
class PromotionCriterion(Artifact):
    name: str
    request_id: str
    direction: ChallengeDirection
    required_improvement: float
    minimum_count: int
    declared_ns: int
    champion_health: tuple[HealthStatus, ...] = ()
    challenger_health: tuple[HealthStatus, ...] = ()
    requires_cost: bool = False
    required_context_ids: tuple[str, ...] = ()

    def _normalize(self) -> None:
        ids(self, "required_context_ids")
        for name in ("champion_health", "challenger_health"):
            values = getattr(self, name)
            require(len(values) == len(set(values)), "duplicate allowed health status")
            object.__setattr__(self, name, tuple(sorted(values, key=lambda v: v.value)))

    def _validate(self) -> None:
        validate_fingerprint(self.request_id, "ch_request")
        require(
            self.required_improvement >= 0 and 1 <= self.minimum_count <= 2000,
            "explicit promotion improvement/support",
        )


@contract("ch_rollback_criterion")
@dataclass(frozen=True, slots=True)
class RollbackCriterion(Artifact):
    name: str
    request_id: str
    baseline_metric_id: str
    direction: ChallengeDirection
    deterioration_threshold: float
    minimum_count: int
    declared_ns: int
    required_health: tuple[HealthStatus, ...] = ()

    def _normalize(self) -> None:
        require(
            len(self.required_health) == len(set(self.required_health)),
            "duplicate rollback health states",
        )
        object.__setattr__(
            self, "required_health", tuple(sorted(self.required_health, key=lambda v: v.value))
        )

    def _validate(self) -> None:
        validate_fingerprint(self.request_id, "ch_request")
        validate_fingerprint(self.baseline_metric_id, "ch_metric")
        require(
            self.deterioration_threshold >= 0 and 1 <= self.minimum_count <= 2000,
            "explicit rollback deterioration/support",
        )

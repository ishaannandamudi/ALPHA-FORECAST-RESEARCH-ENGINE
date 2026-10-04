"""Versioned split/factor streams; total return is deliberately unsupported."""

from dataclasses import dataclass
from enum import Enum

from afre.datasets import AdjustmentBasis
from afre.feature_store.models import AvailabilityEvidence
from afre.ids import InstrumentId, validate_fingerprint
from afre.lineage import ProvenanceRef
from afre.schema import Artifact, contract, enum, require


@enum
class TargetActionKind(Enum):
    SPLIT = "new_shares_per_old_share"
    PRICE_FACTOR = "explicit_price_multiplier"
    CASH_DISTRIBUTION = "cash_distribution_contract_only"


@contract("target_action")
@dataclass(frozen=True, slots=True)
class TargetCorporateAction(Artifact):
    instrument: InstrumentId
    event_id: str
    effective_ns: int
    kind: TargetActionKind
    amount: float
    dataset_id: str
    clocks: AvailabilityEvidence
    source: ProvenanceRef
    predecessor_id: str | None = None

    def _validate(self) -> None:
        validate_fingerprint(self.dataset_id)
        require(self.amount > 0, "positive action ratio/amount required")
        require(self.clocks.historical_delivery is None, "action backdating unsupported")
        if self.predecessor_id is not None:
            validate_fingerprint(self.predecessor_id, "target_action")


@contract("target_action_stream")
@dataclass(frozen=True, slots=True)
class TargetActionStream(Artifact):
    dataset_id: str
    build_version: str
    action_ids: tuple[str, ...]
    coverage_start_ns: int
    complete_through_ns: int
    clocks: AvailabilityEvidence
    evidence: ProvenanceRef

    def _normalize(self) -> None:
        require(len(set(self.action_ids)) == len(self.action_ids), "duplicate action evidence")
        object.__setattr__(self, "action_ids", tuple(sorted(self.action_ids)))

    def _validate(self) -> None:
        validate_fingerprint(self.dataset_id)
        for identity in self.action_ids:
            validate_fingerprint(identity, "target_action")
        require(
            self.coverage_start_ns
            <= self.complete_through_ns
            <= self.clocks.final_available_ns,
            "action stream coverage is not complete by availability",
        )
        require(self.clocks.historical_delivery is None, "action stream backdating unsupported")


def adjusted_price(
    price: float,
    at_ns: int,
    start_ns: int,
    basis: AdjustmentBasis,
    actions: tuple[TargetCorporateAction, ...],
) -> float:
    require(
        basis is not AdjustmentBasis.TOTAL_RETURN,
        "total-return/dividend reinvestment is contract-only in AFRE-2",
    )
    if basis is AdjustmentBasis.RAW:
        return price
    multiplier = 1.0
    for action in actions:
        if start_ns < action.effective_ns <= at_ns:
            if basis is AdjustmentBasis.SPLIT_ADJUSTED:
                require(
                    action.kind in (TargetActionKind.SPLIT, TargetActionKind.CASH_DISTRIBUTION),
                    "split-adjusted policy rejects explicit price factors",
                )
                if action.kind is TargetActionKind.SPLIT:
                    multiplier *= action.amount
            else:
                require(
                    action.kind is TargetActionKind.PRICE_FACTOR,
                    "explicit adjustment stream requires explicit price multipliers",
                )
                multiplier *= action.amount
    return price * multiplier

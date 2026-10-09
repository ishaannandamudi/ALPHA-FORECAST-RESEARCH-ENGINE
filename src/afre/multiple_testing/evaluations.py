"""Separate adjusted evidence, conservative missing slots and final/interim claims."""

from dataclasses import dataclass

from afre.ids import validate_fingerprint
from afre.multiple_testing.schema import (
    CorrectionMethod,
    EvidenceState,
    FamilyCompleteness,
    ids,
)
from afre.schema import Artifact, contract, require


@contract("mt_adjusted")
@dataclass(frozen=True, slots=True)
class AdjustedHypothesisResult(Artifact):
    analysis_spec_id: str
    family_id: str
    plan_id: str
    hypothesis_id: str
    trial_id: str | None
    pvalue_id: str | None
    effect_id: str | None
    correction: CorrectionMethod
    family_size: int
    raw_p_value: float | None
    adjusted_value: float | None
    level: float
    reject: bool | None
    rank: int
    state: EvidenceState
    reason: str
    available_ns: int

    def _validate(self) -> None:
        for identity in (
            self.analysis_spec_id,
            self.family_id,
            self.plan_id,
            self.hypothesis_id,
            self.trial_id,
            self.pvalue_id,
            self.effect_id,
        ):
            if identity:
                validate_fingerprint(identity)
        require(
            1 <= self.rank <= self.family_size <= 2000 and 0 < self.level < 1,
            "adjusted rank/size/level",
        )
        require(
            all(p is None or 0 <= p <= 1 for p in (self.raw_p_value, self.adjusted_value)),
            "adjusted evidence bounds",
        )
        require(
            self.reject is None
            or self.state is EvidenceState.AVAILABLE
            and self.adjusted_value is not None
            and self.reject == (self.adjusted_value <= self.level),
            "final rejection only for supported complete evidence",
        )
        require(
            self.state is not EvidenceState.AVAILABLE or self.reject is not None,
            "final result requires explicit decision",
        )


@contract("mt_family_result")
@dataclass(frozen=True, slots=True)
class FamilyAnalysis(Artifact):
    spec_id: str
    family_id: str
    adjusted_ids: tuple[str, ...]
    family_size: int
    completed_count: int
    failed_count: int
    missing_count: int
    completeness: FamilyCompleteness
    state: EvidenceState
    reason: str
    error_control: str
    available_ns: int

    def _normalize(self) -> None:
        ids(self, "adjusted_ids")

    def _validate(self) -> None:
        validate_fingerprint(self.spec_id, "mt_analysis_spec")
        validate_fingerprint(self.family_id, "mt_family")
        require(
            len(self.adjusted_ids) == self.family_size
            and self.completed_count + self.failed_count + self.missing_count
            == self.family_size
            and self.family_size > 0,
            "complete declared analysis slot accounting",
        )
        require(
            self.state is not EvidenceState.AVAILABLE
            or self.completeness is FamilyCompleteness.COMPLETE
            and self.missing_count == 0,
            "no final open/partial family claims",
        )

"""Exact declared opportunities; missing attempts consume a conservative family slot."""

from dataclasses import dataclass

from afre.multiple_testing.schema import (
    CorrectionMethod,
    DependenceAssumption,
    FamilyCompleteness,
    ids,
)
from afre.schema import Artifact, contract, require


@contract("mt_family")
@dataclass(frozen=True, slots=True)
class HypothesisFamily(Artifact):
    family_key: str
    plan_ids: tuple[str, ...]
    correction: CorrectionMethod
    level: float
    dependence: DependenceAssumption
    declared_ns: int
    caller_attested_predeclaration: bool
    additional_corrections: tuple[CorrectionMethod, ...] = ()
    membership_policy: str = "all-exact-declared-attempts-missing-count-as-one-v1"

    def _normalize(self) -> None:
        ids(self, "plan_ids")
        require(
            len(set(self.additional_corrections)) == len(self.additional_corrections)
            and self.correction not in self.additional_corrections
            and len(self.additional_corrections) <= 3,
            "distinct predeclared correction reports",
        )
        object.__setattr__(
            self,
            "additional_corrections",
            tuple(sorted(self.additional_corrections, key=lambda m: m.value)),
        )

    def _validate(self) -> None:
        require(
            1 <= len(self.plan_ids) <= 2000
            and 0 < self.level < 1
            and len(self.family_key) <= 128,
            "explicit bounded family/alpha/q",
        )
        require(
            self.membership_policy == "all-exact-declared-attempts-missing-count-as-one-v1",
            "closed family size/missing policy",
        )


@contract("mt_analysis_spec")
@dataclass(frozen=True, slots=True)
class FamilyAnalysisSpec(Artifact):
    family_id: str
    correction: CorrectionMethod
    trial_ids: tuple[str, ...]
    completeness: FamilyCompleteness
    cutoff_ns: int
    available_ns: int

    def _normalize(self) -> None:
        ids(self, "trial_ids")

    def _validate(self) -> None:
        from afre.ids import validate_fingerprint

        validate_fingerprint(self.family_id, "mt_family")
        require(
            len(self.trial_ids) <= 2000 and self.cutoff_ns <= self.available_ns,
            "family analysis bound/clocks",
        )

"""Explicit null, direction, effect and caller-attested sampling assumptions."""

from dataclasses import dataclass

from afre.ids import validate_fingerprint
from afre.multiple_testing.schema import (
    HypothesisDirection,
    RawTestMethod,
    ResearchMetric,
    metric_unit,
)
from afre.schema import Artifact, contract, require


@contract("mt_assumptions")
@dataclass(frozen=True, slots=True)
class TestAssumptions(Artifact):
    independent_nonzero_signs: bool
    conditional_fair_sign_null: bool
    exact_pairing: bool
    nonoverlapping_labels: bool
    attestor: str
    declared_ns: int


@contract("mt_hypothesis")
@dataclass(frozen=True, slots=True)
class HypothesisDefinition(Artifact):
    hypothesis_key: str
    family_key: str
    target_id: str
    horizon_id: str
    metric: ResearchMetric
    null_value: float
    direction: HypothesisDirection
    method: RawTestMethod
    minimum_support: int
    assumptions: TestAssumptions
    declared_ns: int
    null: str = "conditional-nonzero-sign-probability-equals-one-half-v1"
    alternative: str = "declared-direction-of-conditional-sign-probability-v1"
    effect_definition: str = "descriptive-sample-median-minus-declared-null-v1"

    def _validate(self) -> None:
        validate_fingerprint(self.target_id, "target_definition")
        validate_fingerprint(self.horizon_id)
        require(1 <= self.minimum_support <= 2000, "explicit hypothesis support")
        require(self.assumptions.declared_ns <= self.declared_ns, "assumptions declaration")
        require(
            self.null == "conditional-nonzero-sign-probability-equals-one-half-v1"
            and self.alternative == "declared-direction-of-conditional-sign-probability-v1"
            and self.effect_definition == "descriptive-sample-median-minus-declared-null-v1",
            "closed test/effect semantics",
        )
        require(
            len(self.hypothesis_key) <= 128 and len(self.family_key) <= 128,
            "hypothesis keys bounded",
        )

    @property
    def unit(self) -> str:
        return metric_unit(self.metric)

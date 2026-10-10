"""Descriptive B-minus-A metrics on the exact common validation/truth intersection."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from afre.schema import Artifact, contract, require
from afre.selection.criteria import metric
from afre.selection.results import CandidateValidationResult
from afre.selection.schema import SelectionCriterion

if TYPE_CHECKING:
    from afre.selection.repository import SelectionRepository


@contract("sel_comparison")
@dataclass(frozen=True, slots=True)
class CandidateComparison(Artifact):
    left_validation_id: str
    right_validation_id: str
    criterion: SelectionCriterion
    matched_sample_truth_ids: tuple[tuple[str, str], ...]
    minimum_support: int
    left_value: float | None
    right_value: float | None
    delta_b_minus_a: float | None
    orientation: str = "B-minus-A-descriptive-only-v1"

    def _validate(self) -> None:
        require(
            1 <= self.minimum_support <= 2000
            and len(self.matched_sample_truth_ids) <= 2000
            and self.orientation == "B-minus-A-descriptive-only-v1",
            "comparison protocol",
        )
        require(
            (self.delta_b_minus_a is None)
            == (self.left_value is None or self.right_value is None),
            "comparison availability",
        )


def comparison_for(
    repo: "SelectionRepository", left_id: str, right_id: str, minimum_support: int
) -> CandidateComparison:
    a, b = (
        repo.resolve(CandidateValidationResult, left_id),
        repo.resolve(CandidateValidationResult, right_id),
    )
    require(
        a.criterion is b.criterion and a.truth_cutoff_ns == b.truth_cutoff_ns,
        "comparison exact criterion/cutoff",
    )
    from afre.selection.definitions import CandidateSpec

    ca, cb = (
        repo.resolve(CandidateSpec, a.candidate_id),
        repo.resolve(CandidateSpec, b.candidate_id),
    )
    require(
        (ca.target_id, ca.horizon_id, ca.dataset_id, ca.fold_id)
        == (cb.target_id, cb.horizon_id, cb.dataset_id, cb.fold_id),
        "comparison exact target/horizon/fold",
    )
    aa = {(p.sample_id, p.truth_id): p for p in a.pairs}
    bb = {(p.sample_id, p.truth_id): p for p in b.pairs}
    common = tuple(sorted(aa.keys() & bb.keys()))
    av = (
        metric(
            a.criterion, tuple(aa[k] for k in common), tuple(aa[k].primary_loss for k in common)
        )
        if len(common) >= minimum_support
        else None
    )
    bv = (
        metric(
            b.criterion, tuple(bb[k] for k in common), tuple(bb[k].primary_loss for k in common)
        )
        if len(common) >= minimum_support
        else None
    )
    return CandidateComparison(
        left_id,
        right_id,
        a.criterion,
        common,
        minimum_support,
        av,
        bv,
        bv - av if av is not None and bv is not None else None,
    )

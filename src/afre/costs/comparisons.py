"""Supplied signals on matched samples and identical policies; no winner selection."""

from typing import TYPE_CHECKING

from afre.costs.artifacts import (
    CostAwareComparison,
    CostAwareEvaluation,
    CostAwareSampleEvaluation,
)
from afre.costs.definitions import CostScenario
from afre.costs.schema import CostResultState
from afre.schema import require

if TYPE_CHECKING:
    from afre.costs.repository import CostResearchRepository


def policy_key(s: CostScenario) -> tuple[object, ...]:
    return (
        s.target,
        s.fold_id,
        s.sample_ids,
        s.exposure_rule,
        s.components,
        s.bindings,
        s.liquidity,
        s.timing,
        s.missing_policy,
        s.currency,
        s.signal_unit,
        s.maximum_participation,
        s.maximum_input_age_ns,
        s.minimum_count,
        s.allow_degraded,
        s.approved_delivery_attestors,
        s.implementation_version,
        s.turnover_convention,
        s.contribution_convention,
    )


def comparison_for(
    repo: "CostResearchRepository", left_id: str, right_id: str, available_ns: int
) -> CostAwareComparison:
    left, right = (
        repo.resolve(CostAwareEvaluation, left_id),
        repo.resolve(CostAwareEvaluation, right_id),
    )
    require(
        available_ns >= max(left.available_ns, right.available_ns),
        "comparison actual availability",
    )
    ls, rs = (
        repo.resolve(CostScenario, left.scenario_id),
        repo.resolve(CostScenario, right.scenario_id),
    )
    lrows = {
        r.sample_id: r
        for i in left.sample_evaluation_ids
        if (r := repo.resolve(CostAwareSampleEvaluation, i)).state is CostResultState.AVAILABLE
    }
    rrows = {
        r.sample_id: r
        for i in right.sample_evaluation_ids
        if (r := repo.resolve(CostAwareSampleEvaluation, i)).state is CostResultState.AVAILABLE
    }
    common = tuple(sorted(lrows.keys() & rrows.keys()))
    valid = (
        policy_key(ls) == policy_key(rs)
        and left.evaluation_cutoff_ns == right.evaluation_cutoff_ns
        and left.included_sample_ids == right.included_sample_ids
        and all(
            lrows[i].truth_id == rrows[i].truth_id and lrows[i].origin == rrows[i].origin
            for i in common
        )
        and left.state is right.state is CostResultState.AVAILABLE
    )
    gross_delta = net_delta = trade_delta = None
    if valid:
        assert (
            left.gross_mean is not None
            and right.gross_mean is not None
            and left.net_mean is not None
            and right.net_mean is not None
        )
        gross_delta, net_delta, trade_delta = (
            right.gross_mean - left.gross_mean,
            right.net_mean - left.net_mean,
            right.turnover - left.turnover,
        )
    return CostAwareComparison(
        left_id,
        right_id,
        common,
        gross_delta,
        net_delta,
        trade_delta,
        CostResultState.AVAILABLE if valid else CostResultState.INCOMPARABLE,
        "exact-matched-cost-policy-descriptive-right-minus-left"
        if valid
        else "cost-policy-samples-truth-cutoff-or-state-incompatible",
        available_ns,
    )

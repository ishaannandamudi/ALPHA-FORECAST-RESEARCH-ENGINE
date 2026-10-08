"""Exact budget diagnostics with explicit unavailable nonnegative thresholds."""

import math
from typing import TYPE_CHECKING

from afre.costs.artifacts import (
    BreakEvenCostDiagnostic,
    CostAwareEvaluation,
    CostAwareSampleEvaluation,
    CostComponentEstimate,
    TotalCostEstimate,
)
from afre.costs.definitions import CostComponentSpec, CostScenario
from afre.costs.impact import impact_multiplier
from afre.costs.schema import CostResultState, CostUnit
from afre.schema import require

if TYPE_CHECKING:
    from afre.costs.repository import CostResearchRepository


def evaluated_components(
    repo: "CostResearchRepository", evaluation: CostAwareEvaluation
) -> tuple[CostComponentEstimate, ...]:
    rows = tuple(
        repo.resolve(CostAwareSampleEvaluation, i) for i in evaluation.sample_evaluation_ids
    )
    return tuple(
        repo.resolve(CostComponentEstimate, c)
        for row in rows
        if row.state is CostResultState.AVAILABLE
        for c in repo.resolve(TotalCostEstimate, row.total_cost_id).component_ids
    )


def breakeven_for(
    repo: "CostResearchRepository",
    evaluation_id: str,
    component_id: str | None,
    available_ns: int,
) -> BreakEvenCostDiagnostic:
    evaluation = repo.resolve(CostAwareEvaluation, evaluation_id)
    require(available_ns >= evaluation.available_ns, "break-even availability")
    unit = CostUnit.BASIS_POINTS
    budget = evaluation.gross_sum
    threshold = None
    state = CostResultState.UNAVAILABLE
    reason = "nonpositive-gross-or-zero-turnover"
    if component_id:
        scenario = repo.resolve(CostScenario, evaluation.scenario_id)
        spec = repo.resolve(CostComponentSpec, component_id)
        require(spec in scenario.components, "break-even exact supplied component")
        unit = spec.unit
        components = evaluated_components(repo, evaluation)
        selected = tuple(c for c in components if c.component_id == component_id)
        other = math.fsum(
            c.amount
            for c in components
            if c.component_id != component_id and c.amount is not None
        )
        budget = budget - other if budget is not None else None
        denominator = math.fsum(
            c.unit_conversion_factor * impact_multiplier(spec.model, c.participation)
            for c in selected
            if c.unit_conversion_factor is not None
        )
    else:
        denominator = evaluation.turnover / 10_000
    if (
        evaluation.state is CostResultState.AVAILABLE
        and budget is not None
        and budget >= 0
        and denominator > 0
    ):
        threshold = budget / denominator
        state, reason = CostResultState.AVAILABLE, "algebraic-zero-net-declared-component-level"
    return BreakEvenCostDiagnostic(
        evaluation_id,
        component_id,
        budget,
        threshold,
        unit,
        evaluation.turnover,
        state,
        reason,
        available_ns,
    )

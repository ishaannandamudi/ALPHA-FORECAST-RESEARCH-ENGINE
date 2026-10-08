"""Only compatible nonnegative component contributions may be summed."""

import math
from typing import TYPE_CHECKING

from afre.costs.artifacts import (
    CostComponentEstimate,
    ResearchExposureChange,
    TotalCostEstimate,
)
from afre.costs.definitions import CostScenario
from afre.costs.schema import CostResultState, CostUnit
from afre.schema import require

if TYPE_CHECKING:
    from afre.costs.repository import CostResearchRepository


def total_for(
    repo: "CostResearchRepository", change_id: str, component_ids: tuple[str, ...]
) -> TotalCostEstimate:
    change = repo.resolve(ResearchExposureChange, change_id)
    scenario = repo.resolve(CostScenario, change.scenario_id)
    components = tuple(repo.resolve(CostComponentEstimate, i) for i in sorted(component_ids))
    return total_from(scenario, change, components)


def total_from(
    scenario: CostScenario,
    change: ResearchExposureChange,
    components: tuple[CostComponentEstimate, ...],
) -> TotalCostEstimate:
    component_ids = tuple(c.fingerprint for c in components)
    change_id = change.fingerprint
    require(
        len(component_ids) == len(set(component_ids)) == len(scenario.components)
        and {c.component_id for c in components} == {c.fingerprint for c in scenario.components}
        and all(
            c.change_id == change_id
            and c.scenario_id == scenario.fingerprint
            and c.amount_unit is CostUnit.RETURN_FRACTION
            for c in components
        ),
        "exact compatible total component set",
    )
    amounts = tuple(c.amount for c in components)
    valid = all(a is not None for a in amounts)
    return TotalCostEstimate(
        scenario.fingerprint,
        change_id,
        component_ids,
        change.exposure,
        change.trade_delta,
        math.fsum(a for a in amounts if a is not None) if valid else None,
        CostUnit.RETURN_FRACTION,
        CostResultState.AVAILABLE if valid else CostResultState.EXCLUDED,
        "all-declared-components-compatible"
        if valid
        else "missing-cost-component-explicit-exclusion",
        scenario.timing,
        change.constructed_ns,
        max(c.available_ns for c in components),
    )

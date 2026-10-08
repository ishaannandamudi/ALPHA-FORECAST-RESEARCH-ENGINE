"""Supplied cost/participation/intensity grids; gross held fixed, no fills or sizing."""

import itertools
import math
from typing import TYPE_CHECKING

from afre.costs.artifacts import CostAwareEvaluation, CostSensitivityCurve, CostSensitivityPoint
from afre.costs.breakeven import evaluated_components
from afre.costs.definitions import CostComponentSpec, CostScenario, CostSensitivitySpec
from afre.costs.impact import impact_multiplier
from afre.costs.schema import CostModel, CostResultState
from afre.research_datasets.splits import FoldDefinition
from afre.schema import require

if TYPE_CHECKING:
    from afre.costs.repository import CostResearchRepository


def validate_sensitivity(repo: "CostResearchRepository", spec: CostSensitivitySpec) -> None:
    scenario = repo.resolve(CostScenario, spec.scenario_id)
    component = repo.resolve(CostComponentSpec, spec.component_id)
    fold = repo.resolve(FoldDefinition, scenario.fold_id)
    require(
        component in scenario.components and spec.declared_ns <= fold.training_cutoff_ns,
        "sensitivity fixed before held-out/TRAIN cutoff",
    )
    require(
        not spec.participation_rates
        or component.model in (CostModel.LINEAR_PARTICIPATION, CostModel.SQRT_PARTICIPATION),
        "participation sensitivity requires impact/slippage model",
    )
    require(
        all(p <= scenario.maximum_participation for p in spec.participation_rates),
        "supplied participation grid bound",
    )


def sensitivity_for(
    repo: "CostResearchRepository", evaluation_id: str, spec_id: str, available_ns: int
) -> CostSensitivityCurve:
    evaluation = repo.resolve(CostAwareEvaluation, evaluation_id)
    spec = repo.resolve(CostSensitivitySpec, spec_id)
    scenario = repo.resolve(CostScenario, spec.scenario_id)
    require(
        evaluation.scenario_id == scenario.fingerprint
        and available_ns >= evaluation.available_ns,
        "sensitivity exact scenario/availability",
    )
    validate_sensitivity(repo, spec)
    definitions = {c.fingerprint: c for c in scenario.components}
    components = evaluated_components(repo, evaluation)
    points = []
    for rate, p, multiplier in itertools.product(
        spec.rates, spec.participation_rates or (None,), spec.turnover_multipliers
    ):
        amounts = []
        invalid = evaluation.state is not CostResultState.AVAILABLE
        for c in components:
            d = definitions[c.component_id]
            participation = (
                p
                if p is not None and c.component_id == spec.component_id
                else c.participation * multiplier
                if c.participation is not None
                else None
            )
            if participation is not None and participation > scenario.maximum_participation:
                invalid = True
                continue
            actual_rate = rate if c.component_id == spec.component_id else c.rate
            assert actual_rate is not None and c.unit_conversion_factor is not None
            # Flat per-trade fees stay flat when the nonzero transition magnitude is scaled.
            from afre.costs.schema import CostBasis

            intensity = 1.0 if d.basis is CostBasis.PER_TRADE else multiplier
            amounts.append(
                actual_rate
                * c.unit_conversion_factor
                * intensity
                * impact_multiplier(d.model, participation)
            )
        cost = math.fsum(amounts) if not invalid else None
        net = (
            evaluation.gross_sum - cost
            if evaluation.gross_sum is not None and cost is not None
            else None
        )
        points.append(
            CostSensitivityPoint(
                rate,
                p,
                multiplier,
                cost,
                net,
                net / evaluation.sample_count if net is not None else None,
                CostResultState.UNAVAILABLE if invalid else CostResultState.AVAILABLE,
                "participation-bound-or-insufficient-evaluation"
                if invalid
                else spec.convention,
            )
        )
    return CostSensitivityCurve(evaluation_id, spec_id, tuple(points), available_ns)

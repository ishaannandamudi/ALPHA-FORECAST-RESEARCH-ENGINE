"""Native declared PIT cohorts; full-path trade deltas stay intact at cohort boundaries."""

import math
from typing import TYPE_CHECKING

from afre.costs.artifacts import (
    CostAwareEvaluation,
    CostAwareSampleEvaluation,
    CostCohortEvaluation,
    ResearchExposureChange,
)
from afre.costs.definitions import CostScenario
from afre.costs.schema import CostResultState
from afre.invariance.artifacts import EnvironmentMembership
from afre.invariance.definitions import EnvironmentDefinition
from afre.regime_conditioned.memberships import effective_support
from afre.schema import require

if TYPE_CHECKING:
    from afre.costs.repository import CostResearchRepository


def cohort_for(
    repo: "CostResearchRepository",
    evaluation_id: str,
    environment_id: str,
    membership_ids: tuple[str, ...],
    available_ns: int,
) -> CostCohortEvaluation:
    evaluation = repo.resolve(CostAwareEvaluation, evaluation_id)
    scenario = repo.resolve(CostScenario, evaluation.scenario_id)
    env = repo.resolve(EnvironmentDefinition, environment_id)
    members = tuple(repo.resolve(EnvironmentMembership, i) for i in sorted(membership_ids))
    require(
        len(membership_ids) == len(set(membership_ids)) == len(scenario.sample_ids)
        and {m.sample_id for m in members} == set(scenario.sample_ids)
        and all(
            m.environment_id == environment_id
            and m.available_ns <= evaluation.evaluation_cutoff_ns
            for m in members
        )
        and env.target == scenario.target
        and available_ns >= evaluation.available_ns,
        "exact full declared environment grid/target/cutoff",
    )
    rows = {
        r.sample_id: r
        for i in evaluation.sample_evaluation_ids
        if (r := repo.resolve(CostAwareSampleEvaluation, i)).state is CostResultState.AVAILABLE
    }
    weighted = tuple(
        (m.sample_id, m.weight) for m in members if m.weight > 0 and m.sample_id in rows
    )
    weights = tuple(w for _, w in weighted)
    count = len(weighted)
    support = effective_support(weights)
    enough = count >= max(scenario.minimum_count, env.minimum_count) and support + 1e-12 >= max(
        scenario.minimum_count, env.minimum_count
    )
    weight_sum = math.fsum(weights)

    def mean(field: str) -> float | None:
        vals = tuple((getattr(rows[i], field), w) for i, w in weighted)
        return math.fsum(v * w for v, w in vals) / weight_sum if enough else None

    trades = math.fsum(
        abs(repo.resolve(ResearchExposureChange, rows[i].change_id).trade_delta) * w
        for i, w in weighted
    )
    return CostCohortEvaluation(
        evaluation_id,
        environment_id,
        membership_ids,
        weighted,
        len(members),
        count,
        support,
        mean("gross_contribution"),
        mean("total_cost"),
        mean("net_contribution"),
        trades,
        CostResultState.AVAILABLE if enough else CostResultState.INSUFFICIENT_DATA,
        "full-path-transitions-explicit-cohort-weights"
        if enough
        else "cohort-minimum-or-effective-support",
        available_ns,
    )

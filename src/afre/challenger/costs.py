"""Native cost rows under one explicit economic plan; no exposure or cost refitting."""

from dataclasses import dataclass, fields
from statistics import fmean
from typing import TYPE_CHECKING

from afre.challenger.artifacts import CommonMatchedEvidence, EvaluationEvidence, ShadowForecast
from afre.challenger.programs import ChallengeProgram
from afre.challenger.schema import ChallengeMetric as M
from afre.challenger.schema import ChallengeStatus as S
from afre.costs.artifacts import (
    BreakEvenCostDiagnostic,
    CostAwareEvaluation,
    CostAwareSampleEvaluation,
    ResearchExposureChange,
)
from afre.costs.definitions import CostScenario
from afre.costs.schema import CostResultState
from afre.ids import validate_fingerprint
from afre.schema import Artifact, contract, require

if TYPE_CHECKING:
    from afre.challenger.repository import ChallengeRepository


@contract("ch_cost_plan")
@dataclass(frozen=True, slots=True)
class ChallengeCostPlan(Artifact):
    name: str
    template_scenario_id: str
    declared_ns: int
    convention: str = "same-economic-assumptions-native-source-bound-scenarios-v1"

    def _validate(self) -> None:
        validate_fingerprint(self.template_scenario_id, "cost_scenario")
        require(
            self.convention == "same-economic-assumptions-native-source-bound-scenarios-v1",
            "closed cost comparison plan",
        )


def equivalent(a: CostScenario, b: CostScenario) -> bool:
    # Only source identity, descriptive scenario name and participant-specific
    # uncertainty annotations may differ. Liquidity, cost vintages, exposure
    # mapping, participation, timing, declaration and missingness remain exact.
    ignored = {"scenario_id", "source_ids", "uncertainty_ids"}
    return all(
        getattr(a, f.name) == getattr(b, f.name) for f in fields(a) if f.name not in ignored
    )


def cost_score(
    repo: "ChallengeRepository",
    program: ChallengeProgram,
    common: CommonMatchedEvidence,
    participant_id: str,
    kind: M,
) -> tuple[float | None, S, str]:
    evidence = repo.resolve(EvaluationEvidence, common.evidence_id)
    bindings = dict(evidence.cost_bindings)
    if program.cost_plan_id is None or set(bindings) != {
        program.champion_id,
        *program.challenger_ids,
    }:
        return None, S.INCOMPARABLE, "missing-explicit-shared-native-cost-plan"
    plan = repo.resolve(ChallengeCostPlan, program.cost_plan_id)
    template = repo.resolve(CostScenario, plan.template_scenario_id)
    shadows = tuple(repo.get(ShadowForecast, i) for i in common.shadow_ids)
    truth_map = dict(common.assignments)
    selected = []
    for participant, identity in sorted(bindings.items()):
        result = repo.resolve(CostAwareEvaluation, identity)
        scenario = repo.resolve(CostScenario, result.scenario_id)
        if (
            not equivalent(template, scenario)
            or result.evaluation_cutoff_ns != common.cutoff_ns
            or (
                result.available_ns > evidence.available_ns
                or result.test_evaluation_id != evidence.test_evaluation_id
            )
        ):
            return None, S.INCOMPARABLE, "different-native-cost-assumptions-cutoff-or-seal"
        rows = tuple(
            repo.resolve(CostAwareSampleEvaluation, i) for i in result.sample_evaluation_ids
        )
        by_sample = {r.sample_id: r for r in rows}
        for sample, truth in common.assignments:
            row = by_sample.get(sample)
            shadow = next(
                s for s in shadows if s.participant_id == participant and s.sample_id == sample
            )
            if (
                row is None
                or (row.source_id, row.truth_id, row.target_id, row.horizon_id)
                != (shadow.source_id, truth, program.target_id, program.horizon_id)
                or row.evaluation_cutoff_ns != common.cutoff_ns
                or row.available_ns > evidence.available_ns
            ):
                return (
                    None,
                    S.INCOMPARABLE,
                    "native-cost-exact-source-truth-common-support-required",
                )
            if row.state is not CostResultState.AVAILABLE:
                return None, S.UNAVAILABLE, "native-cost-row-unavailable"
            if participant == participant_id:
                selected.append(row)
    require(len(selected) == len(truth_map), "cost retains exact common support")
    if kind is M.BREAK_EVEN_COST:
        diagnostics = dict(evidence.breakeven_bindings)
        if set(diagnostics) != set(bindings):
            return None, S.UNAVAILABLE, "no-explicit-common-support-break-even-diagnostic"
        thresholds: dict[str, float] = {}
        units = set()
        for participant, identity in sorted(diagnostics.items()):
            diagnostic = repo.resolve(BreakEvenCostDiagnostic, identity)
            evaluation = repo.resolve(CostAwareEvaluation, bindings[participant])
            if (
                diagnostic.evaluation_id != evaluation.fingerprint
                or set(evaluation.included_sample_ids) != set(truth_map)
                or diagnostic.available_ns > evidence.available_ns
            ):
                return (
                    None,
                    S.INCOMPARABLE,
                    "break-even-requires-exact-common-native-evaluation",
                )
            if diagnostic.threshold is None:
                return None, S.UNAVAILABLE, "native-break-even-threshold-unavailable"
            units.add((diagnostic.threshold_unit, diagnostic.component_id))
            thresholds[participant] = diagnostic.threshold
        if len(units) != 1:
            return None, S.INCOMPARABLE, "break-even-different-native-component-or-unit"
        return thresholds[participant_id], S.AVAILABLE, "native-common-support-break-even"
    values = []
    for row in selected:
        value: float | None
        if kind is M.TURNOVER:
            value = abs(repo.resolve(ResearchExposureChange, row.change_id).trade_delta)
        else:
            value = (
                row.gross_contribution
                if kind is M.GROSS_EDGE
                else (row.total_cost if kind is M.COST else row.net_contribution)
            )
        assert value is not None
        values.append(value)
    return fmean(values), S.AVAILABLE, "native-common-support-gross-cost-net-separated"

"""Explicit health/cost requirements and append-only criteria and native context."""

from dataclasses import replace

import pytest

from afre.challenger import (
    ChallengeMetric as M,
)
from afre.challenger import (
    CommonMatchedEvidence,
    ParticipantMetricResult,
    PromotionAssessment,
)
from afre.challenger import (
    PromotionOutcome as P,
)
from afre.health import HealthStatus
from afre.schema import ContractError
from afre.serialization import canonical_json
from examples.challenge_context import cost_context_for, health_context_for
from examples.challenger_fixture import evidence_for, program_for
from tests.challenger.conftest import ChallengeCase


@pytest.mark.parametrize("state", [None, HealthStatus.HEALTHY, HealthStatus.DEGRADED])
def test_explicit_health_criterion(
    challenge_case: ChallengeCase, state: HealthStatus | None
) -> None:
    c = challenge_case
    program, criteria = program_for(c.fixture)
    rule = replace(
        criteria[0], challenger_health=(HealthStatus.HEALTHY if state is None else state,)
    )
    program = replace(
        program,
        promotion_criterion_ids=(rule.fingerprint,),
        health_participant_ids=program.challenger_ids,
    )
    c.engine.declare(program, (rule,))
    evidence = evidence_for(c.repo, c.fixture, program)
    if state is not None:
        bindings = health_context_for(c.repo, c.fixture, program)
        evidence = replace(
            evidence,
            health_bindings=tuple(b for b in bindings if b[0] in program.challenger_ids),
        )
    c.engine.evidence(evidence)
    run = c.engine.evaluate(evidence.fingerprint)
    better = next(
        c.repo.resolve(PromotionAssessment, i)
        for i in run.promotion_ids
        if c.repo.get(PromotionAssessment, i).challenger_id
        == c.fixture.participants[1].fingerprint
    )
    assert better.outcome is (
        P.INCOMPARABLE
        if state is None
        else P.PROMOTION_ELIGIBLE
        if state is HealthStatus.HEALTHY
        else P.PROMOTION_NOT_ELIGIBLE
    )


def test_cost_common_grid_and_separate_gross_net(challenge_case: ChallengeCase) -> None:
    c = challenge_case
    program, criteria = program_for(
        c.fixture, (M.GROSS_EDGE, M.COST, M.NET_EDGE, M.TURNOVER, M.BREAK_EVEN_COST)
    )
    plan, bindings = cost_context_for(c.repo, c.fixture, program)
    program = replace(program, cost_plan_id=plan.fingerprint)
    c.engine.declare(program, criteria)
    evidence = c.engine.evidence(
        replace(evidence_for(c.repo, c.fixture, program), cost_bindings=bindings)
    )
    run = c.engine.evaluate(evidence.fingerprint)
    metrics = tuple(c.repo.resolve(ParticipantMetricResult, i) for i in run.metric_ids)
    for participant in (program.champion_id, *program.challenger_ids):
        scores = {m.kind: m.value for m in metrics if m.participant_id == participant}
        assert scores[M.COST] == pytest.approx(0.00047)
        assert scores[M.TURNOVER] == 1.0
        gross, net = scores[M.GROSS_EDGE], scores[M.NET_EDGE]
        assert gross is not None and net is not None
        assert net == pytest.approx(gross - 0.00047)
        assert scores[M.BREAK_EVEN_COST] is None
    assert len({m.sample_ids for m in metrics}) == 1


def test_cost_requirement_missing_is_incomparable(challenge_case: ChallengeCase) -> None:
    c = challenge_case
    program, criteria = program_for(c.fixture)
    rule = replace(criteria[0], requires_cost=True)
    program = replace(program, promotion_criterion_ids=(rule.fingerprint,))
    c.engine.declare(program, (rule,))
    evidence = c.engine.evidence(evidence_for(c.repo, c.fixture, program))
    run = c.engine.evaluate(evidence.fingerprint)
    assert all(
        c.repo.resolve(PromotionAssessment, i).outcome is P.INCOMPARABLE
        for i in run.promotion_ids
    )


def test_required_research_context_is_never_fabricated(challenge_case: ChallengeCase) -> None:
    c = challenge_case
    program, criteria = program_for(c.fixture)
    rule = replace(criteria[0], required_context_ids=(program.target_id,))
    program = replace(program, promotion_criterion_ids=(rule.fingerprint,))
    c.engine.declare(program, (rule,))
    evidence = c.engine.evidence(evidence_for(c.repo, c.fixture, program))
    run = c.engine.evaluate(evidence.fingerprint)
    assert all(
        c.repo.resolve(PromotionAssessment, i).outcome is P.INCOMPARABLE
        for i in run.promotion_ids
    )


def test_criteria_correction_creates_new_program_and_run(challenge_case: ChallengeCase) -> None:
    c = challenge_case
    program, criteria = program_for(c.fixture)
    c.engine.declare(program, criteria)
    evidence = c.engine.evidence(evidence_for(c.repo, c.fixture, program))
    old = c.engine.evaluate(evidence.fingerprint)
    before = canonical_json(old)
    rule = replace(criteria[0], required_improvement=1.0)
    changed = replace(program, promotion_criterion_ids=(rule.fingerprint,))
    c.engine.declare(changed, (rule,))
    new_evidence = c.engine.evidence(evidence_for(c.repo, c.fixture, changed))
    new = c.engine.evaluate(new_evidence.fingerprint)
    assert new.fingerprint != old.fingerprint and changed.fingerprint != program.fingerprint
    assert canonical_json(c.repo.resolve(type(old), old.fingerprint)) == before
    assert c.repo.resolve(CommonMatchedEvidence, new.common_id).assignments
    with pytest.raises(ContractError):
        replace(rule, required_improvement=-1.0)


def test_health_correction_preserves_old_run(challenge_case: ChallengeCase) -> None:
    c = challenge_case
    program, rules = program_for(c.fixture)
    program = replace(
        program, health_participant_ids=(program.champion_id, *program.challenger_ids)
    )
    c.engine.declare(program, rules)
    evidence = c.engine.evidence(
        replace(
            evidence_for(c.repo, c.fixture, program),
            health_bindings=health_context_for(c.repo, c.fixture, program),
        )
    )
    old = c.engine.evaluate(evidence.fingerprint)
    before = canonical_json(old)
    new = c.engine.evidence(
        replace(
            evidence,
            health_bindings=health_context_for(
                c.repo, c.fixture, program, warning_threshold=0.0
            ),
        )
    )
    updated = c.engine.evaluate(new.fingerprint)
    assert updated.fingerprint != old.fingerprint
    assert new.health_bindings != evidence.health_bindings
    assert canonical_json(c.repo.resolve(type(old), old.fingerprint)) == before


@pytest.mark.parametrize(
    "scenario", ["equal", "changed-fee", "partial-support", "wrong-diagnostic"]
)
def test_cost_diagnostics_and_corrections(challenge_case: ChallengeCase, scenario: str) -> None:
    from afre.challenger import ChallengeStatus
    from afre.costs import CostResearchEngine

    c = challenge_case
    program, rules = program_for(c.fixture, (M.NET_EDGE, M.BREAK_EVEN_COST))
    plan, bindings = cost_context_for(c.repo, c.fixture, program)
    program = replace(program, cost_plan_id=plan.fingerprint)
    c.engine.declare(program, rules)
    diagnostics = tuple(
        (p, CostResearchEngine(c.repo).breakeven(i, 120).fingerprint) for p, i in bindings
    )
    evidence = c.engine.evidence(
        replace(
            evidence_for(c.repo, c.fixture, program),
            cost_bindings=bindings,
            breakeven_bindings=diagnostics,
        )
    )
    old = c.engine.evaluate(evidence.fingerprint)
    assert all(c.repo.get(ParticipantMetricResult, i).value is not None for i in old.metric_ids)
    if scenario == "equal":
        assert all(
            c.repo.get(ParticipantMetricResult, i).status is ChallengeStatus.AVAILABLE
            for i in old.metric_ids
        )
        from afre.challenger import ChallengerComparison

        assert all(
            c.repo.get(ChallengerComparison, i).oriented_improvement is None
            for i in old.comparison_ids
            if c.repo.get(
                ParticipantMetricResult,
                c.repo.get(ChallengerComparison, i).challenger_metric_id,
            ).kind
            is M.BREAK_EVEN_COST
        )
        return
    if scenario == "changed-fee":
        revised_plan, revised_bindings = cost_context_for(c.repo, c.fixture, program, fee=0.03)
        # Comparing new costs under the old declared plan fails closed.
        wrong = c.engine.evidence(
            replace(evidence, cost_bindings=revised_bindings, breakeven_bindings=())
        )
        wrong_run = c.engine.evaluate(wrong.fingerprint)
        assert all(
            c.repo.get(ParticipantMetricResult, i).status is ChallengeStatus.INCOMPARABLE
            for i in wrong_run.metric_ids
        )
        updated_program = replace(program, cost_plan_id=revised_plan.fingerprint)
        c.engine.declare(updated_program, rules)
        new = c.engine.evidence(
            replace(
                evidence_for(c.repo, c.fixture, updated_program), cost_bindings=revised_bindings
            )
        )
        new_run = c.engine.evaluate(new.fingerprint)
        assert new_run.program_id != old.program_id
        assert all(
            c.repo.get(ParticipantMetricResult, i).value is not None
            for i in new_run.metric_ids
            if c.repo.get(ParticipantMetricResult, i).kind is M.NET_EDGE
        )
    else:
        changed = (
            replace(evidence, truth_assignments=evidence.truth_assignments[:2])
            if scenario == "partial-support"
            else replace(
                evidence,
                breakeven_bindings=tuple((p, diagnostics[0][1]) for p, _ in diagnostics),
            )
        )
        changed = c.engine.evidence(changed)
        new_run = c.engine.evaluate(changed.fingerprint)
        assert all(
            c.repo.get(ParticipantMetricResult, i).status is ChallengeStatus.INCOMPARABLE
            for i in new_run.metric_ids
            if c.repo.get(ParticipantMetricResult, i).kind is M.BREAK_EVEN_COST
        )
    assert c.repo.resolve(type(old), old.fingerprint) == old


@pytest.mark.parametrize("case", ("required-cost", "different-component", "late-diagnostic"))
def test_explicit_cost_requirements_and_diagnostic_units(
    challenge_case: ChallengeCase, case: str
) -> None:
    from afre.challenger import ChallengeStatus
    from afre.costs import CostResearchEngine
    from afre.costs.artifacts import CostAwareEvaluation
    from afre.costs.definitions import CostScenario

    c = challenge_case
    program, rules = program_for(
        c.fixture, (M.MAE,) if case == "required-cost" else (M.BREAK_EVEN_COST,)
    )
    plan, bindings = cost_context_for(c.repo, c.fixture, program)
    if case == "required-cost":
        rules = tuple(replace(r, requires_cost=True) for r in rules)
    program = replace(
        program,
        cost_plan_id=plan.fingerprint,
        promotion_criterion_ids=tuple(r.fingerprint for r in rules),
    )
    c.engine.declare(program, rules)
    diagnostic_bindings = []
    for index, (p, i) in enumerate(bindings):
        scenario = c.repo.get(CostScenario, c.repo.get(CostAwareEvaluation, i).scenario_id)
        component = next(x.fingerprint for x in scenario.components if x.name == "fee")
        diagnostic = CostResearchEngine(c.repo).breakeven(
            i,
            121 if case == "late-diagnostic" else 120,
            component if case == "different-component" and index == 0 else None,
        )
        diagnostic_bindings.append((p, diagnostic.fingerprint))
    evidence = c.engine.evidence(
        replace(
            evidence_for(c.repo, c.fixture, program),
            cost_bindings=bindings,
            breakeven_bindings=tuple(diagnostic_bindings),
        )
    )
    run = c.engine.evaluate(evidence.fingerprint)
    if case == "required-cost":
        assert {c.repo.get(PromotionAssessment, i).outcome for i in run.promotion_ids} == {
            P.PROMOTION_ELIGIBLE,
            P.PROMOTION_NOT_ELIGIBLE,
        }
    else:
        assert all(
            c.repo.get(ParticipantMetricResult, i).status is ChallengeStatus.INCOMPARABLE
            for i in run.metric_ids
        )

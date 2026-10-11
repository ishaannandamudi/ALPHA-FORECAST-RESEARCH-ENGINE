"""Independent threshold, status, cross-section and frozen-window boundary oracles."""

from dataclasses import replace
from math import nextafter

import pytest

from afre.challenger import (
    ChallengeDirection,
    ChallengeMetric,
    ChallengeMetricRequest,
    ChallengerComparison,
    ChallengeStatus,
    CommonMatchedEvidence,
    ParticipantMetricResult,
    PromotionAssessment,
    PromotionOutcome,
    ShadowForecast,
)
from afre.challenger.assessments import comparison_for, promotion_for
from afre.challenger.metrics import rank_score
from afre.schema import ContractError
from examples.challenger_fixture import evidence_for, program_for
from tests.challenger.conftest import ChallengeCase


@pytest.mark.parametrize("status", list(ChallengeStatus))
def test_comparison_status_and_descriptive_delta(
    challenge_case: ChallengeCase, status: ChallengeStatus
) -> None:
    c = challenge_case
    program, rules = program_for(c.fixture)
    c.engine.declare(program, rules)
    evidence = c.engine.evidence(evidence_for(c.repo, c.fixture, program))
    run = c.engine.evaluate(evidence.fingerprint)
    metrics = tuple(c.repo.get(ParticipantMetricResult, i) for i in run.metric_ids)
    champion = next(m for m in metrics if m.participant_id == program.champion_id)
    challenger = next(m for m in metrics if m.participant_id == program.challenger_ids[0])
    # Test the pure comparison primitive independently of publication/replay.
    a = replace(champion, value=0.25, orientation="descriptive-only")
    b = replace(
        challenger, value=0.375 if status is ChallengeStatus.AVAILABLE else None, status=status
    )
    result = comparison_for(program, a, b)
    assert result.status is status
    assert result.oriented_improvement is None
    assert result.delta == (0.125 if status is ChallengeStatus.AVAILABLE else None)
    with pytest.raises(ContractError, match="support"):
        comparison_for(
            program,
            a,
            replace(b, count=1, sample_ids=b.sample_ids[:1], truth_ids=b.truth_ids[:1]),
        )


@pytest.mark.parametrize("direction", list(ChallengeDirection))
@pytest.mark.parametrize("boundary", ("below", "exact", "above"))
def test_inclusive_promotion_threshold(
    challenge_case: ChallengeCase, direction: ChallengeDirection, boundary: str
) -> None:
    c = challenge_case
    program, rules = program_for(c.fixture)
    rule = replace(rules[0], direction=direction, required_improvement=0.125)
    program = replace(program, promotion_criterion_ids=(rule.fingerprint,))
    c.engine.declare(program, (rule,))
    evidence = c.engine.evidence(evidence_for(c.repo, c.fixture, program))
    run = c.engine.evaluate(evidence.fingerprint)
    assessment = c.repo.get(PromotionAssessment, run.promotion_ids[0])
    original = tuple(c.repo.get(ChallengerComparison, i) for i in assessment.comparison_ids)
    magnitude = {
        "below": nextafter(0.125, 0.0),
        "exact": 0.125,
        "above": nextafter(0.125, 1.0),
    }[boundary]
    delta = magnitude if direction is ChallengeDirection.HIGHER else -magnitude
    comparisons = tuple(replace(v, delta=delta) for v in original)
    result = promotion_for(c.repo, program, evidence, assessment.challenger_id, comparisons)
    assert result.outcome is (
        PromotionOutcome.PROMOTION_NOT_ELIGIBLE
        if boundary == "below"
        else PromotionOutcome.PROMOTION_ELIGIBLE
    )
    assert result.action == "MANUAL_ONLY"


@pytest.mark.parametrize("case", ("small", "constant", "ties", "empty"))
def test_rank_cross_section_support_and_ties(challenge_case: ChallengeCase, case: str) -> None:
    c = challenge_case
    program, rules = program_for(c.fixture)
    c.engine.declare(program, rules)
    evidence = evidence_for(c.repo, c.fixture, program)
    shadows = tuple(c.repo.get(ShadowForecast, i) for i in evidence.shadow_ids)
    selected = sorted(
        (s for s in shadows if s.participant_id == program.champion_id),
        key=lambda s: s.security_id,
    )
    rows = tuple((replace(s, value=1.0), 1.0) for s in selected)
    request = ChallengeMetricRequest(ChallengeMetric.TOP_K_OVERLAP, 1, top_k=2)
    if case == "small":
        request = replace(request, top_k=4)
    elif case == "constant":
        request = replace(request, kind=ChallengeMetric.IC)
    elif case == "empty":
        rows = ()
    value, details = rank_score(request, rows)
    assert value == (1.0 if case == "ties" else None)
    assert bool(details) == (case == "ties")


@pytest.mark.parametrize("case", ("missing-truth", "outside-window", "metric-minimum"))
def test_explicit_matching_exclusions(challenge_case: ChallengeCase, case: str) -> None:
    c = challenge_case
    program, rules = program_for(c.fixture)
    if case == "outside-window":
        program = replace(program, window=replace(program.window, start_ns=41, end_ns=42))
    if case == "metric-minimum":
        request = replace(program.requests[0], minimum_count=4)
        rule = replace(rules[0], request_id=request.fingerprint)
        rules = (rule,)
        program = replace(
            program, requests=(request,), promotion_criterion_ids=(rule.fingerprint,)
        )
    c.engine.declare(program, rules)
    if case == "outside-window":
        # Inputs are admissible causal shadows, explicitly outside the frozen evaluation window.
        original, original_rules = program_for(c.fixture)
        c.engine.declare(original, original_rules)
        evidence = evidence_for(c.repo, c.fixture, original)
        shadows = tuple(c.repo.get(ShadowForecast, i) for i in evidence.shadow_ids)
        ids = tuple(
            c.engine.shadow(
                program.fingerprint, s.participant_id, s.source_id, s.computed_ns
            ).fingerprint
            for s in shadows
        )
        evidence = replace(evidence, program_id=program.fingerprint, shadow_ids=ids)
    else:
        evidence = evidence_for(c.repo, c.fixture, program)
    if case == "missing-truth":
        evidence = replace(evidence, truth_assignments=())
    evidence = c.engine.evidence(evidence)
    run = c.engine.evaluate(evidence.fingerprint)
    common = c.repo.resolve(CommonMatchedEvidence, run.common_id)
    if case == "metric-minimum":
        assert common.status is ChallengeStatus.AVAILABLE
        assert all(
            c.repo.get(ParticipantMetricResult, i).status is ChallengeStatus.INSUFFICIENT_DATA
            for i in run.metric_ids
        )
    else:
        assert not common.assignments
        assert all(
            ("no-explicit-truth" if case == "missing-truth" else "outside-frozen-window")
            in reason
            for _, reason in common.exclusions
        )


def test_shadow_declaration_and_partition_boundaries(challenge_case: ChallengeCase) -> None:
    c = challenge_case
    program, rules = program_for(c.fixture)
    program = replace(program, declared_ns=40)
    c.engine.declare(program, rules)
    source = c.fixture.outputs[0][1][0]
    with pytest.raises(ContractError, match="declaration"):
        c.engine.shadow(program.fingerprint, c.fixture.outputs[0][0], source, 39)
    test_program, rules = program_for(c.fixture, start=70, test=True)
    c.engine.declare(test_program, rules)
    with pytest.raises(ContractError, match="partition"):
        c.engine.shadow(test_program.fingerprint, c.fixture.outputs[0][0], source, 40)


def test_unsupported_context_cannot_be_participant(challenge_case: ChallengeCase) -> None:
    from afre.challenger import ParticipantRole
    from afre.health.artifacts import ModelHealthSnapshot
    from examples.challenge_context import health_context_for

    c = challenge_case
    program, _ = program_for(c.fixture)
    binding = health_context_for(c.repo, c.fixture, program)[0][1]
    snapshot = c.repo.get(ModelHealthSnapshot, binding)
    with pytest.raises(ContractError):
        c.engine.participant(
            "not-a-predictive-model", ParticipantRole.CHALLENGER, snapshot.fingerprint
        )

"""Independent numeric oracles, global support, explicit roles and manual boundaries."""

from dataclasses import replace
from math import erf, exp, log, pi, sqrt
from pathlib import Path
from typing import TypeVar
from unittest.mock import patch

import pytest

from afre.challenger import (
    ChallengeMetric as M,
)
from afre.challenger import (
    ChallengerComparison,
    ChallengeRepository,
    CommonMatchedEvidence,
    CriteriaPolicy,
    ParticipantMetricResult,
    ParticipantRole,
    PromotionAssessment,
    ShadowForecast,
    ShadowMode,
)
from afre.challenger import (
    ChallengeStatus as S,
)
from afre.challenger import (
    PromotionOutcome as P,
)
from afre.research_datasets.schema import Partition
from afre.schema import Artifact, ContractError
from afre.serialization import canonical_json
from afre.statistical_models.evaluation import test_record as native_test_record
from afre.target_engine.definitions import TargetDefinition
from afre.target_engine.models import TargetVintage
from examples.challenger_fixture import evidence_for, program_for
from tests.challenger.conftest import ChallengeCase

A = TypeVar("A", bound=Artifact)


@pytest.mark.parametrize("kind", list(M))
def test_native_numeric_oracles(challenge_case: ChallengeCase, kind: M) -> None:
    c = challenge_case
    program, criteria = program_for(c.fixture, (kind,))
    c.engine.declare(program, criteria)
    evidence = c.engine.evidence(evidence_for(c.repo, c.fixture, program))
    run = c.engine.evaluate(evidence.fingerprint)
    metrics = tuple(c.repo.resolve(ParticipantMetricResult, i) for i in run.metric_ids)
    assert all(m.count == 3 and len(m.truth_ids) == 3 for m in metrics)
    assert len({m.common_id for m in metrics}) == 1
    better_id = c.fixture.participants[1].fingerprint
    better = next(m for m in metrics if m.participant_id == better_id)
    champion = next(m for m in metrics if m.participant_id == program.champion_id)
    if kind in (M.MAE, M.RMSE, M.MSE):
        assert better.value == pytest.approx(0.0, abs=1e-12)
        assert champion.value == pytest.approx(0.01 if kind is M.MSE else 0.1)
    elif kind in (
        M.PEARSON,
        M.SPEARMAN,
        M.R_SQUARED,
        M.SIGN_ACCURACY,
        M.IC,
        M.RANK_IC,
        M.TOP_K_OVERLAP,
    ):
        assert better.value == pytest.approx(1.0)
    elif kind is M.RANK_DISPLACEMENT:
        assert better.value == 0.0
    elif kind is M.NLL:
        assert better.value == pytest.approx(log(0.05 * sqrt(2 * pi)))
        assert champion.value == pytest.approx(log(0.05 * sqrt(2 * pi)) + 2.0)
    elif kind is M.CRPS:
        assert better.value == pytest.approx(0.05 * (sqrt(2) - 1) / sqrt(pi))
        z = 2.0
        expected = 0.05 * (z * erf(z / sqrt(2)) + sqrt(2 / pi) * exp(-z * z / 2) - 1 / sqrt(pi))
        assert champion.value == pytest.approx(expected)
    elif kind is M.BRIER:
        common = c.repo.resolve(CommonMatchedEvidence, run.common_id)
        truths = tuple(c.repo.resolve(TargetVintage, t).value for _, t in common.assignments)
        assert all(y is not None for y in truths)
        expected = (
            sum(
                (0.5 * (1 + erf(float(y) / (0.05 * sqrt(2)))) - 1) ** 2
                for y in truths
                if y is not None
            )
            / 3
        )
        assert better.value == pytest.approx(expected)
    elif kind in (M.COVERAGE, M.SHARPNESS, M.PINBALL):
        assert better.value == pytest.approx(
            1.0 if kind is M.COVERAGE else 0.164485362695147 if kind is M.SHARPNESS else 0.0,
            abs=1e-9,
        )
    else:
        assert better.status is S.INCOMPARABLE
    assert run.action == "MANUAL_ONLY"
    assert len(run.comparison_ids) == 2 and len(run.promotion_ids) == 2
    for identity in run.comparison_ids:
        comparison = c.repo.resolve(ChallengerComparison, identity)
        if comparison.delta is not None and comparison.orientation != "descriptive-only":
            assert comparison.oriented_improvement == pytest.approx(
                comparison.delta
                if comparison.orientation == "higher-is-better"
                else -comparison.delta
            )


def test_independent_eligible_and_losing_challenger(challenge_case: ChallengeCase) -> None:
    c = challenge_case
    program, criteria = program_for(c.fixture)
    c.engine.declare(program, criteria)
    evidence = c.engine.evidence(evidence_for(c.repo, c.fixture, program))
    before = canonical_json(program)
    run = c.engine.evaluate(evidence.fingerprint)
    outcomes = {
        c.repo.resolve(PromotionAssessment, i).challenger_id: c.repo.resolve(
            PromotionAssessment, i
        ).outcome
        for i in run.promotion_ids
    }
    assert outcomes[c.fixture.participants[1].fingerprint] is P.PROMOTION_ELIGIBLE
    assert outcomes[c.fixture.participants[2].fingerprint] is P.PROMOTION_NOT_ELIGIBLE
    assert c.repo.resolve(type(program), program.fingerprint).champion_id == program.champion_id
    assert canonical_json(program) == before
    assert all(
        c.repo.resolve(PromotionAssessment, i).action == "MANUAL_ONLY"
        for i in run.promotion_ids
    )


@pytest.mark.parametrize("minimum", [3, 4])
def test_minimum_support(challenge_case: ChallengeCase, minimum: int) -> None:
    c = challenge_case
    program, criteria = program_for(c.fixture, minimum=minimum)
    c.engine.declare(program, criteria)
    evidence = c.engine.evidence(evidence_for(c.repo, c.fixture, program))
    run = c.engine.evaluate(evidence.fingerprint)
    common = c.repo.resolve(CommonMatchedEvidence, run.common_id)
    assert common.status is (S.AVAILABLE if minimum == 3 else S.INSUFFICIENT_DATA)
    if minimum == 4:
        assert all(
            c.repo.resolve(PromotionAssessment, i).outcome is P.INSUFFICIENT_DATA
            for i in run.promotion_ids
        )


def test_global_matching_never_pairwise(challenge_case: ChallengeCase) -> None:
    c = challenge_case
    program, criteria = program_for(c.fixture)
    c.engine.declare(program, criteria)
    evidence = evidence_for(c.repo, c.fixture, program)
    removed = c.repo.get(ShadowForecast, evidence.shadow_ids[0])
    evidence = c.engine.evidence(replace(evidence, shadow_ids=evidence.shadow_ids[1:]))
    run = c.engine.evaluate(evidence.fingerprint)
    metrics = tuple(c.repo.resolve(ParticipantMetricResult, i) for i in run.metric_ids)
    assert all(m.count == 2 and removed.sample_id not in m.sample_ids for m in metrics)
    assert len({m.sample_ids for m in metrics}) == 1


@pytest.mark.parametrize("field", ["target_id", "horizon_id", "unit"])
def test_declared_mismatch_incomparable(challenge_case: ChallengeCase, field: str) -> None:
    c = challenge_case
    program, criteria = program_for(c.fixture)
    if field == "unit":
        program = replace(program, unit="incompatible")
    elif field == "target_id":
        target = replace(c.repo.get(TargetDefinition, program.target_id), name="target.other")
        c.engine.publish((target,))
        program = replace(program, target_id=target.fingerprint)
    else:
        program = replace(program, horizon_id=program.target_id)
    c.engine.declare(program, criteria)
    evidence = c.engine.evidence(evidence_for(c.repo, c.fixture, program))
    run = c.engine.evaluate(evidence.fingerprint)
    assert c.repo.resolve(CommonMatchedEvidence, run.common_id).status is S.INCOMPARABLE
    assert all(
        c.repo.resolve(PromotionAssessment, i).outcome is P.INCOMPARABLE
        for i in run.promotion_ids
    )


def test_roles_duplicates_and_freeze(challenge_case: ChallengeCase) -> None:
    c = challenge_case
    program, criteria = program_for(c.fixture)
    wrong = c.engine.participant(
        "wrong", ParticipantRole.CHALLENGER, c.fixture.participants[0].reference.artifact_id
    )
    with pytest.raises(ContractError, match="duplicate"):
        c.engine.declare(replace(program, challenger_ids=(wrong.fingerprint,)), criteria)
    with pytest.raises(ContractError, match="roles"):
        c.engine.declare(
            replace(
                program,
                champion_id=c.fixture.participants[1].fingerprint,
                challenger_ids=(c.fixture.participants[2].fingerprint,),
            ),
            criteria,
        )
    with pytest.raises(ContractError):
        replace(program, challenger_ids=())
    with pytest.raises(ContractError):
        replace(program, declared_ns=41)


def test_target_free_before_warm_cache_and_live_clock(challenge_case: ChallengeCase) -> None:
    c = challenge_case
    program, criteria = program_for(c.fixture)
    c.engine.declare(program, criteria)
    evidence = evidence_for(c.repo, c.fixture, program)
    row = c.repo.get(ShadowForecast, evidence.shadow_ids[0])
    sample, truth = evidence.truth_assignments[0]
    get = c.repo.get

    def deny(cls: type[A], identity: str) -> A:
        if cls is TargetVintage:
            raise AssertionError("shadow cannot read any target")
        return get(cls, identity)

    with patch.object(c.repo, "get", deny):
        assert (
            c.engine.shadow(
                program.fingerprint, row.participant_id, row.source_id, row.computed_ns
            )
            == row
        )
    with c.repo.read_snapshot(), c.repo.validation_cache():
        c.repo.resolve(TargetVintage, truth)
        with c.repo.feature_only():
            for method in ("get", "resolve", "get_any"):
                with pytest.raises(ContractError, match="target-free"):
                    if method == "get_any":
                        c.repo.get_any(truth)
                    elif method == "get":
                        c.repo.get(TargetVintage, truth)
                    else:
                        c.repo.resolve(TargetVintage, truth)
    with pytest.raises(ContractError, match="after origin"):
        c.engine.shadow(
            program.fingerprint, row.participant_id, row.source_id, row.origin_ns + 1
        )
    later = replace(program, shadow_mode=ShadowMode.RECONSTRUCTED_NATIVE)
    c.engine.declare(later, criteria)
    reconstructed = c.engine.shadow(later.fingerprint, row.participant_id, row.source_id, 120)
    assert reconstructed.available_ns == reconstructed.computed_ns == 120
    assert reconstructed.source_available_ns == row.origin_ns
    assert sample != reconstructed.fingerprint


def test_late_truth(challenge_case: ChallengeCase) -> None:
    c = challenge_case
    program, criteria = program_for(c.fixture, cutoff=41)
    c.engine.declare(program, criteria)
    evidence = c.engine.evidence(evidence_for(c.repo, c.fixture, program))
    run = c.engine.evaluate(evidence.fingerprint)
    common = c.repo.resolve(CommonMatchedEvidence, run.common_id)
    assert common.assignments == () and common.status is S.INSUFFICIENT_DATA
    assert all("truth-not-known" in reason for _, reason in common.exclusions)


def test_native_test_seal_and_program_isolation(challenge_case: ChallengeCase) -> None:
    c = challenge_case
    program, criteria = program_for(c.fixture, start=70, test=True)
    c.engine.declare(program, criteria)
    evidence = evidence_for(c.repo, c.fixture, program)
    evidence = replace(
        evidence,
        truth_assignments=tuple(
            (s, t)
            for s, t in (
                (s.fingerprint, s.target_id)
                for s in c.repo.partition_samples(
                    program.fold_id,
                    Partition.TEST,
                )
            )
            if t is not None
        ),
    )
    c.engine.evidence(evidence)
    with pytest.raises(ContractError, match="seal"):
        c.engine.evaluate(evidence.fingerprint)
    seal = native_test_record(
        c.repo, program.fold_id, "challenge-test", "frozen-manual-protocol", 120
    )
    c.engine.publish((seal,))
    sealed = c.engine.evidence(replace(evidence, test_evaluation_id=seal.fingerprint))
    before = tuple(canonical_json(x) for x in (program, *criteria))
    run = c.engine.evaluate(sealed.fingerprint)
    assert len(run.metric_ids) == 3
    assert before == tuple(canonical_json(x) for x in (program, *criteria))
    assert c.repo.resolve(CommonMatchedEvidence, run.common_id).assignments


@pytest.mark.parametrize("policy", list(CriteriaPolicy))
def test_threshold_and_multicriteria(
    challenge_case: ChallengeCase, policy: CriteriaPolicy
) -> None:
    c = challenge_case
    program, criteria = program_for(c.fixture, (M.MAE, M.MSE))
    rules = (replace(criteria[0], required_improvement=1.0), criteria[1])
    program = replace(
        program,
        criteria_policy=policy,
        promotion_criterion_ids=tuple(r.fingerprint for r in rules),
    )
    c.engine.declare(program, rules)
    evidence = c.engine.evidence(evidence_for(c.repo, c.fixture, program))
    run = c.engine.evaluate(evidence.fingerprint)
    better = next(
        c.repo.resolve(PromotionAssessment, i)
        for i in run.promotion_ids
        if c.repo.get(PromotionAssessment, i).challenger_id
        == c.fixture.participants[1].fingerprint
    )
    assert better.outcome is (
        P.PROMOTION_ELIGIBLE
        if policy is CriteriaPolicy.ANY_REQUIRED
        else P.PROMOTION_NOT_ELIGIBLE
    )


def test_restart_history_audit(challenge_case: ChallengeCase, tmp_path: Path) -> None:
    c = challenge_case
    program, criteria = program_for(c.fixture)
    c.engine.declare(program, criteria)
    evidence = c.engine.evidence(evidence_for(c.repo, c.fixture, program))
    run = c.engine.evaluate(evidence.fingerprint)
    audit = c.engine.audit(run.fingerprint)
    assert run.fingerprint in audit.node_ids and audit.serialized_bytes > 0
    assert c.engine.history(program.fingerprint) == (run,)
    assert c.engine.evaluate(evidence.fingerprint) == run
    with ChallengeRepository(c.path) as reopened:
        assert canonical_json(reopened.resolve(type(run), run.fingerprint)) == canonical_json(
            run
        )
        assert reopened.resolve(type(audit), audit.fingerprint) == audit
    assert tmp_path.exists()

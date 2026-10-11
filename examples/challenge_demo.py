"""Asserted offline champion/challenger research; every decision remains MANUAL_ONLY."""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from afre.challenger import (
    ChallengeEngine,
    ChallengeRepository,
    CommonMatchedEvidence,
    ParticipantMetricResult,
    ParticipantRole,
    PromotionAssessment,
    PromotionOutcome,
    RollbackAssessment,
    ShadowForecast,
)
from afre.challenger import (
    ChallengeMetric as M,
)
from afre.fusion import FusionArtifact
from afre.health.context import context_records
from afre.invariance.artifacts import EnvironmentMembership
from afre.serialization import canonical_json
from afre.statistical_models.evaluation import test_record as native_test_record
from afre.target_engine.models import TargetVintage
from examples.challenge_context import cost_context_for, health_context_for
from examples.challenge_corrections import source_correction, truth_correction
from examples.challenge_horizons import horizon_challenges
from examples.challenge_native import native_challenge
from examples.challenge_rollback import rollback_challenge
from examples.challenge_selection import evaluate_selected, selected_participants
from examples.challenger_fixture import build_challenge_fixture, evidence_for, program_for
from examples.health_native import build_native, matching_family


def demo(directory: Path) -> tuple[str, ...]:
    messages: list[str] = []

    def step(message: str) -> None:
        messages.append(f"{len(messages) + 1:02d}. {message}")

    path = directory / "challenge.sqlite"
    with ChallengeRepository(path) as repo:
        fixture = build_challenge_fixture(repo)
        engine = ChallengeEngine(repo)
        champion, *challengers = fixture.participants
        assert champion.role is ParticipantRole.CHAMPION
        step("Champion is explicitly designated")
        assert len(challengers) == 2 and all(
            p.role is ParticipantRole.CHALLENGER for p in challengers
        )
        step("Multiple challengers are exact supplied frozen artifacts")
        before_models = tuple(
            canonical_json(repo.get(FusionArtifact, p.reference.producer_id))
            for p in fixture.participants
        )
        program, rules = program_for(
            fixture, (M.MAE, M.MSE, M.RMSE, M.CRPS, M.NLL, M.BRIER, M.IC, M.RANK_IC)
        )
        rules = tuple(
            r
            for r in rules
            if r.request_id == next(q.fingerprint for q in program.requests if q.kind is M.MAE)
        )
        program = replace(program, promotion_criterion_ids=tuple(r.fingerprint for r in rules))
        engine.declare(program, rules)
        assert repo.resolve(type(program), program.fingerprint) == program
        step("ChallengeProgram is immutable and identity-bearing")
        assert program.window.start_ns == 40 and program.window.end_ns == 41
        step("Evaluation window and later truth cutoff are fixed")
        assert program.matching.value == "COMMON_INTERSECTION"
        step("One common matching policy is explicit")
        assert all(r.declared_ns == 0 for r in rules)
        step("Promotion thresholds and directions are predeclared")
        evidence = evidence_for(repo, fixture, program)
        champion_rows = tuple(
            repo.get(ShadowForecast, i)
            for i in evidence.shadow_ids
            if repo.get(ShadowForecast, i).participant_id == champion.fingerprint
        )
        assert len(champion_rows) == 3
        step("Champion shadow records retain exact source/sample/origin")
        assert len(evidence.shadow_ids) == 9
        step("Challengers have separate target-free shadow records")
        row = champion_rows[0]
        with patch.object(repo, "get", wraps=repo.get) as get:
            assert (
                engine.shadow(
                    program.fingerprint, row.participant_id, row.source_id, row.computed_ns
                )
                == row
            )
            assert not any(call.args[0] is TargetVintage for call in get.call_args_list)
        step("Shadow construction and replay cannot read TargetVintage")
        assert all(repo.get(ShadowForecast, i).available_ns <= 40 for i in evidence.shadow_ids)
        step("Live shadow availability cannot precede native receipt/computation")
        engine.evidence(evidence)
        run = engine.evaluate(evidence.fingerprint)
        common = repo.resolve(CommonMatchedEvidence, run.common_id)
        assert len(common.assignments) == 3
        step("Exact later-known native truth is joined explicitly")
        assert (
            len({repo.get(ParticipantMetricResult, i).sample_ids for i in run.metric_ids}) == 1
        )
        step("All participants retain one common sample/truth support")
        assert all(
            repo.get(ParticipantMetricResult, i).value is not None for i in run.metric_ids
        )
        step("Point metrics use exact native score conventions")
        assert any(repo.get(ParticipantMetricResult, i).kind is M.CRPS for i in run.metric_ids)
        step("Native Gaussian laws support exact CRPS/NLL/Brier")
        assert any(
            repo.get(ParticipantMetricResult, i).kind is M.RANK_IC for i in run.metric_ids
        )
        step("Ranking metrics use same-origin common cross-sections")
        assert len(run.comparison_ids) == 16
        step("Each challenger is compared independently against champion")
        assert all(repo.get(ParticipantMetricResult, i).orientation for i in run.metric_ids)
        step("Metric orientation is retained separately from raw deltas")
        outcomes = {
            repo.get(PromotionAssessment, i).challenger_id: repo.get(
                PromotionAssessment, i
            ).outcome
            for i in run.promotion_ids
        }
        assert outcomes[challengers[0].fingerprint] is PromotionOutcome.PROMOTION_ELIGIBLE
        step("A known better challenger is promotion-eligible")
        assert outcomes[challengers[1].fingerprint] is PromotionOutcome.PROMOTION_NOT_ELIGIBLE
        step("A known worse challenger remains ineligible")
        small, small_rules = program_for(fixture, minimum=4)
        engine.declare(small, small_rules)
        small_evidence = engine.evidence(evidence_for(repo, fixture, small))
        small_run = engine.evaluate(small_evidence.fingerprint)
        assert all(
            repo.get(PromotionAssessment, i).outcome is PromotionOutcome.INSUFFICIENT_DATA
            for i in small_run.promotion_ids
        )
        step("Insufficient common support stays explicit")
        mismatch = replace(program, unit="incompatible-unit")
        engine.declare(mismatch, rules)
        mismatch_evidence = engine.evidence(evidence_for(repo, fixture, mismatch))
        mismatch_run = engine.evaluate(mismatch_evidence.fingerprint)
        assert (
            repo.get(CommonMatchedEvidence, mismatch_run.common_id).status.value
            == "INCOMPARABLE"
        )
        step("Incompatible semantics never become a misleading score")
        health = health_context_for(repo, fixture, program)
        health_program = replace(
            program, health_participant_ids=(program.champion_id, *program.challenger_ids)
        )
        engine.declare(health_program, rules)
        health_evidence = engine.evidence(
            replace(evidence_for(repo, fixture, health_program), health_bindings=health)
        )
        assert engine.evaluate(health_evidence.fingerprint).action == "MANUAL_ONLY"
        step("Exact AFRE-22 health context is attached without promotion actions")
        cost_program, cost_rules = program_for(fixture, (M.GROSS_EDGE, M.COST, M.NET_EDGE))
        plan, costs = cost_context_for(repo, fixture, cost_program)
        cost_program = replace(cost_program, cost_plan_id=plan.fingerprint)
        engine.declare(cost_program, cost_rules)
        cost_evidence = engine.evidence(
            replace(evidence_for(repo, fixture, cost_program), cost_bindings=costs)
        )
        cost_run = engine.evaluate(cost_evidence.fingerprint)
        assert all(
            repo.get(ParticipantMetricResult, i).value is not None for i in cost_run.metric_ids
        )
        step("Native AFRE-18 scenarios share exact economic assumptions")
        assert (
            len({repo.get(ParticipantMetricResult, i).kind for i in cost_run.metric_ids}) == 3
        )
        step("Gross, cost and net evidence remain separate")
        assert run.champion_id == champion.fingerprint and run.action == "MANUAL_ONLY"
        step("Eligibility does not promote or replace the champion")
        assert before_models == tuple(
            canonical_json(repo.get(FusionArtifact, p.reference.producer_id))
            for p in fixture.participants
        )
        step("No retraining, recalibration or fusion weight mutation occurs")
        test_program, test_rules = program_for(fixture, start=70, test=True)
        engine.declare(test_program, test_rules)
        seal = native_test_record(
            repo, test_program.fold_id, "demo-seal", "predeclared-challenge-demo", 120
        )
        engine.publish((seal,))
        test_evidence = engine.evidence(
            replace(
                evidence_for(repo, fixture, test_program, seal.fingerprint),
                context_records=context_records(repo, (seal.fingerprint,)),
            )
        )
        test_run = engine.evaluate(test_evidence.fingerprint)
        frozen = tuple(canonical_json(v) for v in (test_program, *test_rules))
        step("Sealed TEST requires exact native fold/sample/cutoff evidence")
        corrected_truth = truth_correction(repo, test_evidence.truth_assignments[0][1])
        assert corrected_truth != test_evidence.truth_assignments[0][1]
        assert frozen == tuple(canonical_json(v) for v in (test_program, *test_rules))
        assert engine.evaluate(test_evidence.fingerprint) == test_run
        step("Perturbing TEST truth cannot redefine frozen program or thresholds")
        assert context_records(repo, (seal.fingerprint,))[0][0] == seal.fingerprint
        step("Native TEST evidence retains exact history context")
        candidate_row = next(
            repo.get(ShadowForecast, i)
            for i in evidence.shadow_ids
            if repo.get(ShadowForecast, i).participant_id == challengers[0].fingerprint
        )
        revised_source = source_correction(repo, candidate_row)
        changed = engine.shadow(
            program.fingerprint,
            candidate_row.participant_id,
            revised_source,
            candidate_row.origin_ns,
        )
        step("A corrected native challenger source creates a new shadow identity")
        corrected = engine.evidence(
            replace(
                evidence,
                shadow_ids=tuple(
                    changed.fingerprint if i == candidate_row.fingerprint else i
                    for i in evidence.shadow_ids
                ),
            )
        )
        new_run = engine.evaluate(corrected.fingerprint)
        assert new_run.fingerprint != run.fingerprint
        step("Changed source evidence creates a new run")
        assert repo.resolve(type(run), run.fingerprint) == run
        step("The original run remains byte-identical after correction")
        assert engine.history(program.fingerprint) == tuple(
            sorted((run, new_run), key=lambda r: (r.cutoff_ns, r.available_ns, r.fingerprint))
        )
        step("Challenge history is append-only and deterministic")
        audit = engine.audit(run.fingerprint)
        assert run.fingerprint in audit.node_ids and audit.serialized_bytes > 0
        step("Bounded audit retains exact native lineage")
    with ChallengeRepository(path) as restarted:
        assert canonical_json(restarted.resolve(type(run), run.fingerprint)) == canonical_json(
            run
        )
        step("Persisted restart reproduces exact canonical bytes")
        assert ChallengeEngine(restarted).evaluate(evidence.fingerprint) == run
        step("Deterministic replay reconstructs the same immutable run")
    with ChallengeRepository(directory / "native.sqlite") as repo:
        native = build_native(repo)
        sources = native.upstream.upstream.upstream
        point, gaussian = (
            matching_family(repo, sources.ids("point")),
            matching_family(repo, sources.ids("gaussian")),
        )
        rollback = rollback_challenge(repo, point, gaussian)
        assessment = repo.get(RollbackAssessment, rollback.rollback_ids[0])
        assert assessment.baseline_metric_id and assessment.current_metric_id
        step("Rollback criterion pins an explicit earlier frozen champion baseline")
        assert assessment.deterioration is not None
        step("Rollback assessment uses explicit deterioration direction and threshold")
        assert assessment.action == rollback.action == "MANUAL_ONLY"
        step("Rollback advice performs no rollback action")
        for kind in ("EVENT", "REGIME", "SECTOR", "UNIVERSE"):
            environment = next(
                d
                for d in native.cohorts.environment_set.definitions
                if d.kind.name == kind
                and (d.membership_kind is None or d.membership_kind.value == "hard")
            )
            members = tuple(
                i
                for i in native.cohorts.membership_ids
                if repo.get(EnvironmentMembership, i).environment_id == environment.fingerprint
            )
            scoped, scoped_evidence = native_challenge(
                repo,
                point,
                gaussian,
                name="demo-" + kind,
                environment_id=environment.fingerprint,
                membership_ids=members,
            )
            e = ChallengeEngine(repo)
            e.evidence(scoped_evidence)
            scoped_run = e.evaluate(scoped_evidence.fingerprint)
            assert repo.get(CommonMatchedEvidence, scoped_run.common_id).assignments
            step("Explicit PIT " + kind.lower() + " cohort scopes the common evidence")
        assert sources.results("gaussian")
        step("Native uncertainty context remains a separate identified artifact")
        horizons = horizon_challenges(repo)
        assert {duration for duration, _ in horizons} == {3600000000000, 86400000000000}
        step("Actual one-hour and one-day programs retain their native horizons")
        assert len({r.program_id for _, r in horizons}) == 2
        step("Hour/day programs have separate immutable identities")
    selection_path = directory / "selection.sqlite"
    a, b, left, right, records = selected_participants(selection_path)
    assert a.role is ParticipantRole.CHAMPION and b.selection_result_id is not None
    step("AFRE-20 selected-model provenance is retained as explicit context")
    assert any(kind == "ResearchTrial" for _, kind, _, _ in records)
    step("AFRE-19 attempted trial history is preserved without significance claims")
    assert any(kind == "HypothesisFamily" for _, kind, _, _ in records)
    step("Native hypothesis-family context is preserved without resetting overfitting history")
    with ChallengeRepository(selection_path) as repo:
        selected_run = evaluate_selected(repo, a, b, left, right, records)
        assert selected_run.action == "MANUAL_ONLY"
        from afre.multiple_testing import TestReuseDiagnostic, TestReuseStatus

        reuse = repo.resolve(
            TestReuseDiagnostic,
            next(i for i, kind, _, _ in records if kind == "TestReuseDiagnostic"),
        )
        assert reuse.use_count == 3 and reuse.status is TestReuseStatus.HEAVILY_REUSED
        step("Selected challenger evaluation preserves native heavily reused TEST history")
    assert len(messages) >= 43
    return tuple(messages)


if __name__ == "__main__":
    with TemporaryDirectory() as directory:
        print("\n".join(demo(Path(directory))))

"""A completed native selection imported after migration, without rerunning model selection."""

from dataclasses import replace
from pathlib import Path

from afre.challenger import (
    ChallengeEngine,
    ChallengeRepository,
    ChallengeRun,
    EvaluationEvidence,
    ParticipantRole,
    ShadowMode,
)
from afre.challenger.participants import ParticipantReference
from afre.health.context import context_records
from afre.multiple_testing import (
    CorrectionMethod,
    DependenceAssumption,
    HypothesisFamily,
    MultipleTestingEngine,
    TestReusePolicy,
)
from afre.research_datasets.samples import ResearchSample
from afre.selection import SelectionEngine, SelectionRepository
from afre.selection.results import CandidateFitResult
from afre.statistical_models import ModelEngine, PredictionScope
from afre.statistical_models.artifacts import PointForecast
from examples.challenger_fixture import ChallengeFixture, program_for
from examples.fusion_fixture import build_fixture
from examples.multiple_testing_fixture import declare_plan
from examples.selection_fixture import small_fixture


def selected_participants(
    path: Path,
) -> tuple[
    ParticipantReference,
    ParticipantReference,
    tuple[str, ...],
    tuple[str, ...],
    tuple[tuple[str, str, int, str], ...],
]:
    with SelectionRepository(path) as prior:
        fixture = small_fixture(prior)
        result, registry = SelectionEngine(prior).select(fixture.space, 100, 100)
        assert result.selected_model_id is not None
        fits = tuple(
            prior.get(CandidateFitResult, r[0])
            for r in prior._connection.execute(
                "SELECT fingerprint FROM sel_artifacts WHERE type_name='CandidateFitResult'"
            )
        )
        other = next(
            f for f in fits if f.model_id is not None and f.model_id != result.selected_model_id
        )
        assert other.model_id is not None
        model = ModelEngine(prior)
        champion = model.predict_samples(
            other.model_id, fixture.space.validation_sample_ids, PredictionScope.VALIDATION
        )
        challenger = model.predict_samples(
            result.selected_model_id,
            fixture.space.validation_sample_ids,
            PredictionScope.VALIDATION,
        )
        test_outputs = model.predict_samples(
            result.selected_model_id, fixture.test_sample_ids, PredictionScope.TEST
        )
        research = MultipleTestingEngine(prior)
        plans = tuple(
            declare_plan(
                prior,
                "challenge-test-use-" + str(j),
                "challenge-prior-test-history",
                5,
                min(p.fingerprint for p in test_outputs),
                tuple(p.fingerprint for p in test_outputs),
            )
            for j in range(3)
        )
        family = research.family(
            HypothesisFamily(
                "challenge-prior-test-history",
                tuple(p.fingerprint for p in plans),
                CorrectionMethod.HOLM,
                0.05,
                DependenceAssumption.ARBITRARY,
                40,
                True,
            )
        )
        trials = tuple(
            research.complete(
                p.fingerprint,
                family.fingerprint,
                100,
                100,
                test_identity="challenge-prior-test-" + str(j),
            )
            for j, p in enumerate(plans)
        )
        policy = research.reuse_policy(TestReusePolicy(3, 40))
        snapshot = research.registry(100, 100)
        reuse = research.test_reuse(
            snapshot.fingerprint, trials[-1].fingerprint, policy.fingerprint, 100
        )
    with ChallengeRepository(path) as repo:
        engine = ChallengeEngine(repo)
        a = engine.participant(
            "explicit-other-champion", ParticipantRole.CHAMPION, other.model_id
        )
        b = engine.participant(
            "explicit-selected-challenger", ParticipantRole.CHALLENGER, result.fingerprint
        )
        records = context_records(
            repo,
            (
                result.fingerprint,
                result.multiple_testing_family_id,
                *(r.trial_id for r in registry.entries),
                family.fingerprint,
                *(t.fingerprint for t in trials),
                reuse.fingerprint,
            ),
        )
        return (
            a,
            b,
            tuple(p.fingerprint for p in champion),
            tuple(p.fingerprint for p in challenger),
            records,
        )


def evaluate_selected(
    repo: ChallengeRepository,
    champion: ParticipantReference,
    challenger: ParticipantReference,
    a: tuple[str, ...],
    b: tuple[str, ...],
    records: tuple[tuple[str, str, int, str], ...],
) -> ChallengeRun:
    fixture = ChallengeFixture(
        build_fixture(repo),
        (champion, challenger),
        ((champion.fingerprint, a), (challenger.fingerprint, b)),
    )
    program, rules = program_for(fixture)
    program = replace(
        program,
        declared_ns=100,
        predeclared=False,
        shadow_mode=ShadowMode.RECONSTRUCTED_NATIVE,
        context_records=records,
    )
    engine = ChallengeEngine(repo)
    engine.declare(program, rules)
    shadows = tuple(
        engine.shadow(program.fingerprint, p.fingerprint, i, 120).fingerprint
        for p, outputs in ((champion, a), (challenger, b))
        for i in outputs
    )
    samples = tuple(repo.get(PointForecast, i).input.sample_id for i in a)
    evidence = engine.evidence(
        EvaluationEvidence(
            program.fingerprint,
            shadows,
            tuple(
                (s.fingerprint, s.target_id)
                for s in (repo.get(ResearchSample, i) for i in samples if i is not None)
                if s.target_id is not None
            ),
            120,
        )
    )
    return engine.evaluate(evidence.fingerprint)

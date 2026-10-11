"""Actual hour/day shadow programs, each pinning its own native target and dataset."""

from dataclasses import replace

from afre.challenger import (
    ChallengeDirection,
    ChallengeEngine,
    ChallengeMetric,
    ChallengeMetricRequest,
    ChallengeProgram,
    ChallengeRepository,
    ChallengeRun,
    ChallengeTestPolicy,
    ChallengeWindow,
    EvaluationEvidence,
    ParticipantRole,
    PromotionCriterion,
)
from afre.fusion import FusedForecast, FusionArtifact, FusionEngine, FusionSpec
from afre.research_datasets.samples import ResearchSample
from examples.fusion_native import horizon_fixture
from examples.regime_horizon_fixture import DAY


def horizon_challenges(repo: ChallengeRepository) -> tuple[tuple[int, ChallengeRun], ...]:
    engine, fusion = ChallengeEngine(repo), FusionEngine(repo)
    results = []
    for duration, identity in horizon_fixture(repo):
        original = repo.get(FusedForecast, identity)
        artifact = repo.get(FusionArtifact, original.artifact_id)
        spec = repo.get(FusionSpec, artifact.spec_id)
        clone = fusion.fit(
            replace(spec, name=spec.name + "-explicit-alternative-version"),
            artifact.fit_cutoff_ns,
            artifact.computed_ns,
            artifact.available_ns,
        )
        challenger_output = fusion.apply(
            clone.fingerprint,
            original.sample_id,
            original.observation_ids,
            original.origin.timestamp_ns,
        )
        champion = engine.participant(
            "actual-champion-" + str(duration), ParticipantRole.CHAMPION, identity
        )
        challenger = engine.participant(
            "actual-challenger-" + str(duration),
            ParticipantRole.CHALLENGER,
            challenger_output.fingerprint,
        )
        at, cutoff = original.origin.timestamp_ns, original.origin.timestamp_ns + DAY + 1
        declaration = max(champion.reference.available_ns, challenger.reference.available_ns)
        request = ChallengeMetricRequest(ChallengeMetric.MAE, 1)
        rule = PromotionCriterion(
            "actual-hour-day-criterion",
            request.fingerprint,
            ChallengeDirection.LOWER,
            0.0,
            1,
            declaration,
        )
        program = ChallengeProgram(
            "actual-program-" + str(duration),
            champion.fingerprint,
            (challenger.fingerprint,),
            original.target_id,
            original.horizon_id,
            original.unit,
            champion.dataset_id,
            champion.fold_id,
            ChallengeWindow(at, at + 1, cutoff),
            1,
            (request,),
            (rule.fingerprint,),
            (),
            ChallengeTestPolicy.VALIDATION_ONLY,
            declaration,
        )
        engine.declare(program, (rule,))
        shadows = tuple(
            engine.shadow(program.fingerprint, p.fingerprint, i, at).fingerprint
            for p, i in ((champion, identity), (challenger, challenger_output.fingerprint))
        )
        sample = repo.get(ResearchSample, original.sample_id)
        assert sample.target_id is not None
        evidence = engine.evidence(
            EvaluationEvidence(
                program.fingerprint, shadows, ((sample.fingerprint, sample.target_id),), cutoff
            )
        )
        results.append((duration, engine.evaluate(evidence.fingerprint)))
    return tuple(results)

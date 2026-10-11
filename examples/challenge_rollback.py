"""An explicit earlier native baseline and a separate retrospective rollback program."""

from dataclasses import replace

from afre.challenger import (
    ChallengeDirection,
    ChallengeEngine,
    ChallengeRepository,
    ChallengeRun,
    ParticipantMetricResult,
    PromotionCriterion,
    RollbackCriterion,
    ShadowForecast,
)
from afre.uncertainty.sources import source_for
from examples.challenge_native import native_challenge, panel_family


def rollback_challenge(
    repo: ChallengeRepository, a: tuple[str, ...], b: tuple[str, ...]
) -> ChallengeRun:
    engine = ChallengeEngine(repo)
    a, b = panel_family(repo, a[0]), panel_family(repo, b[0])
    common_samples = {source_for(repo, i).sample_id for i in a} & {
        source_for(repo, i).sample_id for i in b
    }
    times = sorted(
        {
            source_for(repo, i).origin.timestamp_ns
            for i in a
            if source_for(repo, i).sample_id in common_samples
        }
    )
    assert len(times) >= 2
    first, second = times[:2]
    prior, evidence = native_challenge(
        repo, a, b, start_ns=first, end_ns=first + 1, name="rollback-baseline"
    )
    engine.evidence(evidence)
    old = engine.evaluate(evidence.fingerprint)
    baseline = next(
        repo.resolve(ParticipantMetricResult, i)
        for i in old.metric_ids
        if repo.get(ParticipantMetricResult, i).participant_id == prior.champion_id
    )
    program, new_evidence = native_challenge(
        repo,
        a,
        b,
        start_ns=second,
        end_ns=second + 1,
        name="rollback-current",
        declared_ns=120,
        predeclared=False,
    )
    rule = RollbackCriterion(
        "fixed-earlier-baseline",
        program.requests[0].fingerprint,
        baseline.fingerprint,
        ChallengeDirection.HIGHER,
        0.0,
        1,
        120,
    )
    program = replace(program, rollback_criterion_ids=(rule.fingerprint,))
    engine.declare(
        program,
        tuple(repo.get(PromotionCriterion, i) for i in program.promotion_criterion_ids),
        (rule,),
    )
    shadows = tuple(repo.get(ShadowForecast, i) for i in new_evidence.shadow_ids)
    new_evidence = replace(
        new_evidence,
        program_id=program.fingerprint,
        shadow_ids=tuple(
            engine.shadow(
                program.fingerprint, s.participant_id, s.source_id, s.computed_ns
            ).fingerprint
            for s in shadows
        ),
    )
    engine.evidence(new_evidence)
    return engine.evaluate(new_evidence.fingerprint)

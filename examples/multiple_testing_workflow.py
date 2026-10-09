"""Evaluate only explicitly supplied opportunities; no selection or follow-up generation."""

from afre.multiple_testing import (
    FamilyAnalysis,
    FamilyCompleteness,
    MultipleTestingEngine,
    ResearchTrial,
    TrialState,
)
from examples.multiple_testing_fixture import TestingFixture


def complete_fixture(
    engine: MultipleTestingEngine, f: TestingFixture, reverse: bool = False
) -> tuple[tuple[ResearchTrial, ...], tuple[FamilyAnalysis, ...]]:
    results, cutoffs = dict(f.cost_results), dict(f.cutoffs)
    trials = []
    # TEST reuse chronology is explicit and independent of request insertion order.
    for p in reversed(f.plans) if reverse else f.plans:
        state = (
            TrialState.FAILED
            if p.attempt_key == "failed"
            else TrialState.UNAVAILABLE
            if p.attempt_key == "unavailable"
            else TrialState.COMPLETED
        )
        at = cutoffs.get(p.fingerprint, 100)
        trial = engine.complete(
            p.fingerprint,
            f.family.fingerprint,
            at,
            at,
            state=state,
            native_result_ids=(results[p.fingerprint],) if p.fingerprint in results else (),
            test_identity="frozen-mt-test" if p.attempt_key.startswith("test-") else None,
        )
        trials.append(trial)
    cutoff = max(t.completed_ns for t in trials)
    analyses = engine.analyze(
        f.family.fingerprint,
        tuple(t.fingerprint for t in trials),
        FamilyCompleteness.COMPLETE,
        cutoff,
        cutoff,
    )
    return tuple(sorted(trials, key=lambda t: t.fingerprint)), analyses

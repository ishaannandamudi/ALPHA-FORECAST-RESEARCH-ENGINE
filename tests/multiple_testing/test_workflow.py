"""Native held-out trials retain distinct choices and complete opportunity accounting."""

from afre.multiple_testing import FamilyCompleteness, ResearchTrial, TrialState
from tests.multiple_testing.conftest import TestingCase as MTCase


def test_native_complete_family(mt_case: MTCase) -> None:
    f, e = mt_case.fixture, mt_case.engine
    results = dict(f.cost_results)
    cutoffs = dict(f.cutoffs)
    trials: list[ResearchTrial] = []
    for p in f.plans:
        state = (
            TrialState.FAILED
            if p.attempt_key == "failed"
            else TrialState.UNAVAILABLE
            if p.attempt_key == "unavailable"
            else TrialState.COMPLETED
        )
        trials.append(
            e.complete(
                p.fingerprint,
                f.family.fingerprint,
                cutoffs.get(p.fingerprint, 100),
                cutoffs.get(p.fingerprint, 100),
                state=state,
                native_result_ids=(results[p.fingerprint],) if p.fingerprint in results else (),
                test_identity="frozen-mt-test" if p.attempt_key.startswith("test-") else None,
            )
        )
    cutoff = max(t.completed_ns for t in trials)
    analyses = e.analyze(
        f.family.fingerprint,
        tuple(t.fingerprint for t in trials),
        FamilyCompleteness.COMPLETE,
        cutoff,
        cutoff,
    )
    assert len(analyses) == 4
    assert all(a.family_size == len(f.plans) and a.failed_count == 2 for a in analyses)
    assert {p.native_phase for p in f.plans} == set(range(5, 19))

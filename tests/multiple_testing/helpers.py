"""Pinned test queries: no latest-source or outcome-dependent opportunity rewriting."""

from afre.multiple_testing import (
    FamilyAnalysis,
    HypothesisFamily,
    ResearchTrial,
    TrialSpecification,
)
from tests.multiple_testing.conftest import TestingCase as MTCase


def trial(case: MTCase, key: str) -> ResearchTrial:
    plan = case.fixture.plan(key)
    identity = case.repo._connection.execute(
        "SELECT fingerprint FROM mt_records WHERE kind='ResearchTrial' AND plan_id=?",
        (plan.fingerprint,),
    ).fetchone()[0]
    return case.repo.resolve(ResearchTrial, identity)


def analyses(case: MTCase) -> tuple[FamilyAnalysis, ...]:
    if not case.repo._reading and not case.repo._in_transaction:
        with case.repo.read_snapshot(), case.repo.validation_cache():
            return analyses(case)
    return tuple(
        case.repo.resolve(FamilyAnalysis, i)
        for (i,) in case.repo._connection.execute(
            "SELECT fingerprint FROM mt_records WHERE kind='FamilyAnalysis' "
            "ORDER BY fingerprint"
        )
    )


def completed_cutoff(case: MTCase) -> int:
    return max((100, *dict(case.fixture.cutoffs).values()))


def one_family(case: MTCase, key: str) -> tuple[TrialSpecification, HypothesisFamily]:
    from dataclasses import replace

    p = case.fixture.plan(key)
    family = case.engine.family(replace(case.fixture.family, plan_ids=(p.fingerprint,)))
    return p, family

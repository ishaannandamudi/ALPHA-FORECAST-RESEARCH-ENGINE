"""Replay TEST reuse only from exact registry membership and native seal evidence."""

from collections import Counter
from typing import TYPE_CHECKING

from afre.multiple_testing.hypotheses import HypothesisDefinition
from afre.multiple_testing.registry import TrialRegistrySnapshot
from afre.multiple_testing.schema import TestReuseStatus
from afre.multiple_testing.test_reuse import (
    TestReuseDiagnostic,
    TestReusePolicy,
    classify_reuse,
)
from afre.multiple_testing.trials import ResearchTrial, TrialSpecification
from afre.research_datasets.splits import TestEvaluation
from afre.schema import require

if TYPE_CHECKING:
    from afre.multiple_testing.repository import MultipleTestingRepository


def reuse_scope(repo: "MultipleTestingRepository", trial: ResearchTrial) -> tuple[str, ...]:
    plan = repo.resolve(TrialSpecification, trial.plan_id)
    hypothesis = repo.resolve(HypothesisDefinition, trial.hypothesis_id)
    return (
        plan.dataset_id,
        plan.fold_id,
        hypothesis.target_id,
        hypothesis.horizon_id,
        hypothesis.metric.value,
    )


def reuse_for(
    repo: "MultipleTestingRepository",
    registry_id: str,
    trial_id: str,
    policy_id: str,
    available_ns: int,
) -> TestReuseDiagnostic:
    registry = repo.resolve(TrialRegistrySnapshot, registry_id)
    trial = repo.resolve(ResearchTrial, trial_id)
    policy = repo.resolve(TestReusePolicy, policy_id)
    plan = repo.resolve(TrialSpecification, trial.plan_id)
    require(
        trial_id in registry.trial_ids
        and registry.available_ns <= available_ns
        and policy.declared_ns <= plan.declared_ns,
        "reuse registry/policy chronology",
    )
    scoped = tuple(
        t
        for i in registry.trial_ids
        if isinstance((t := repo.resolve(ResearchTrial, i)), ResearchTrial)
        and t.test_seal_ids
        and reuse_scope(repo, t) == reuse_scope(repo, trial)
    )
    counts = Counter(s for t in scoped for s in t.test_seal_ids)
    all_tracked = {
        s for i in registry.trial_ids for s in repo.resolve(ResearchTrial, i).test_seal_ids
    }
    unknown = tuple(
        i
        for i in registry.native_test_seal_ids
        if repo.resolve(TestEvaluation, i).fold_id == plan.fold_id and i not in all_tracked
    )
    tracked = classify_reuse(
        len(scoped) if trial.test_seal_ids else 0, policy.heavily_reused_count
    )
    status = TestReuseStatus.UNTRACKED if trial.test_seal_ids and unknown else tracked
    return TestReuseDiagnostic(
        registry_id,
        policy_id,
        trial_id,
        tuple(t.fingerprint for t in scoped),
        tuple(counts.items()),
        unknown,
        len(scoped),
        tracked,
        status,
        available_ns,
    )

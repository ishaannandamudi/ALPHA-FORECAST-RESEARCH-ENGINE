"""Target-free planning, fixed TEST family choices, exact sources and explicit attempts."""

from dataclasses import replace
from typing import TypeVar, cast

import pytest

from afre.multiple_testing import (
    AdaptiveTrialStatus,
    FamilyCompleteness,
    HypothesisDefinition,
    MultipleTestingEngine,
    ResearchTrial,
    TrialSpecification,
)
from afre.multiple_testing.sources import source_grid
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.splits import TestEvaluation as NativeSeal
from afre.schema import Artifact, ContractError
from afre.serialization import canonical_json
from afre.target_engine.market_data import TargetBar
from afre.target_engine.models import TargetVintage
from tests.multiple_testing.conftest import TestingCase as MTCase
from tests.multiple_testing.helpers import completed_cutoff, one_family, trial

A = TypeVar("A", bound=Artifact)


def test_target_free_registration(mt_case: MTCase, monkeypatch: pytest.MonkeyPatch) -> None:
    original = mt_case.repo.get
    reads = []

    def guarded(cls: type[A], identity: str) -> A:
        reads.append(cls)
        if cls is TargetVintage:
            raise AssertionError("registration read future target")
        return original(cls, identity)

    monkeypatch.setattr(mt_case.repo, "get", guarded)
    p = mt_case.fixture.plan("phase-5")
    h = mt_case.repo.resolve(HypothesisDefinition, p.hypothesis_id)
    mt_case.engine.hypothesis(h)
    mt_case.engine.plan(p)
    mt_case.engine.family(mt_case.fixture.family)
    assert TargetVintage not in reads


def test_cached_later_truth_and_results_guard(completed_case: MTCase) -> None:
    t = trial(completed_case, "phase-5")
    with completed_case.repo.read_snapshot(), completed_case.repo.validation_cache():
        assert completed_case.repo.resolve(ResearchTrial, t.fingerprint) == t
        truth_id = t.observations[0].truth_id
        completed_case.repo.resolve(TargetVintage, truth_id)
        with completed_case.repo.feature_only():
            for cls, identity in ((ResearchTrial, t.fingerprint), (TargetVintage, truth_id)):
                with pytest.raises(ContractError):
                    completed_case.repo.get_any(identity)
                with pytest.raises(ContractError):
                    completed_case.repo.resolve(cls, identity)


def test_test_truth_correction_keeps_family_and_results(completed_case: MTCase) -> None:
    t = trial(completed_case, "test-0")
    family = completed_case.fixture.family
    before = canonical_json(family), canonical_json(t)
    truth = completed_case.repo.resolve(TargetVintage, t.observations[0].truth_id)
    assert truth.endpoint_bar_id is not None
    bar = completed_case.repo.resolve(TargetBar, truth.endpoint_bar_id)
    with completed_case.repo.transaction():
        completed_case.repo.put(
            replace(bar, close=(bar.close or 0) + 999, predecessor_id=bar.fingerprint)
        )
    assert canonical_json(completed_case.repo.get_any(family.fingerprint)) == before[0]
    assert canonical_json(completed_case.repo.get_any(t.fingerprint)) == before[1]
    assert family.level == 0.05 and len(family.plan_ids) == len(completed_case.fixture.plans)
    with pytest.raises(ContractError):
        completed_case.engine.family(replace(family, declared_ns=100))


@pytest.mark.parametrize(
    "field", ["sample", "phase", "source", "dataset", "environment", "cost", "declared"]
)
def test_incompatible_planning_rejected(mt_case: MTCase, field: str) -> None:
    p = mt_case.fixture.plan("phase-5")
    q = mt_case.fixture.plan("actual-3600000000000")
    changes: dict[str, object] = {"attempt_key": "invalid-" + field}
    if field == "sample":
        changes["sample_ids"] = q.sample_ids
    elif field == "phase":
        changes["native_phase"] = 6
    elif field == "source":
        changes["source_ids"] = mt_case.fixture.plan("phase-6").source_ids
    elif field == "dataset":
        changes["dataset_id"] = q.dataset_id
    elif field == "environment":
        changes["environment_id"] = mt_case.fixture.plan("env-early").environment_id
        changes["membership_ids"] = mt_case.fixture.plan("env-late").membership_ids
    elif field == "cost":
        changes["cost_scenario_id"] = mt_case.fixture.plan("cost-0").cost_scenario_id
    else:
        changes["declared_ns"] = 100
    with pytest.raises(ContractError):
        mt_case.engine.plan(cast(TrialSpecification, replace(cast(Artifact, p), **changes)))


def test_no_implicit_test_assessment(mt_case: MTCase) -> None:
    p, f = one_family(mt_case, "test-0")
    with pytest.raises(ContractError, match="TEST"):
        mt_case.engine.complete(p.fingerprint, f.fingerprint, 100, 100)
    t = mt_case.engine.complete(
        p.fingerprint, f.fingerprint, 100, 100, test_identity="frozen-explicit-test"
    )
    assert t.test_seal_ids
    seal = mt_case.repo.resolve(NativeSeal, t.test_seal_ids[0])
    assert seal.fold_id == p.fold_id and set(p.sample_ids) <= set(seal.sample_ids)


def test_repeated_completion_requires_new_attempt(mt_case: MTCase) -> None:
    p, f = one_family(mt_case, "phase-5")
    t = mt_case.engine.complete(p.fingerprint, f.fingerprint, 100, 100)
    assert mt_case.engine.complete(p.fingerprint, f.fingerprint, 100, 100) == t
    with pytest.raises(ContractError, match="distinct declared attempt"):
        mt_case.engine.complete(p.fingerprint, f.fingerprint, 101, 101)


def test_actual_horizons_and_distinct_environment_cost_choices(mt_case: MTCase) -> None:
    f = mt_case.fixture
    assert (
        f.plan("actual-3600000000000").fingerprint
        != f.plan("actual-86400000000000").fingerprint
    )
    assert f.plan("env-early").fingerprint != f.plan("env-late").fingerprint
    assert f.plan("cost-0").fingerprint != f.plan("cost-1").fingerprint
    p = f.plan("phase-5")
    assert replace(p, choices=(("threshold", "0.1"),)).fingerprint != p.fingerprint
    assert replace(p, preprocessing_ids=(p.dataset_id,)).fingerprint != p.fingerprint
    assert replace(p, model_spec_ids=(p.dataset_id,)).fingerprint != p.fingerprint


def test_exact_pair_intersection_records_exclusions(mt_case: MTCase) -> None:
    p = mt_case.fixture.plan("paired")
    # Remove one right-side sample without changing the exact left-side opportunity set.
    p = mt_case.engine.plan(
        replace(p, attempt_key="partial-pair", right_source_ids=p.right_source_ids[:-1])
    )
    f = mt_case.engine.family(replace(mt_case.fixture.family, plan_ids=(p.fingerprint,)))
    t = mt_case.engine.complete(p.fingerprint, f.fingerprint, 100, 100)
    assert len(t.exclusions) == 1 and len(t.observations) == len(p.sample_ids) - 1
    assert all(o.right_source_id is not None for o in t.observations)
    assert {o.sample_id for o in t.observations} == {
        s.sample_id for s in source_grid(mt_case.repo, p, True)
    }
    for o in t.observations:
        assert o.truth_id == mt_case.repo.resolve(ResearchSample, o.sample_id).target_id


def test_analysis_does_not_promote_prune_or_search(completed_case: MTCase) -> None:
    before = tuple(
        completed_case.repo._connection.execute(
            "SELECT fingerprint FROM mt_records WHERE kind='ResearchTrial' ORDER BY fingerprint"
        )
    )
    models = tuple(
        completed_case.repo._connection.execute(
            "SELECT fingerprint FROM m_artifacts ORDER BY fingerprint"
        )
    )
    trials = tuple(i for (i,) in before)
    cutoff = completed_cutoff(completed_case)
    completed_case.engine.analyze(
        completed_case.fixture.family.fingerprint,
        trials,
        FamilyCompleteness.COMPLETE,
        cutoff,
        cutoff,
    )
    assert (
        tuple(
            completed_case.repo._connection.execute(
                "SELECT fingerprint FROM mt_records WHERE kind='ResearchTrial' "
                "ORDER BY fingerprint"
            )
        )
        == before
    )
    assert (
        tuple(
            completed_case.repo._connection.execute(
                "SELECT fingerprint FROM m_artifacts ORDER BY fingerprint"
            )
        )
        == models
    )
    assert not any(
        hasattr(MultipleTestingEngine, name)
        for name in (
            "select_model",
            "promote",
            "prune",
            "search",
            "optimize",
            "generate_hypotheses",
        )
    )


def test_unsupported_adaptive_parent_unknown_or_future(mt_case: MTCase) -> None:
    p = mt_case.fixture.plan("phase-5")
    with pytest.raises(ContractError, match="parent"):
        mt_case.engine.plan(
            replace(
                p,
                attempt_key="bad-parent",
                declared_ns=110,
                adaptivity=AdaptiveTrialStatus.ADAPTIVE,
                known_trial_ids=(p.fingerprint,),
            )
        )


def test_forecast_cannot_claim_native_residual_semantics(mt_case: MTCase) -> None:
    from afre.multiple_testing import ResearchMetric
    from examples.multiple_testing_fixture import declare_plan

    p = mt_case.fixture.plan("phase-5")
    with pytest.raises(ContractError, match="actual native residual"):
        declare_plan(
            mt_case.repo,
            "false-residual",
            "false-residual-family",
            5,
            p.source_artifact_id,
            p.source_ids,
            metric=ResearchMetric.RESIDUAL_VALUE,
        )

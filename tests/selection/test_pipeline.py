"""Native TRAIN fits, validation-only decision and complete AFRE19 accounting."""

from dataclasses import replace

import pytest

from afre.multiple_testing.families import HypothesisFamily
from afre.multiple_testing.trials import ResearchTrial, TrialSpecification
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.schema import ContractError
from afre.selection import (
    DiscreteDimension,
    SelectionCriterion,
    SelectionEngine,
    SelectionReadRole,
    SelectionStatus,
)
from afre.selection.comparisons import comparison_for
from afre.selection.guards import read_role
from afre.selection.results import CandidateValidationResult
from afre.selection.schema import CandidateStatus
from afre.statistical_models.artifacts import FittedModelArtifact
from afre.statistical_models.definitions import BaselineModelSpec
from afre.statistical_models.schema import ModelFamily, SolverIdentity
from afre.target_engine.models import TargetVintage
from tests.selection.conftest import SelectionCase


@pytest.mark.parametrize(
    "criterion",
    (SelectionCriterion.MIN_MSE, SelectionCriterion.MIN_MAE, SelectionCriterion.MAX_R2),
)
def test_native_metrics_and_winner_oracle(
    case: SelectionCase, criterion: SelectionCriterion
) -> None:
    result, registry = SelectionEngine(case.repository).select(
        replace(case.space, criterion=criterion), 100, 100
    )
    records = tuple(
        case.repository.get(CandidateValidationResult, e.validation_id)
        for e in registry.entries
    )
    for r in records:
        errors = tuple(p.prediction - p.truth for p in r.pairs)
        import math

        expected = (
            math.fsum(e * e for e in errors) / len(errors)
            if criterion is SelectionCriterion.MIN_MSE
            else math.fsum(abs(e) for e in errors) / len(errors)
            if criterion is SelectionCriterion.MIN_MAE
            else 1
            - math.fsum(e * e for e in errors)
            / math.fsum(
                (p.truth - math.fsum(q.truth for q in r.pairs) / len(r.pairs)) ** 2
                for p in r.pairs
            )
        )
        assert r.value == pytest.approx(expected, abs=1e-14)
    expected_winner = sorted(
        records,
        key=lambda r: (
            -r.value if criterion.maximize and r.value is not None else r.value,
            r.candidate_id,
        ),
    )[0].candidate_id
    assert result.selected_candidate_id == expected_winner
    assert result.exhaustive and result.status is SelectionStatus.COMPETITIVE
    assert result.usage.fit_operations_attempted == result.usage.fit_operations_reserved
    assert result.usage.validation_pairs == 6


@pytest.mark.parametrize("role", tuple(SelectionReadRole))
@pytest.mark.parametrize("access", ("get", "resolve", "get_any"))
def test_mandatory_test_truth_guard_before_caches(
    case: SelectionCase, role: SelectionReadRole, access: str
) -> None:
    repo = case.repository
    sample = repo.get(ResearchSample, case.fixture.test_sample_ids[0])
    assert sample.target_id is not None
    with repo.read_snapshot(), repo.validation_cache():
        repo.resolve(TargetVintage, sample.target_id)
        with (
            read_role(repo, role, case.space),
            pytest.raises(ContractError, match="truth|response guard"),
        ):
            if access == "get_any":
                repo.get_any(sample.target_id)
            else:
                getattr(repo, access)(TargetVintage, sample.target_id)


@pytest.mark.parametrize("partition", (Partition.VALIDATION, Partition.TRAIN))
def test_fit_guard_validation_and_planning_target_free(
    case: SelectionCase, partition: Partition
) -> None:
    sample = next(
        s
        for s in case.repository.partition_samples(case.space.fold_id, partition)
        if s.target_id and s.target_definition_id == case.space.target_id
    )
    assert sample.target_id is not None
    role = (
        SelectionReadRole.FIT
        if partition is Partition.VALIDATION
        else SelectionReadRole.PLANNING
    )
    with read_role(case.repository, role, case.space), pytest.raises(ContractError):
        case.repository.resolve(TargetVintage, sample.target_id)


def test_failed_candidate_kept_and_counts_in_full_native_family(case: SelectionCase) -> None:
    recipes = []
    for recipe in case.space.recipes:
        spec = recipe.native_spec
        assert isinstance(spec, BaselineModelSpec)
        if spec.family is ModelFamily.REFERENCE_VALUE:
            spec = replace(
                spec,
                family=ModelFamily.LASSO_REGRESSION,
                solver=SolverIdentity.COORDINATE_DESCENT,
                l1_penalty=0.00001,
                max_iterations=1,
                reference_value=None,
            )
        recipes.append(replace(recipe, native_spec=spec))
    result, registry = SelectionEngine(case.repository).select(
        replace(case.space, recipes=tuple(recipes)), 100, 100
    )
    assert len(registry.entries) == 2
    assert any(
        e.status in (CandidateStatus.FIT_FAILED, CandidateStatus.NUMERICAL_FAILURE)
        for e in registry.entries
    )
    family = case.repository.get(HypothesisFamily, result.multiple_testing_family_id)
    trials = tuple(case.repository.get(ResearchTrial, e.trial_id) for e in registry.entries)
    assert {t.plan_id for t in trials} == set(family.plan_ids)
    for e, t in zip(registry.entries, trials, strict=True):
        plan = case.repository.get(TrialSpecification, t.plan_id)
        assert e.candidate_id in plan.model_spec_ids
        if e.status in (CandidateStatus.FIT_FAILED, CandidateStatus.NUMERICAL_FAILURE):
            assert not t.observations and not t.test_seal_ids
    assert result.status is SelectionStatus.NONCOMPETITIVE


@pytest.mark.parametrize("criterion", (SelectionCriterion.MIN_CRPS, SelectionCriterion.MIN_NLL))
def test_point_incompatible_and_no_fabricated_fallback(
    case: SelectionCase, criterion: SelectionCriterion
) -> None:
    result, registry = SelectionEngine(case.repository).select(
        replace(case.space, criterion=criterion), 100, 100
    )
    assert result.status is SelectionStatus.NO_VALID_CANDIDATE
    assert result.selected_candidate_id is None and result.selected_model_id is None
    assert all(e.status is CandidateStatus.INCOMPATIBLE for e in registry.entries)
    assert all(
        case.repository.get(ResearchTrial, e.trial_id).observations for e in registry.entries
    )


def test_explicit_minimum_support_no_valid(case: SelectionCase) -> None:
    result, registry = SelectionEngine(case.repository).select(
        replace(case.space, minimum_support=4), 100, 100
    )
    assert result.status is SelectionStatus.NO_VALID_CANDIDATE
    assert all(e.status is CandidateStatus.INSUFFICIENT_DATA for e in registry.entries)


def test_single_valid_protocol_and_native_tie(case: SelectionCase) -> None:
    recipe = case.space.recipes[0]
    one = replace(
        case.space,
        dimensions=(DiscreteDimension("one", ("one",)),),
        recipes=(replace(recipe, choices=(("one", "one"),)),),
        permit_single_valid=False,
    )
    result, _ = SelectionEngine(case.repository).select(one, 100, 100)
    assert result.status is SelectionStatus.NO_VALID_CANDIDATE
    result, _ = SelectionEngine(case.repository).select(
        replace(one, permit_single_valid=True), 100, 100
    )
    assert result.status is SelectionStatus.NONCOMPETITIVE
    spec = recipe.native_spec
    assert isinstance(spec, BaselineModelSpec)
    tied = replace(
        case.space,
        dimensions=(DiscreteDimension("seed", ("0", "1")),),
        recipes=tuple(
            replace(
                recipe, native_spec=replace(spec, random_seed=n), choices=(("seed", str(n)),)
            )
            for n in (0, 1)
        ),
    )
    tie_result, tie_registry = SelectionEngine(case.repository).select(tied, 100, 100)
    values = tuple(
        case.repository.get(CandidateValidationResult, e.validation_id).value
        for e in tie_registry.entries
    )
    assert values[0] == values[1]
    assert tie_result.selected_candidate_id == min(e.candidate_id for e in tie_registry.entries)


def test_comparison_exact_intersection_b_minus_a(case: SelectionCase) -> None:
    repo = case.repository
    with repo.read_snapshot(), repo.validation_cache():
        a, b = case.registry.entries
        comparison = comparison_for(repo, a.validation_id, b.validation_id, 2)
        av = repo.get(CandidateValidationResult, a.validation_id)
        bv = repo.get(CandidateValidationResult, b.validation_id)
        assert av.value is not None and bv.value is not None
        assert comparison.delta_b_minus_a == pytest.approx(bv.value - av.value)
        unavailable = comparison_for(repo, a.validation_id, b.validation_id, 4)
        assert unavailable.delta_b_minus_a is None
    with repo.transaction():
        repo.put(comparison)
        repo.put(unavailable)
    assert repo.resolve(type(comparison), comparison.fingerprint) == comparison


def test_exact_native_selection_event_full_pool(case: SelectionCase) -> None:
    from afre.multiple_testing.selection_bias import SelectionEvent
    from afre.statistical_models.artifacts import PointForecast

    sample = case.space.validation_sample_ids[0]
    space = replace(
        case.space,
        validation_sample_ids=(sample,),
        minimum_support=1,
        failure_anchor_source_ids=tuple(
            i
            for i in case.space.failure_anchor_source_ids
            if case.repository.get(PointForecast, i).input.sample_id == sample
        ),
    )
    result, registry = SelectionEngine(case.repository).select(space, 100, 100)
    assert result.multiple_testing_event_id is not None
    event = case.repository.get(SelectionEvent, result.multiple_testing_event_id)
    assert set(event.candidate_trial_ids) == {e.trial_id for e in registry.entries}
    assert event.selected_trial_ids == (
        next(
            e.trial_id
            for e in registry.entries
            if e.candidate_id == result.selected_candidate_id
        ),
    )
    assert not event.test_involved


def test_validation_source_correction_new_identity_old_unchanged(case: SelectionCase) -> None:
    from examples.selection_corrections import corrected_validation_space

    old = case.repository.resolve(type(case.result), case.result.fingerprint)
    new = corrected_validation_space(case.repository, case.space)
    result, registry = SelectionEngine(case.repository).select(new, 100, 100)
    assert result.fingerprint != old.fingerprint
    assert result.search_space_id != old.search_space_id
    assert old.selected_model_id is not None and result.selected_model_id is not None
    old_fit = case.repository.get(FittedModelArtifact, old.selected_model_id)
    new_fit = case.repository.get(FittedModelArtifact, result.selected_model_id)
    assert (
        case.repository.get(BaselineModelSpec, old_fit.spec_id).family
        is not case.repository.get(BaselineModelSpec, new_fit.spec_id).family
    )
    assert case.repository.resolve(type(old), old.fingerprint) == old
    assert all(e.status is CandidateStatus.VALID for e in registry.entries)


@pytest.mark.parametrize("role", tuple(SelectionReadRole))
@pytest.mark.parametrize("access", ("get", "resolve", "get_any"))
def test_stored_test_evaluation_guard_before_cache(
    case: SelectionCase, role: SelectionReadRole, access: str
) -> None:
    from afre.statistical_models import ModelEngine, PredictionScope

    repo = case.repository
    assert case.result.selected_model_id is not None
    engine = ModelEngine(repo)
    forecasts = engine.predict_samples(
        case.result.selected_model_id, case.fixture.test_sample_ids, PredictionScope.TEST
    )
    evaluation = engine.evaluate(
        tuple(p.fingerprint for p in forecasts), 100, 100, "selection-guard-test-seal"
    )
    with repo.read_snapshot(), repo.validation_cache():
        repo.resolve(type(evaluation), evaluation.fingerprint)
        with (
            read_role(repo, role, case.space),
            pytest.raises(ContractError, match="held-out evaluation"),
        ):
            if access == "get_any":
                repo.get_any(evaluation.fingerprint)
            else:
                getattr(repo, access)(type(evaluation), evaluation.fingerprint)

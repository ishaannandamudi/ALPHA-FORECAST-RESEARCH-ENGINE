"""Fail-closed selection graph validation, exact frozen validation/decision replay."""

from dataclasses import replace
from typing import TYPE_CHECKING

from afre.multiple_testing.families import HypothesisFamily
from afre.multiple_testing.trials import ResearchTrial, TrialSpecification
from afre.research_datasets.splits import FoldDefinition
from afre.schema import Artifact, require
from afre.selection.decisions import ordering_for, winner_for
from afre.selection.definitions import (
    CandidateFamilyPlan,
    CandidateSpec,
    NativeCandidateRecipe,
    SearchSpace,
    SelectionRequest,
)
from afre.selection.enumeration import enumerate_candidates
from afre.selection.guards import read_role
from afre.selection.registry import CandidateRegistrySnapshot
from afre.selection.results import (
    CandidateFitResult,
    CandidateValidationResult,
    SelectionResult,
)
from afre.selection.schema import CandidateStatus, SelectionReadRole
from afre.selection.scoring import score_candidate
from afre.serialization import canonical_json

if TYPE_CHECKING:
    from afre.selection.repository import SelectionRepository


def validate_selection(repo: "SelectionRepository", value: Artifact) -> None:
    if isinstance(value, SearchSpace):
        fold = repo.get(FoldDefinition, value.fold_id)
        require(
            fold.dataset_id == value.dataset_id
            and value.declared_ns <= fold.training_cutoff_ns,
            "selection exact predeclared fold",
        )
        require(
            len(value.recipes) <= repo.selection_bounds.candidates
            and len(value.dimensions) <= repo.selection_bounds.dimensions
            and len(value.validation_sample_ids) <= repo.selection_bounds.rows,
            "selection configured space bound",
        )
    elif isinstance(value, NativeCandidateRecipe):
        require(value.native_phase in (5, 6, 10, 11, 13, 14), "native recipe family")
    elif isinstance(value, CandidateSpec):
        space = repo.resolve(SearchSpace, value.search_space_id)
        require(value in enumerate_candidates(space), "candidate exact Cartesian parent")
    elif isinstance(value, SelectionRequest):
        space = repo.resolve(SearchSpace, value.search_space_id)
        require(space.declared_ns <= value.truth_cutoff_ns, "declared selection request")
    elif isinstance(value, CandidateFamilyPlan):
        request = repo.resolve(SelectionRequest, value.request_id)
        require(request.search_space_id == value.search_space_id, "planned exact request")
        space = repo.resolve(SearchSpace, value.search_space_id)
        require(
            value.candidate_ids == tuple(c.fingerprint for c in enumerate_candidates(space))
            and value.declared_ns == space.declared_ns,
            "complete planned candidate family",
        )
    elif isinstance(value, CandidateFitResult):
        candidate = repo.resolve(CandidateSpec, value.candidate_id)
        space = repo.resolve(SearchSpace, candidate.search_space_id)
        from afre.selection.fitting import fit_operations

        require(
            value.fit_operations_attempted <= fit_operations(candidate.recipe), "fit work bound"
        )
        if value.status is CandidateStatus.VALID:
            assert value.model_id is not None
            with read_role(repo, SelectionReadRole.FIT, space):
                native_model = repo.get_any(value.model_id)
                require(
                    getattr(native_model, "spec_id", None)
                    == candidate.recipe.native_spec.fingerprint,
                    "fit exact native spec",
                )
            with read_role(repo, SelectionReadRole.VALIDATION, space):
                from afre.uncertainty.sources import source_for

                sources = tuple(source_for(repo, i) for i in value.forecast_ids)
                require(
                    {s.sample_id for s in sources} == set(space.validation_sample_ids)
                    and all(
                        s.partition.value == "validation"
                        and s.fold_id == space.fold_id
                        and s.target.fingerprint == space.target_id
                        for s in sources
                    ),
                    "fit exact VALIDATION sources",
                )
    elif isinstance(value, CandidateValidationResult):
        candidate = repo.resolve(CandidateSpec, value.candidate_id)
        space = repo.resolve(SearchSpace, candidate.search_space_id)
        fit = repo.resolve(CandidateFitResult, value.fit_id)
        with read_role(repo, SelectionReadRole.VALIDATION, space):
            trial = repo.resolve(ResearchTrial, value.trial_id)
            plan = repo.resolve(TrialSpecification, trial.plan_id)
            require(
                candidate.fingerprint in plan.model_spec_ids and not trial.test_seal_ids,
                "candidate exact native trial/no TEST",
            )
            expected_validation = score_candidate(
                repo,
                space,
                fit,
                value.trial_id,
                value.truth_cutoff_ns,
                value.available_ns,
                value.pairs,
            )
        require(value == expected_validation, "selection validation semantic replay mismatch")
    elif isinstance(value, SelectionResult):
        space = repo.resolve(SearchSpace, value.search_space_id)
        planned = repo.resolve(CandidateFamilyPlan, value.family_plan_id)
        request = repo.resolve(SelectionRequest, value.request_id)
        require(
            planned.request_id == value.request_id
            and request
            == SelectionRequest(
                value.search_space_id, value.selection_cutoff_ns, value.available_ns
            ),
            "selection frozen request",
        )
        require(
            value.candidate_ids == planned.candidate_ids and value.criterion is space.criterion,
            "selection full predeclared roster/criterion",
        )
        results = tuple(
            repo.resolve(CandidateValidationResult, i) for i in value.validation_ids
        )
        require(
            {r.candidate_id for r in results} == set(value.candidate_ids)
            and all(
                r.truth_cutoff_ns == value.selection_cutoff_ns
                and r.available_ns <= value.available_ns
                for r in results
            ),
            "selection exact validation records/clocks",
        )
        winner, status = winner_for(space, results)
        require(
            value.ordering == ordering_for(space, results)
            and (value.selected_candidate_id, value.status) == (winner, status),
            "selection canonical decision replay",
        )
        fits = tuple(repo.resolve(CandidateFitResult, r.fit_id) for r in results)
        model = next((f.model_id for f in fits if f.candidate_id == winner), None)
        require(value.selected_model_id == model, "selected immutable TRAIN model")
        with read_role(repo, SelectionReadRole.VALIDATION, space):
            family = repo.resolve(HypothesisFamily, value.multiple_testing_family_id)
            trials = tuple(repo.resolve(ResearchTrial, r.trial_id) for r in results)
            require(
                {t.plan_id for t in trials} == set(family.plan_ids),
                "all inspected candidate trials in exact native family",
            )
            from afre.selection.accounting import exact_native_event

            expected = exact_native_event(
                repo,
                space,
                results,
                value.ordering,
                winner,
                value.selection_cutoff_ns,
                value.available_ns,
            )
        require(
            value.multiple_testing_event_id == (expected.fingerprint if expected else None),
            "selection native event replay",
        )
        from afre.selection.admission import admit

        with read_role(repo, SelectionReadRole.PLANNING, space):
            reserved = admit(repo, space)
        measured = replace(
            reserved,
            fit_operations_attempted=sum(f.fit_operations_attempted for f in fits),
            fitted_candidates=sum(f.status is CandidateStatus.VALID for f in fits),
            validation_pairs=sum(len(r.pairs) for r in results),
            payload_bytes=reserved.payload_bytes
            + sum(len(canonical_json(r).encode()) for r in (*fits, *results)),
        )
        require(value.usage == measured, "selection measured usage replay")
        require(measured.payload_bytes <= space.budget.max_payload_bytes, "payload budget")
    elif isinstance(value, CandidateRegistrySnapshot):
        result = repo.resolve(SelectionResult, value.selection_id)
        require(
            value.search_space_id == result.search_space_id
            and {e.candidate_id for e in value.entries} == set(result.candidate_ids)
            and value.completion_cutoff_ns == result.available_ns,
            "registry exact complete search",
        )
        for entry in value.entries:
            record = repo.resolve(CandidateValidationResult, entry.validation_id)
            fit = repo.resolve(CandidateFitResult, entry.fit_id)
            require(
                (entry.candidate_id, entry.fit_id, entry.trial_id, entry.status, entry.model_id)
                == (
                    record.candidate_id,
                    record.fit_id,
                    record.trial_id,
                    record.status,
                    fit.model_id,
                ),
                "registry exact candidate witness",
            )
    else:
        from afre.selection.comparisons import CandidateComparison, comparison_for
        from afre.selection.lineage import SelectionAudit, audit_for
        from afre.selection.orthogonal_features import (
            OrthogonalFeatureBinding,
            validate_binding,
        )

        if isinstance(value, OrthogonalFeatureBinding):
            validate_binding(repo, value)
        elif isinstance(value, SelectionAudit):
            require(value == audit_for(repo, value.root_id), "selection audit replay")
        elif isinstance(value, CandidateComparison):
            require(
                value
                == comparison_for(
                    repo,
                    value.left_validation_id,
                    value.right_validation_id,
                    value.minimum_support,
                ),
                "selection comparison replay",
            )

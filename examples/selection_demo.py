"""Thirty-five verified offline steps through the declared AFRE20 selection boundary."""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from afre.multiple_testing.families import HypothesisFamily
from afre.multiple_testing.selection_bias import SelectionEvent
from afre.multiple_testing.trials import ResearchTrial
from afre.research_datasets.samples import ResearchSample
from afre.schema import ContractError
from afre.selection import (
    CandidateStatus,
    DiscreteDimension,
    SelectionCriterion,
    SelectionEngine,
    SelectionReadRole,
    SelectionRepository,
    SelectionStatus,
    enumerate_candidates,
)
from afre.selection.guards import read_role
from afre.selection.registry import CandidateRegistrySnapshot
from afre.selection.results import CandidateValidationResult, SelectionResult
from afre.serialization import canonical_json
from afre.statistical_models.artifacts import FittedModelArtifact, ModelFitInputs, PointForecast
from afre.statistical_models.definitions import BaselineModelSpec
from afre.statistical_models.schema import ModelFamily, SolverIdentity
from afre.target_engine.market_data import TargetBar
from afre.target_engine.models import TargetVintage
from examples.regime_horizon_fixture import DAY, HOUR
from examples.selection_corrections import corrected_validation_space
from examples.selection_fixture import family_fixture, small_fixture
from examples.selection_horizons import horizon_spaces
from examples.selection_orthogonal_fixture import orthogonal_space


def demo(directory: Path) -> tuple[str, ...]:
    messages: list[str] = []

    def step(number: int, message: str) -> None:
        assert number == len(messages) + 1
        messages.append(f"{number:02d}. {message}")

    path = directory / "selection.sqlite"
    with SelectionRepository(path) as repo:
        fixture = small_fixture(repo)
        space = fixture.space
        step(1, "Discrete SearchSpace declared with a native recipe for each combination")
        assert space.budget.max_candidates >= len(space.recipes)
        step(2, "ResourceBudget reserves the complete exhaustive grid")
        candidates = enumerate_candidates(space)
        assert tuple(c.fingerprint for c in candidates) == tuple(
            sorted(c.fingerprint for c in candidates)
        )
        step(3, "Candidate enumeration uses canonical fingerprints")
        engine = SelectionEngine(repo)
        result, registry = engine.select(space, 100, 100)
        family = repo.get(HypothesisFamily, result.multiple_testing_family_id)
        trials = tuple(repo.get(ResearchTrial, e.trial_id) for e in registry.entries)
        assert {t.plan_id for t in trials} == set(family.plan_ids)
        step(4, "Every candidate has an AFRE-19 plan and completed attempt")
        assert result.selected_model_id is not None
        fitted = repo.get(FittedModelArtifact, result.selected_model_id)
        inputs = repo.get(ModelFitInputs, fitted.fit_inputs_id)
        assert inputs.training_cutoff_ns == repo.resolve_fold(space.fold_id).training_cutoff_ns
        step(5, "Selected native model is fitted at the TRAIN cutoff")
        assert all(r.preprocessing_ids for r in space.recipes)
        step(6, "TRAIN preprocessing identities are frozen in candidate recipes")
        records = tuple(
            repo.get(CandidateValidationResult, e.validation_id) for e in registry.entries
        )
        assert all(r.status is CandidateStatus.VALID for r in records)
        step(7, "Exact VALIDATION sample/truth pairs determine criterion values")
        sample = repo.get(ResearchSample, fixture.test_sample_ids[0])
        assert sample.target_id is not None
        try:
            with read_role(repo, SelectionReadRole.FIT, space):
                repo.get(TargetVintage, sample.target_id)
        except ContractError:
            step(8, "TEST truth read is rejected before fitting can access it")
        else:
            raise AssertionError("TEST guard did not reject")
        assert result.criterion is SelectionCriterion.MIN_MSE
        step(9, "MIN_MSE selects an immutable TRAIN-fitted candidate")
        mae, _ = engine.select(replace(space, criterion=SelectionCriterion.MIN_MAE), 100, 100)
        assert mae.selected_candidate_id is not None
        step(10, "MIN_MAE uses a separate declared criterion identity")
        recipe = space.recipes[0]
        spec = recipe.native_spec
        assert isinstance(spec, BaselineModelSpec)
        tied = replace(
            space,
            dimensions=(DiscreteDimension("seed", ("0", "1")),),
            recipes=tuple(
                replace(
                    recipe,
                    native_spec=replace(spec, random_seed=n),
                    choices=(("seed", str(n)),),
                )
                for n in (0, 1)
            ),
        )
        tie, tied_registry = engine.select(tied, 100, 100)
        assert tie.selected_candidate_id == min(e.candidate_id for e in tied_registry.entries)
        step(11, "Equal native forecasts select the canonical candidate fingerprint")
        failed_recipes = []
        for r in space.recipes:
            native = r.native_spec
            assert isinstance(native, BaselineModelSpec)
            if native.family is ModelFamily.REFERENCE_VALUE:
                native = replace(
                    native,
                    family=ModelFamily.LASSO_REGRESSION,
                    solver=SolverIdentity.COORDINATE_DESCENT,
                    l1_penalty=0.00001,
                    max_iterations=1,
                    reference_value=None,
                )
            failed_recipes.append(replace(r, native_spec=native))
        _, failed = engine.select(replace(space, recipes=tuple(failed_recipes)), 100, 100)
        assert any(e.status is not CandidateStatus.VALID for e in failed.entries)
        step(12, "Actual native nonconvergence remains in the complete trial registry")
        no_valid, incompatible = engine.select(
            replace(space, criterion=SelectionCriterion.MIN_CRPS), 100, 100
        )
        assert all(e.status is CandidateStatus.INCOMPATIBLE for e in incompatible.entries)
        step(13, "Point-only candidates remain explicitly incompatible with CRPS")
        assert no_valid.status is SelectionStatus.NO_VALID_CANDIDATE
        step(14, "No compatible candidate produces NO_VALID_CANDIDATE")
        one = replace(
            space,
            dimensions=(DiscreteDimension("one", ("one",)),),
            recipes=(replace(recipe, choices=(("one", "one"),)),),
            permit_single_valid=True,
        )
        single, _ = engine.select(one, 100, 100)
        assert single.status is SelectionStatus.NONCOMPETITIVE
        step(15, "Explicit single-valid protocol is NONCOMPETITIVE")
        comparison = engine.compare(records[0].fingerprint, records[1].fingerprint)
        assert comparison.delta_b_minus_a is not None
        step(16, "Matched comparison reports descriptive B-minus-A metric delta")
        assert len(trials) == len(candidates)
        step(17, "Full AFRE-19 opportunity denominator includes the complete candidate pool")
        exact_sample = space.validation_sample_ids[0]
        exact, exact_registry = engine.select(
            replace(
                space,
                validation_sample_ids=(exact_sample,),
                minimum_support=1,
                failure_anchor_source_ids=tuple(
                    i
                    for i in space.failure_anchor_source_ids
                    if repo.get(PointForecast, i).input.sample_id == exact_sample
                ),
            ),
            100,
            100,
        )
        assert result.multiple_testing_event_id is None
        assert exact.multiple_testing_event_id is not None
        event = repo.get(SelectionEvent, exact.multiple_testing_event_id)
        assert set(event.candidate_trial_ids) == {e.trial_id for e in exact_registry.entries}
        step(
            18, "Native SelectionEvent exists only where mean/median and ordering match exactly"
        )
        with SelectionRepository(directory / "families.sqlite") as families:
            native_fixture = family_fixture(families)
            _, native_registry = SelectionEngine(families).select(
                native_fixture.space, 100, 100
            )
            assert all(e.status is CandidateStatus.VALID for e in native_registry.entries)
            phases = {r.native_phase for r in native_fixture.space.recipes}
            for number, phase, name in (
                (19, 10, "event"),
                (20, 11, "regime"),
                (21, 13, "nonlinear"),
                (22, 14, "sequence"),
            ):
                assert phase in phases
                step(number, f"Native {name} candidate fits and forecasts VALIDATION")
        residual = orthogonal_space(repo, space)
        _, residual_registry = engine.select(residual, 100, 100)
        assert all(e.status is CandidateStatus.VALID for e in residual_registry.entries)
        assert all(r.orthogonal_feature_ids for r in residual.recipes)
        step(
            23, "Declared causal AFRE-16 residual feature enters a later fold without TEST rows"
        )
        step(
            24,
            "AFRE-18 cost criterion is explicitly deferred; no portfolio or net-edge optimizer",
        )
        with SelectionRepository(directory / "horizons.sqlite") as horizon_repo:
            by_duration = {}
            for hspace, cutoff in horizon_spaces(horizon_repo):
                hresult, _ = SelectionEngine(horizon_repo).select(hspace, cutoff, cutoff)
                hspec = hspace.recipes[0].native_spec
                assert isinstance(hspec, BaselineModelSpec)
                by_duration[hspec.target.horizon.duration_ns] = hresult
            assert by_duration[HOUR].selected_candidate_id is not None
            step(25, "Actual one-hour native target has an independent search")
            assert by_duration[DAY].selected_candidate_id is not None
            step(26, "Actual one-day native target has an independent search")
            assert by_duration[HOUR].search_space_id != by_duration[DAY].search_space_id
            step(27, "Hour/day search and candidate identities remain distinct")
        with SelectionRepository(path) as writer:

            def correction() -> None:
                identity = writer._connection.execute(
                    "SELECT fingerprint FROM target_bars WHERE end_ns=80 LIMIT 1"
                ).fetchone()[0]
                bar = writer.get(TargetBar, identity)
                assert bar.close is not None
                with writer.transaction():
                    writer.put(replace(bar, close=bar.close + 10, predecessor_id=identity))

            replay, _ = engine.select(space, 100, 100, snapshot_hook=correction)
        assert replay == result
        step(28, "Real second-writer TEST source correction leaves frozen selection unchanged")
        corrected = corrected_validation_space(repo, space)
        changed, _ = engine.select(corrected, 100, 100)
        assert changed.fingerprint != result.fingerprint
        step(29, "VALIDATION source/label revision creates a new selection result")
        assert set(changed.candidate_ids).isdisjoint(result.candidate_ids)
        step(30, "Corrected source context produces new candidate identities")
        assert repo.resolve(SelectionResult, result.fingerprint) == result
        step(31, "Earlier selection remains immutable and replays its original truth IDs")
        assert repo.resolve(CandidateRegistrySnapshot, registry.fingerprint) == registry
        step(32, "Complete immutable candidate registry snapshot persists")
        semantic = canonical_json(result)
        with SelectionRepository(path) as restarted:
            assert (
                canonical_json(restarted.resolve(SelectionResult, result.fingerprint))
                == semantic
            )
        step(33, "Restart resolves the same persisted result bytes")
        replay, _ = engine.select(space, 100, 100)
        assert canonical_json(replay) == semantic
        step(34, "Deterministic replay reproduces the exact semantic artifact")
        audit = engine.audit(result.fingerprint)
        assert set(result.candidate_ids) <= set(audit.node_ids)
        step(35, f"Bounded lineage audit covers {len(audit.node_ids)} nodes")
    return tuple(messages)


def main() -> None:
    with TemporaryDirectory(prefix="afre-selection-demo-") as directory:
        print("\n".join(demo(Path(directory))))


if __name__ == "__main__":
    main()

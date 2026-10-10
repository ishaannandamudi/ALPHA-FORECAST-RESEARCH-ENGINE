"""Native TRAIN fits and target-free VALIDATION predictions; no final refit."""

from dataclasses import replace
from typing import TYPE_CHECKING

from afre.event_conditioned.artifacts import EventConditionedObservation
from afre.event_conditioned.definitions import EventConditioningSpec
from afre.event_conditioned.engine import EventEngine
from afre.nonlinear.definitions import NonlinearModelSpec
from afre.nonlinear.engine import NonlinearEngine
from afre.nonlinear.schema import KnotPolicy
from afre.probabilistic.definitions import ProbabilisticModelSpec
from afre.probabilistic.engine import ProbabilisticEngine
from afre.regime_conditioned.artifacts import RegimeConditionedSample
from afre.regime_conditioned.definitions import RegimeConditioningSpec
from afre.regime_conditioned.engine import RegimeEngine
from afre.research_datasets.engine import DatasetEngine
from afre.research_datasets.preprocessing import FoldPreprocessingState
from afre.research_datasets.samples import ResearchSample
from afre.schema import ContractError
from afre.selection.definitions import CandidateSpec, NativeCandidateRecipe, SearchSpace
from afre.selection.results import CandidateFitResult
from afre.selection.schema import CandidateStatus
from afre.sequence.definitions import SequenceModelSpec
from afre.sequence.engine import SequenceEngine
from afre.statistical_models.definitions import BaselineModelSpec
from afre.statistical_models.engine import ModelEngine
from afre.statistical_models.schema import PredictionScope

if TYPE_CHECKING:
    from afre.selection.repository import SelectionRepository


def fit_operations(recipe: NativeCandidateRecipe) -> int:
    spec = recipe.native_spec
    if isinstance(spec, SequenceModelSpec):
        return 2
    if isinstance(spec, NonlinearModelSpec):
        return 1 + sum(
            d.parameters.knot_policy is KnotPolicy.TRAIN_QUANTILES
            for d in spec.interaction_set.definitions
        )
    return 1 + (len(spec.preprocessing_state_ids) if isinstance(spec, BaselineModelSpec) else 0)


def fit_candidate(
    repo: "SelectionRepository", space: SearchSpace, candidate: CandidateSpec, cutoff_ns: int
) -> CandidateFitResult:
    recipe = candidate.recipe
    spec = recipe.native_spec
    at = repo.resolve_fold(space.fold_id).training_cutoff_ns
    operations = 0
    states: tuple[str, ...] = ()
    model_id: str | None = None
    ids: tuple[str, ...] = ()
    try:
        if isinstance(spec, BaselineModelSpec):
            # Refitting the identical native TRAIN-only preprocessing spec is
            # idempotent, and proves that no VALIDATION normalization is fitted.
            fitted = []
            for identity in spec.preprocessing_state_ids:
                old = repo.resolve(FoldPreprocessingState, identity)
                operations += 1
                fitted.append(
                    DatasetEngine(repo)
                    .fit_preprocessing(space.fold_id, old.spec, at)
                    .fingerprint
                )
            states = tuple(sorted(fitted))
            native = replace(spec, preprocessing_state_ids=states)
            operations += 1
            engine = ModelEngine(repo)
            model_id = engine.fit_model(native, at, at, at).artifact_id
            ids = tuple(
                p.fingerprint
                for p in engine.predict_samples(
                    model_id, space.validation_sample_ids, PredictionScope.VALIDATION
                )
            )
        elif isinstance(spec, ProbabilisticModelSpec):
            operations += 1
            engine_p = ProbabilisticEngine(repo)
            model_id = engine_p.fit_model(spec, at, at, at).artifact_id
            ids = tuple(
                p.fingerprint
                for p in engine_p.predict_samples(
                    model_id, space.validation_sample_ids, PredictionScope.VALIDATION
                )
            )
        elif isinstance(spec, EventConditioningSpec):
            operations += 1
            engine_e = EventEngine(repo)
            model_id = engine_e.fit(spec, recipe.train_input_ids, at, at, at).fingerprint
            ids = tuple(
                engine_e.forecast(
                    model_id,
                    observation,
                    base,
                    repo.get(EventConditionedObservation, observation).origin.timestamp_ns,
                ).fingerprint
                for observation, base in recipe.validation_bindings
            )
        elif isinstance(spec, RegimeConditioningSpec):
            operations += 1
            engine_r = RegimeEngine(repo)
            model_id = engine_r.fit(spec, recipe.train_input_ids, at, at, at).fingerprint
            ids = tuple(
                engine_r.forecast(
                    model_id,
                    observation,
                    base,
                    repo.get(RegimeConditionedSample, observation).origin.timestamp_ns,
                ).fingerprint
                for observation, base in recipe.validation_bindings
            )
        elif isinstance(spec, NonlinearModelSpec):
            engine_n = NonlinearEngine(repo)
            transforms = []
            for d in spec.interaction_set.definitions:
                if d.parameters.knot_policy is KnotPolicy.TRAIN_QUANTILES:
                    operations += 1
                    transforms.append(
                        engine_n.fit_transform(
                            spec, d, recipe.train_input_ids, at, at, at
                        ).fingerprint
                    )
            states = tuple(sorted(transforms))
            matrix = engine_n.matrix(spec, recipe.train_input_ids, states, at)
            operations += 1
            model_id = engine_n.fit(spec, matrix.fingerprint, at, at, at).fingerprint
            ids = tuple(
                engine_n.predict(
                    model_id, packet, repo.get(ResearchSample, sample).timestamp_ns
                ).fingerprint
                for sample, packet in recipe.validation_bindings
            )
        else:
            assert isinstance(spec, SequenceModelSpec)
            engine_s = SequenceEngine(repo)
            operations += 1
            state = engine_s.fit_transform(spec, recipe.train_bindings, at, at, at)
            states = (state.fingerprint,)
            dataset = engine_s.dataset(spec, state.fingerprint, at)
            operations += 1
            model_id = engine_s.fit(spec, dataset.fingerprint, at, at, at).fingerprint
            ids = tuple(
                engine_s.predict(
                    model_id, sample, snapshot, repo.get(ResearchSample, sample).timestamp_ns
                ).fingerprint
                for sample, snapshot in recipe.validation_bindings
            )
        return CandidateFitResult(
            candidate.fingerprint,
            model_id,
            states,
            ids,
            CandidateStatus.VALID,
            "native-TRAIN-fit-frozen-VALIDATION-predictions",
            operations,
            cutoff_ns,
        )
    except (ContractError, ArithmeticError) as exc:
        if isinstance(exc, ContractError) and any(
            s in str(exc).lower()
            for s in (
                "corruption",
                "hash",
                "unresolved",
                "response guard",
                "test/held-out",
                "planning cannot",
                "canonical",
                "payload",
                "cycle",
                "writer transaction",
                "snapshot",
                "relational index",
            )
        ):
            raise
        # KeyError/storage corruption propagate and roll back the whole search.
        # Only expected native admission/numerical failures become trial outcomes.
        numeric = isinstance(exc, ArithmeticError) or any(
            s in str(exc).lower()
            for s in ("nonfinite", "numeric", "condition", "rank deficient", "convergen")
        )
        return CandidateFitResult(
            candidate.fingerprint,
            None,
            states,
            (),
            CandidateStatus.NUMERICAL_FAILURE if numeric else CandidateStatus.FIT_FAILED,
            "native-fit-rejected:" + str(exc)[:220],
            operations,
            cutoff_ns,
        )

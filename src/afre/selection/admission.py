"""Target-free exact native context and deterministic whole-grid reservations."""

from typing import TYPE_CHECKING

from afre.event_conditioned.definitions import EventConditioningSpec
from afre.nonlinear.definitions import NonlinearModelSpec
from afre.probabilistic.definitions import ProbabilisticModelSpec
from afre.regime_conditioned.definitions import RegimeConditioningSpec
from afre.research_datasets.manifests import ResearchDatasetManifest
from afre.research_datasets.schema import Partition
from afre.research_datasets.splits import FoldDefinition
from afre.schema import require
from afre.selection.budgets import ResourceUsage
from afre.selection.definitions import SearchSpace
from afre.selection.fitting import fit_operations
from afre.sequence.definitions import SequenceModelSpec
from afre.serialization import canonical_json
from afre.statistical_models.artifacts import FittedModelArtifact, PointForecast
from afre.statistical_models.definitions import BaselineModelSpec

if TYPE_CHECKING:
    from afre.selection.repository import SelectionRepository


def admit(repo: "SelectionRepository", space: SearchSpace) -> ResourceUsage:
    fold = repo.get(FoldDefinition, space.fold_id)
    dataset = repo.get(ResearchDatasetManifest, space.dataset_id)
    require(
        fold.dataset_id == dataset.fingerprint and space.declared_ns <= fold.training_cutoff_ns,
        "selection declaration before TRAIN boundary/exact dataset",
    )
    train = tuple(
        s
        for s in repo.partition_samples(space.fold_id, Partition.TRAIN)
        if s.target_definition_id == space.target_id
    )
    validation = {
        s.fingerprint
        for s in repo.partition_samples(space.fold_id, Partition.VALIDATION)
        if s.target_definition_id == space.target_id
    }
    sealed = {
        row[0]
        for row in repo._connection.execute(
            "SELECT m.sample_id FROM r_memberships m JOIN r_folds f ON m.fold_id=f.fingerprint "
            "WHERE f.dataset_id=? AND m.partition=?",
            (space.dataset_id, Partition.TEST.value),
        )
    }
    require(
        sealed.isdisjoint({s.fingerprint for s in train} | set(space.validation_sample_ids)),
        "cannot reclassify a declared TEST sample for selection",
    )
    require(
        set(space.validation_sample_ids) <= validation,
        "selection declared samples must be VALIDATION",
    )
    require(
        len(space.recipes) <= repo.selection_bounds.candidates
        and len(space.dimensions) <= repo.selection_bounds.dimensions
        and len(train) <= repo.selection_bounds.rows
        and len(space.validation_sample_ids) <= repo.selection_bounds.rows,
        "selection configured admission bounds",
    )
    for r in space.recipes:
        spec = r.native_spec
        if isinstance(spec, EventConditioningSpec):
            base = repo.get(FittedModelArtifact, spec.base_model_id)
            native = repo.get(BaselineModelSpec, base.spec_id)
            target, fold_id = spec.window.target, native.fold_id
        elif isinstance(spec, RegimeConditioningSpec):
            base = repo.get(FittedModelArtifact, spec.base_model_id)
            native = repo.get(BaselineModelSpec, base.spec_id)
            target, fold_id = spec.target, native.fold_id
        else:
            target, fold_id = spec.target, spec.fold_id
        require(
            target.fingerprint == space.target_id
            and target.horizon.fingerprint == space.horizon_id
            and fold_id == space.fold_id,
            "candidate exact target/horizon/fold",
        )
        if isinstance(spec, (NonlinearModelSpec, SequenceModelSpec)):
            require(spec.cutoff_ns == fold.training_cutoff_ns, "candidate TRAIN cutoff")
        if isinstance(spec, ProbabilisticModelSpec):
            require(
                spec.training_cutoff_ns == fold.training_cutoff_ns, "probability TRAIN cutoff"
            )
        if isinstance(spec, (NonlinearModelSpec, SequenceModelSpec)):
            require(
                set(r.feature_ids) == {f.fingerprint for f in spec.features},
                "exact declared native feature variant",
            )
        elif isinstance(spec, BaselineModelSpec):
            require(
                set(r.preprocessing_ids) == set(spec.preprocessing_state_ids),
                "exact native preprocessing variant",
            )
        if r.orthogonal_feature_ids:
            from afre.selection.orthogonal_features import validate_orthogonal_features

            validate_orthogonal_features(repo, r)
        for identity in (
            *r.train_input_ids,
            *r.preprocessing_ids,
            *r.feature_ids,
            *r.diagnostic_ids,
        ):
            repo.get_any(identity)
        if isinstance(spec, (EventConditioningSpec, RegimeConditioningSpec)):
            for identity in r.train_input_ids:
                obs = repo.get_any(identity)
                require(
                    getattr(obs, "sample_id", None) in {s.fingerprint for s in train}
                    and getattr(obs, "spec_id", None) == spec.fingerprint,
                    "exact TRAIN conditioned recipe",
                )
            for obs_id, base_id in r.validation_bindings:
                obs = repo.get_any(obs_id)
                base_forecast = repo.get(PointForecast, base_id)
                require(
                    getattr(obs, "sample_id", None) == base_forecast.input.sample_id
                    and base_forecast.input.sample_id in space.validation_sample_ids
                    and getattr(obs, "spec_id", None) == spec.fingerprint,
                    "exact VALIDATION conditioned binding",
                )
        elif isinstance(spec, NonlinearModelSpec):
            require(
                {getattr(repo.get_any(i), "sample_id", None) for i in r.train_input_ids}
                <= {s.fingerprint for s in train},
                "nonlinear TRAIN inputs",
            )
            require(
                {s for s, _ in r.validation_bindings} == set(space.validation_sample_ids),
                "nonlinear VALIDATION bindings",
            )
        elif isinstance(spec, SequenceModelSpec):
            require(
                {s for s, _ in r.train_bindings} <= {s.fingerprint for s in train}
                and {s for s, _ in r.validation_bindings} == set(space.validation_sample_ids),
                "sequence TRAIN/VALIDATION bindings",
            )
    anchors = tuple(repo.get(PointForecast, i) for i in space.failure_anchor_source_ids)
    for source in anchors:
        from afre.statistical_models.schema import PredictionScope

        require(
            source.input.scope is PredictionScope.VALIDATION
            and source.input.sample_id in space.validation_sample_ids
            and source.target_definition_id == space.target_id,
            "declared native VALIDATION failure anchor",
        )
    if anchors:
        require(
            {s.input.sample_id for s in anchors} == set(space.validation_sample_ids),
            "full anchor protocol",
        )
    count = len(space.recipes)
    operations = sum(fit_operations(r) for r in space.recipes)
    iterations = sum(getattr(r.native_spec, "max_iterations", 1) for r in space.recipes)
    payload = len(canonical_json(space).encode())
    budget = space.budget
    require(
        operations <= budget.max_fit_operations
        and len(train) * count <= budget.max_train_rows
        and len(space.validation_sample_ids) * count <= budget.max_validation_rows
        and iterations <= budget.max_numerical_iterations
        and payload <= budget.max_payload_bytes,
        "exhaustive grid exceeds deterministic resource budget before fitting",
    )
    return ResourceUsage(
        count,
        operations,
        len(train) * count,
        len(space.validation_sample_ids) * count,
        iterations,
        0,
        0,
        0,
        payload,
    )

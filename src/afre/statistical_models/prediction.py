"""Feature-only forecast construction; this module never imports target truth."""

from typing import TYPE_CHECKING

from afre.feature_store.materialization import PointInTimeJoinResult
from afre.research_datasets.definitions import ResearchDatasetDefinition
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.research_datasets.splits import FoldMembership
from afre.schema import require
from afre.statistical_models.artifacts import (
    FittedModelArtifact,
    ModelFitInputs,
    ModelFitRun,
    PointForecast,
    PredictionInput,
)
from afre.statistical_models.definitions import BaselineModelSpec
from afre.statistical_models.design_matrix import feature_values, preprocessing_states
from afre.statistical_models.linear_algebra import dot, finite
from afre.statistical_models.schema import PredictionScope

if TYPE_CHECKING:
    from afre.statistical_models.repository import ModelRepository

PARTITIONS = {
    PredictionScope.IN_SAMPLE: Partition.TRAIN,
    PredictionScope.VALIDATION: Partition.VALIDATION,
    PredictionScope.TEST: Partition.TEST,
}


def input_for_sample(
    repo: "ModelRepository", model: FittedModelArtifact, sample_id: str, scope: PredictionScope
) -> PredictionInput:
    spec = repo.resolve(BaselineModelSpec, model.spec_id)
    sample = repo.resolve(ResearchSample, sample_id)
    require(
        sample.origin is not None and sample.join_id is not None,
        "prediction lacks feature origin",
    )
    require(
        sample.target_definition_id == spec.target.fingerprint,
        "prediction target/horizon mismatch",
    )
    assert sample.origin is not None and sample.join_id is not None
    return PredictionInput(sample.origin, sample.join_id, sample_id, scope)


def forecast_for(
    repo: "ModelRepository",
    model: FittedModelArtifact,
    request: PredictionInput,
    computed_ns: int,
) -> PointForecast:
    spec = repo.resolve(BaselineModelSpec, model.spec_id)
    runs = repo._connection.execute(
        "SELECT fingerprint FROM m_fits WHERE artifact_id=?", (model.fingerprint,)
    ).fetchall()
    require(len(runs) == 1, "prediction requires one completed model fit run")
    run = repo.resolve(ModelFitRun, runs[0][0])
    require(
        run.artifact_id == model.fingerprint
        and run.inputs.fingerprint == model.fit_inputs_id
        and run.diagnostics_id == model.diagnostics.fingerprint,
        "prediction completed fit lineage mismatch",
    )
    require(model.diagnostics.converged, "nonconverged artifact cannot issue a forecast")
    origin = request.origin
    historical = request.scope is not PredictionScope.IN_SAMPLE
    require(
        not historical or model.available_ns <= origin.availability_cutoff_ns,
        "model unavailable at forecast origin",
    )
    require(
        historical or computed_ns >= model.available_ns,
        "in-sample diagnostics require an explicit later computation time",
    )
    if request.sample_id is not None:
        sample = repo.resolve(ResearchSample, request.sample_id)
        require(
            sample.origin == origin
            and sample.join_id == request.join_id
            and sample.target_definition_id == spec.target.fingerprint,
            "prediction sample/evidence mismatch",
        )
        rows = repo._connection.execute(
            "SELECT fingerprint FROM r_memberships WHERE fold_id=? AND sample_id=?",
            (spec.fold_id, request.sample_id),
        ).fetchall()
        require(len(rows) == 1, "prediction sample outside model fold")
        membership = repo.resolve(FoldMembership, rows[0][0])
        require(
            membership.fold_id == spec.fold_id and membership.sample_id == request.sample_id,
            "prediction membership index mismatch",
        )
        if request.scope in PARTITIONS:
            require(
                membership.partition is PARTITIONS[request.scope],
                "prediction scope/partition mismatch",
            )
        else:
            require(
                membership.partition not in (Partition.TRAIN, Partition.TEST),
                "other OOS scope cannot bypass TRAIN/TEST boundary",
            )
    else:
        require(
            request.scope is PredictionScope.OUT_OF_SAMPLE_OTHER,
            "external forecast requires explicit other-OOS scope",
        )
    states = preprocessing_states(repo, spec, False)
    join = repo.resolve(PointInTimeJoinResult, request.join_id)
    require(join.row.origin == origin, "prediction feature row/origin mismatch")
    inputs = repo.resolve(ModelFitInputs, model.fit_inputs_id)
    dataset = repo.resolve_dataset(inputs.dataset_id)
    definition = repo.resolve(ResearchDatasetDefinition, dataset.definition_id)
    compatibility = definition.compatibility
    require(
        {a.feature for a in join.audits} == set(spec.feature_set.definitions)
        and join.row.dataset.calendar_id == compatibility.calendar_id
        and join.row.dataset.adjustment == compatibility.feature_adjustment
        and join.row.dataset.source_dataset_ids == compatibility.source_dataset_ids,
        "prediction rich feature/calendar/source/adjustment mismatch",
    )
    application_ns = origin.availability_cutoff_ns if historical else computed_ns
    values, _ = feature_values(join, model.feature_ids, states, application_ns)
    require(
        values is not None, "prediction missing/unverified features; no implicit imputation"
    )
    assert values is not None
    value = finite(model.intercept + dot(values, model.coefficients))
    return PointForecast(
        model.fingerprint,
        spec.target.fingerprint,
        request,
        value,
        model.available_ns,
        computed_ns,
        computed_ns,
        historical,
    )

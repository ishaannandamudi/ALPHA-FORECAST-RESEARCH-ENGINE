"""Completed fit publication, semantic replay and workload limits fail closed."""

from dataclasses import replace

import pytest

from afre.research_datasets import Partition
from afre.schema import ContractError
from afre.statistical_models import (
    DesignMatrix,
    InterceptPolicy,
    ModelFamily,
    ModelFitInputs,
    NonconvergencePolicy,
    PredictionScope,
)
from afre.statistical_models.design_matrix import build_matrix
from afre.statistical_models.validation import fitted_artifact
from afre.universe.models import UniverseSnapshot
from tests.statistical_models.conftest import ModelCase


def validation_samples(case: ModelCase) -> tuple[str, ...]:
    with case.repository.read_snapshot(), case.repository.validation_cache():
        return tuple(
            s.fingerprint
            for s in case.repository.partition_samples(
                case.spec().fold_id, Partition.VALIDATION
            )
            if s.target_definition_id == case.spec().target.fingerprint
        )


def test_model_store_records_current_snapshot_engine(model_case: ModelCase) -> None:
    c = model_case
    snapshot = c.repository.get(UniverseSnapshot, c.fixture.requests[0].snapshot_id)
    assert snapshot.engine_version == "0.6.0"


@pytest.mark.parametrize(
    "family",
    (
        ModelFamily.UNCONDITIONAL_MEAN,
        ModelFamily.UNCONDITIONAL_MEDIAN,
        ModelFamily.REFERENCE_VALUE,
    ),
)
def test_reference_intercept_policy_is_explicit(
    model_case: ModelCase, family: ModelFamily
) -> None:
    with pytest.raises(ContractError, match="intercept policy"):
        replace(model_case.spec(family), intercept=InterceptPolicy.NONE)


def test_incomplete_fit_cannot_issue_forecasts(model_case: ModelCase) -> None:
    c = model_case
    spec = c.spec()
    with c.repository.transaction(), c.repository.validation_cache():
        matrix = build_matrix(c.repository, spec, 40)
        inputs = ModelFitInputs(
            spec.fingerprint,
            matrix.dataset_id,
            matrix.split_id,
            matrix.fold_id,
            matrix.fingerprint,
            tuple(r.sample_id for r in matrix.rows),
            spec.preprocessing_state_ids,
            matrix.training_cutoff_ns,
            40,
            40,
            40,
        )
        artifact = fitted_artifact(c.repository, spec, matrix, inputs)
        for value in (
            spec.foundation_spec,
            spec,
            matrix,
            inputs,
            artifact.diagnostics,
            artifact,
        ):
            c.repository.put(value)
    with pytest.raises(ContractError, match="completed model fit run"):
        c.engine.predict_samples(
            artifact.fingerprint, validation_samples(c), PredictionScope.VALIDATION
        )


def test_nonconverged_fit_cannot_issue_forecasts(model_case: ModelCase) -> None:
    c = model_case
    spec = replace(
        c.spec(ModelFamily.ELASTIC_NET),
        max_iterations=1,
        tolerance=1e-15,
        nonconvergence=NonconvergencePolicy.RETURN_NONCONVERGED,
    )
    run = c.engine.fit_model(spec, 40, 40, 40)
    assert not c.engine.model_artifact(run.artifact_id).diagnostics.converged
    with pytest.raises(ContractError, match="nonconverged"):
        c.engine.predict_samples(
            run.artifact_id, validation_samples(c), PredictionScope.VALIDATION
        )


def test_semantic_forgeries_with_valid_hashes_are_rejected(model_case: ModelCase) -> None:
    c = model_case
    run = c.engine.fit_model(c.spec(), 40, 40, 40)
    model = c.engine.model_artifact(run.artifact_id)
    matrix = c.repository.get(DesignMatrix, run.inputs.matrix_id)
    with c.repository.transaction(), pytest.raises(ContractError, match="contamination"):
        c.repository.put(
            replace(matrix, rows=(replace(matrix.rows[0], response=999.0), *matrix.rows[1:]))
        )
    with c.repository.transaction(), pytest.raises(ContractError, match="solver replay"):
        c.repository.put(replace(model, coefficients=tuple(v + 1 for v in model.coefficients)))
    predictions = c.engine.predict_samples(
        run.artifact_id, validation_samples(c), PredictionScope.VALIDATION
    )
    with c.repository.transaction(), pytest.raises(ContractError, match="forecast replay"):
        c.repository.put(replace(predictions[0], value=predictions[0].value + 1))
    evaluation = c.engine.evaluate(tuple(p.fingerprint for p in predictions), 100, 100)
    with c.repository.transaction(), pytest.raises(ContractError, match="evaluation replay"):
        c.repository.put(
            replace(
                evaluation,
                pairs=(replace(evaluation.pairs[0], truth=999.0), *evaluation.pairs[1:]),
            )
        )


def test_batch_evaluation_and_audit_limits(model_case: ModelCase) -> None:
    c = model_case
    run = c.engine.fit_model(c.spec(), 40, 40, 40)
    samples = validation_samples(c)
    bounds = c.repository.model_bounds
    c.repository.model_bounds = replace(bounds, predictions=1)
    with pytest.raises(ContractError, match="prediction sample bound"):
        c.engine.predict_samples(run.artifact_id, samples, PredictionScope.VALIDATION)
    c.repository.model_bounds = replace(bounds, evaluations=1)
    predictions = c.engine.predict_samples(run.artifact_id, samples, PredictionScope.VALIDATION)
    ids = tuple(p.fingerprint for p in predictions)
    first = c.engine.evaluate(ids, 100, 100)
    assert c.engine.evaluate(ids, 100, 100) == first
    with pytest.raises(ContractError, match="evaluation result bound"):
        c.engine.evaluate(ids, 99, 100)
    for limit in (replace(bounds, audit_nodes=1), replace(bounds, audit_depth=1)):
        c.repository.model_bounds = limit
        with pytest.raises(ContractError, match="audit depth/node bound"):
            c.engine.model_audit(run.artifact_id)

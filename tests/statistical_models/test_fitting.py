"""TRAIN-only fitting and frozen safe lineage integration."""

from dataclasses import replace

import pytest

from afre.models import ModelSpec
from afre.research_datasets import Partition
from afre.schema import ContractError
from afre.serialization import canonical_json, deserialize
from afre.statistical_models import (
    DesignMatrix,
    FittedModelArtifact,
    ModelFamily,
    ModelFitRun,
    PredictionScope,
)
from afre.target_engine.models import TargetVintage
from tests.statistical_models.conftest import ModelCase


@pytest.mark.parametrize(
    "family",
    tuple(
        f
        for f in ModelFamily
        if f not in (ModelFamily.PERSISTENCE, ModelFamily.RESIDUAL_LINEAR)
    ),
)
def test_families_and_train_lineage(model_case: ModelCase, family: ModelFamily) -> None:
    c = model_case
    spec = c.spec(family)
    run = c.engine.fit_model(spec, 40, 40, 40)
    model = c.engine.model_artifact(run.artifact_id)
    matrix = c.repository.get(DesignMatrix, run.inputs.matrix_id)
    with c.repository.read_snapshot(), c.repository.validation_cache():
        train = {
            s.fingerprint for s in c.repository.partition_samples(spec.fold_id, Partition.TRAIN)
        }
    assert set(run.inputs.train_sample_ids) <= train
    assert all(
        c.repository.get(TargetVintage, row.target_id).clocks.final_available_ns <= 40
        for row in matrix.rows
    )
    assert c.repository.get(ModelSpec, model.foundation_spec_id) == spec.foundation_spec
    assert model.diagnostics.converged and model.diagnostics.sample_count == len(matrix.rows)
    assert deserialize(canonical_json(model)) == model
    assert c.engine.fit_model(spec, 40, 40, 40) == run
    assert c.engine.model_history(spec.fold_id) == (run,)


def test_target_free_prediction_evaluation_and_audit(
    model_case: ModelCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = model_case
    run = c.engine.fit_model(c.spec(), 40, 40, 40)
    with c.repository.read_snapshot(), c.repository.validation_cache():
        samples = tuple(
            s
            for s in c.repository.partition_samples(c.spec().fold_id, Partition.VALIDATION)
            if s.target_definition_id == c.spec().target.fingerprint
        )
    original = c.repository.get

    def guarded(cls: type[object], identity: str) -> object:
        assert cls is not TargetVintage, "prediction must not load any response"
        return original(cls, identity)  # type: ignore[type-var]

    with monkeypatch.context() as patch:
        patch.setattr(c.repository, "get", guarded)
        predictions = c.engine.predict_samples(
            run.artifact_id, tuple(s.fingerprint for s in samples), PredictionScope.VALIDATION
        )
    evaluation = c.engine.evaluate(tuple(p.fingerprint for p in predictions), 100, 100)
    assert len(evaluation.pairs) == len(samples)
    assert (
        c.engine.prediction_audit(predictions[0].fingerprint).root_id
        == predictions[0].fingerprint
    )
    assert c.repository.get(ModelFitRun, run.fingerprint) == run
    assert c.repository.get(FittedModelArtifact, run.artifact_id).available_ns == 40
    delayed = c.engine.fit_model(c.spec(), 40, 41, 41)
    with pytest.raises(ContractError, match="model unavailable"):
        c.engine.predict_samples(
            delayed.artifact_id, (samples[0].fingerprint,), PredictionScope.VALIDATION
        )


def test_spec_versions_change_identity(model_case: ModelCase) -> None:
    c = model_case
    spec = c.spec()
    changed = replace(spec, solver_version="stdlib-v2")
    assert changed.fingerprint != spec.fingerprint
    with pytest.raises(ContractError, match="unsupported"):
        c.engine.fit_model(changed, 40, 40, 40)

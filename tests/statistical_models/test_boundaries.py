"""Causal cutoffs, fixed scopes, forbidden truth inputs and held-out isolation."""

from collections.abc import Callable
from dataclasses import replace
from typing import TypeVar

import pytest

from afre.feature_store.materialization import PointInTimeJoinResult
from afre.research_datasets import DatasetEngine, Partition, SplitStrategy
from afre.schema import Artifact, ContractError
from afre.statistical_models import (
    DesignMatrix,
    ModelFamily,
    PredictionInput,
    PredictionScope,
)
from afre.statistical_models.design_matrix import feature_values
from afre.target_engine.models import TargetVintage
from afre.time import TimeRange
from examples.research_dataset_demo import split_definition
from tests.statistical_models.conftest import ModelCase

A = TypeVar("A", bound=Artifact)


@pytest.mark.parametrize(
    "partition",
    (
        Partition.VALIDATION,
        Partition.TEST,
        Partition.PURGED,
        Partition.EMBARGOED,
        Partition.INELIGIBLE,
    ),
)
def test_excluded_responses_cannot_affect_fit(
    model_case: ModelCase, monkeypatch: pytest.MonkeyPatch, partition: Partition
) -> None:
    c = model_case
    spec = c.spec()
    first = c.engine.fit_model(spec, 40, 40, 40)
    with c.repository.read_snapshot(), c.repository.validation_cache():
        blocked = {s.target_id for s in c.repository.partition_samples(spec.fold_id, partition)}
    original = c.repository.get

    def guarded(cls: type[A], identity: str) -> A:
        assert cls is not TargetVintage or identity not in blocked, (
            "excluded response entered fit"
        )
        return original(cls, identity)

    with monkeypatch.context() as patch:
        patch.setattr(c.repository, "get", guarded)
        repeated = c.engine.fit_model(spec, 40, 40, 40)
    assert repeated == first


@pytest.mark.parametrize("cutoff,admitted", ((34, False), (35, True)))
def test_exact_label_cutoff(model_case: ModelCase, cutoff: int, admitted: bool) -> None:
    c = model_case
    definition = replace(
        split_definition(c.fixture),
        name=f"split.cutoff_{cutoff}",
        strategy=SplitStrategy.FIXED_HOLDOUT,
        step_ns=0,
        fold_count=1,
        training_cutoff_ns=cutoff,
        train=TimeRange(10, 30),
        preprocessing_spec_ids=(),
    )
    split = DatasetEngine(c.repository).build_split(c.dataset.fingerprint, definition)
    spec = replace(c.spec(), fold_id=split.fold_ids[0], preprocessing_state_ids=())
    run = c.engine.fit_model(spec, cutoff, cutoff, cutoff)
    matrix = c.repository.get(DesignMatrix, run.inputs.matrix_id)
    assert (
        any(
            c.repository.get(TargetVintage, r.target_id).clocks.final_available_ns == 35
            for r in matrix.rows
        )
        is admitted
    )


def test_in_sample_diagnostics_and_test_seal(model_case: ModelCase) -> None:
    c = model_case
    run = c.engine.fit_model(c.spec(), 40, 40, 40)
    with c.repository.read_snapshot(), c.repository.validation_cache():
        train = tuple(
            s.fingerprint
            for s in c.repository.partition_samples(c.spec().fold_id, Partition.TRAIN)
            if s.target_definition_id == c.spec().target.fingerprint
        )
        test = tuple(
            s.fingerprint
            for s in c.repository.partition_samples(c.spec().fold_id, Partition.TEST)
            if s.target_definition_id == c.spec().target.fingerprint
        )
    train = run.inputs.train_sample_ids
    in_sample = c.engine.predict_samples(run.artifact_id, train, PredictionScope.IN_SAMPLE, 40)
    assert all(not p.historical_admissible for p in in_sample)
    assert (
        c.engine.evaluate(tuple(p.fingerprint for p in in_sample), 40, 40).scope
        is PredictionScope.IN_SAMPLE
    )
    with pytest.raises(ContractError, match="explicit later computation"):
        c.engine.predict_samples(run.artifact_id, train, PredictionScope.IN_SAMPLE)
    predictions = c.engine.predict_samples(run.artifact_id, test, PredictionScope.TEST)
    with pytest.raises(ContractError, match="explicit identity"):
        c.engine.evaluate(tuple(p.fingerprint for p in predictions), 100, 100)
    evaluation = c.engine.evaluate(
        tuple(p.fingerprint for p in predictions), 100, 100, "afre5-test-v1"
    )
    assert evaluation.test_evaluation_id is not None
    assert (
        c.engine.evaluate(tuple(p.fingerprint for p in predictions), 100, 100, "afre5-test-v1")
        == evaluation
    )
    with pytest.raises(ContractError, match="identity reuse"):
        c.engine.evaluate(tuple(p.fingerprint for p in predictions), 99, 100, "afre5-test-v1")
    with pytest.raises(ContractError, match="scope/partition"):
        c.engine.predict_samples(run.artifact_id, test, PredictionScope.VALIDATION)
    with pytest.raises(ContractError, match="bypass"):
        c.engine.predict_samples(run.artifact_id, test, PredictionScope.OUT_OF_SAMPLE_OTHER)


def test_prediction_input_no_response_and_feature_boundary(model_case: ModelCase) -> None:
    c = model_case
    run = c.engine.fit_model(c.spec(), 40, 40, 40)
    with c.repository.read_snapshot(), c.repository.validation_cache():
        sample = next(
            s
            for s in c.repository.partition_samples(c.spec().fold_id, Partition.VALIDATION)
            if s.target_definition_id == c.spec().target.fingerprint
        )
    assert sample.origin is not None and sample.join_id is not None
    join = c.repository.get(PointInTimeJoinResult, sample.join_id)
    with pytest.raises(ContractError, match="unavailable"):
        feature_values(
            join,
            (c.fixture.preprocessing.normalization.feature.definition.fingerprint,),
            (),
            39,
        )
    constructor: Callable[..., PredictionInput] = PredictionInput
    with pytest.raises(TypeError):
        constructor(
            **{
                "origin": sample.origin,
                "join_id": sample.join_id,
                "sample_id": sample.fingerprint,
                "scope": PredictionScope.VALIDATION,
                "target_value": 999.0,
            }
        )
    request = PredictionInput(
        sample.origin, sample.join_id, sample.fingerprint, PredictionScope.VALIDATION
    )
    with pytest.raises(ContractError, match="sample/evidence"):
        c.engine.predict(
            run.artifact_id,
            replace(request, origin=replace(sample.origin, build_context="wrong")),
            40,
        )
    external = replace(request, sample_id=None, scope=PredictionScope.OUT_OF_SAMPLE_OTHER)
    assert c.engine.predict(run.artifact_id, external, 40).historical_admissible


def test_comparisons_exact_samples_and_target_horizons(model_case: ModelCase) -> None:
    c = model_case
    mean = c.engine.fit_model(c.spec(ModelFamily.UNCONDITIONAL_MEAN), 40, 40, 40)
    linear = c.engine.fit_model(c.spec(), 40, 40, 40)
    with c.repository.read_snapshot(), c.repository.validation_cache():
        ids = tuple(
            s.fingerprint
            for s in c.repository.partition_samples(c.spec().fold_id, Partition.VALIDATION)
            if s.target_definition_id == c.spec().target.fingerprint
        )
        other = next(
            s.fingerprint
            for s in c.repository.partition_samples(c.spec().fold_id, Partition.VALIDATION)
            if s.target_definition_id != c.spec().target.fingerprint
        )
    predictions = c.engine.predict_samples(linear.artifact_id, ids, PredictionScope.VALIDATION)
    references = c.engine.predict_samples(mean.artifact_id, ids, PredictionScope.VALIDATION)
    evaluation = c.engine.evaluate(tuple(p.fingerprint for p in predictions), 100, 100)
    reference = c.engine.evaluate(tuple(p.fingerprint for p in references), 100, 100)
    assert c.engine.compare_models(
        evaluation.fingerprint, reference.fingerprint
    ).sample_ids == tuple(sorted(ids))
    smaller = c.engine.evaluate((predictions[0].fingerprint,), 100, 100)
    with pytest.raises(ContractError, match="same samples"):
        c.engine.compare_models(smaller.fingerprint, reference.fingerprint)
    with pytest.raises(ContractError, match="target/horizon"):
        c.engine.predict_samples(linear.artifact_id, (other,), PredictionScope.VALIDATION)
    with pytest.raises(ContractError, match="cannot mix"):
        c.engine.evaluate((predictions[0].fingerprint, references[1].fingerprint), 100, 100)
    with pytest.raises(ContractError, match="unavailable"):
        c.engine.evaluate(tuple(p.fingerprint for p in predictions), 39, 40)
    assert evaluation.ic_summary.origin_count == 1
    assert reference.ic_summary.pearson_count == 0

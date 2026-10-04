"""Causal persistence and exact supplied residual-return target integration."""

from dataclasses import replace

import pytest

from afre.feature_store import FeatureSetManifest
from afre.research_datasets import DatasetEngine, Partition
from afre.schema import ContractError
from afre.statistical_models import (
    InterceptPolicy,
    ModelFamily,
    PersistenceReference,
    PredictionScope,
    SolverIdentity,
)
from afre.target_engine import TargetDatasetManifest, TargetEngine, TargetSetManifest
from afre.target_engine.residuals import SuppliedBenchmarkReturn
from afre.targets import TargetType
from afre.time import TimeRange
from examples.feature_store_demo import SOURCE, clocks, definition, source_vintage
from examples.research_dataset_demo import split_definition
from examples.target_demo import BENCHMARK, CALENDAR_TARGET, SOURCE_MARKET
from examples.target_demo import definition as target_definition
from examples.universe_demo import SECURITIES
from tests.statistical_models.conftest import ModelCase


def test_supplied_residual_baseline(model_case: ModelCase) -> None:
    c = model_case
    residual = replace(
        target_definition(TargetType.RESIDUAL_RETURN, horizon_ns=5),
        name="target.model_residual",
    )
    target_set = TargetSetManifest((residual,))
    target_engine = TargetEngine(c.repository)
    requests = []
    with c.repository.transaction():
        c.repository.put(BENCHMARK)
        c.repository.put(residual)
        c.repository.put(target_set)
    for request in c.fixture.requests:
        assert request.target_dataset_id is not None
        old = c.repository.get(TargetDatasetManifest, request.target_dataset_id)
        at = old.origins[0].timestamp_ns
        benchmark = SuppliedBenchmarkReturn(
            BENCHMARK,
            TimeRange(at, at + 5),
            at,
            at + 5,
            0.001,
            clocks(at + 15),
            SOURCE.provenance,
        )
        with c.repository.transaction():
            c.repository.put(benchmark)
        source = target_engine.freeze_source(
            SOURCE_MARKET, CALENDAR_TARGET, at + 15, benchmark_ids=(benchmark.fingerprint,)
        )
        labels = target_engine.build_dataset(
            "model-residual-labels",
            old.origins,
            target_set,
            source.fingerprint,
            old.universe,
            clocks(at + 15),
        )
        requests.append(replace(request, target_dataset_id=labels.fingerprint))
    research = DatasetEngine(c.repository)
    dataset = research.build_dataset(
        replace(c.fixture.definition, name="research.model_residual", target_set=target_set),
        tuple(requests),
        100,
        100,
    )
    split = research.build_split(dataset.fingerprint, split_definition(c.fixture))
    state = research.fit_preprocessing(split.fold_ids[0], c.fixture.preprocessing)
    spec = replace(
        c.spec(),
        family=ModelFamily.RESIDUAL_LINEAR,
        target=residual,
        fold_id=split.fold_ids[0],
        preprocessing_state_ids=(state.fingerprint,),
    )
    run = c.engine.fit_model(spec, 40, 40, 40)
    assert c.engine.model_artifact(run.artifact_id).diagnostics.converged
    with pytest.raises(ContractError, match="residual"):
        replace(spec, target=c.spec().target)


def test_causal_persistence_reference(model_case: ModelCase) -> None:
    c = model_case
    feature = definition("market.trailing_return", "dimensionless", lookback_ns=5)
    features = FeatureSetManifest((feature,))
    with c.repository.transaction():
        c.repository.put(feature)
        c.repository.put(features)
        for index, security in enumerate(SECURITIES):
            for at in range(10, 81, 10):
                past_return = (100.0 + at + index) / (100.0 + at - 5 + index) - 1
                c.repository.put(
                    source_vintage(feature, at, at, past_return, entity=security.instrument)
                )
    research = DatasetEngine(c.repository)
    dataset = research.build_dataset(
        replace(c.fixture.definition, name="research.persistence", feature_set=features),
        c.fixture.requests,
        100,
        100,
    )
    split = research.build_split(
        dataset.fingerprint, replace(split_definition(c.fixture), preprocessing_spec_ids=())
    )
    target = c.spec().target
    spec = replace(
        c.spec(),
        family=ModelFamily.PERSISTENCE,
        feature_set=features,
        fold_id=split.fold_ids[0],
        preprocessing_state_ids=(),
        intercept=InterceptPolicy.NONE,
        solver=SolverIdentity.REFERENCE_STATISTIC,
        persistence=PersistenceReference(
            feature.definition.fingerprint,
            target.fingerprint,
            5,
            "completed-trailing-simple-return-v1",
        ),
    )
    run = c.engine.fit_model(spec, 40, 40, 40)
    with c.repository.read_snapshot(), c.repository.validation_cache():
        samples = tuple(
            s
            for s in c.repository.partition_samples(spec.fold_id, Partition.VALIDATION)
            if s.target_definition_id == target.fingerprint
        )
    predictions = c.engine.predict_samples(
        run.artifact_id, tuple(s.fingerprint for s in samples), PredictionScope.VALIDATION
    )
    assert c.engine.model_artifact(run.artifact_id).coefficients == (1.0,)
    assert all(0 < p.value < 0.1 for p in predictions)
    assert spec.persistence is not None
    with pytest.raises(ContractError, match="horizon"):
        replace(spec, persistence=replace(spec.persistence, trailing_window_ns=10))

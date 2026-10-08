"""Real second SQLite writer appends corrections while readers retain exact frozen IDs."""

from dataclasses import replace

import pytest

from afre.costs import CostInputRole, CostResearchEngine, CostResearchRepository
from afre.probabilistic.artifacts import ProbabilisticForecast
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.schema import ContractError
from afre.serialization import canonical_json
from afre.statistical_models import ModelEngine
from afre.statistical_models.artifacts import FittedModelArtifact, PointForecast
from afre.statistical_models.definitions import BaselineModelSpec
from afre.target_engine.market_data import TargetBar
from afre.target_engine.models import TargetVintage
from examples.costs_fixture import declare_scenario
from examples.costs_workflow import assess, corrected_input
from examples.costs_workflow import test_spec_sources as supplied_test_sources
from tests.costs.conftest import CostCase


@pytest.mark.parametrize("kind", ("cost", "forecast", "target", "all"))
def test_frozen_reader_with_real_writer(case: CostCase, kind: str) -> None:
    scenario = case.fixture.scenario
    path, totals, expected = assess(case.engine, scenario)
    original = canonical_json(expected)
    filename = case.repo._connection.execute("PRAGMA database_list").fetchone()[2]
    with CostResearchRepository(filename) as writer:

        def correction() -> None:
            if kind in ("cost", "all"):
                old = next(
                    i for i in case.fixture.inputs if i.role is CostInputRole.MODEL_VALUE
                )
                value = replace(old, value=(old.value or 0) + 1, revision="writer2")
                CostResearchEngine(writer).publish_input(value)
            if kind in ("forecast", "all"):
                prob = writer.get(ProbabilisticForecast, scenario.source_ids[0])
                raw = writer.get(PointForecast, prob.point_forecast_id)
                models = tuple(
                    writer.get(FittedModelArtifact, r[0])
                    for r in writer._connection.execute(
                        "SELECT fingerprint FROM m_artifacts "
                        "WHERE type_name='FittedModelArtifact' "
                        "ORDER BY fingerprint"
                    )
                )
                alternate = next(
                    m
                    for m in models
                    if m.fingerprint != raw.model_artifact_id
                    and writer.get(BaselineModelSpec, m.spec_id).target == scenario.target
                    and m.available_ns <= raw.input.origin.availability_cutoff_ns
                )
                corrected = ModelEngine(writer).predict(
                    alternate.fingerprint, raw.input, raw.computed_ns
                )
                assert corrected.fingerprint != raw.fingerprint
            if kind in ("target", "all"):
                identity = writer._connection.execute(
                    "SELECT fingerprint FROM target_artifacts WHERE type_name='TargetBar' "
                    "LIMIT 1"
                ).fetchone()[0]
                bar = writer.get(TargetBar, identity)
                with writer.transaction():
                    writer.put(
                        replace(bar, close=(bar.close or 0) + 2, predecessor_id=identity)
                    )

        if kind in ("cost", "forecast"):
            p, ts = case.engine.estimate(scenario.fingerprint, 100, snapshot_hook=correction)
            assert canonical_json(p) == canonical_json(path)
            assert tuple(canonical_json(t) for t in ts) == tuple(
                canonical_json(t) for t in totals
            )
        else:
            actual = case.engine.evaluate(
                path.fingerprint,
                tuple(t.fingerprint for t in totals),
                100,
                100,
                snapshot_hook=correction,
            )
            assert canonical_json(actual) == original
    assert canonical_json(case.repo.resolve(type(expected), expected.fingerprint)) == original


def test_corrected_input_requires_new_scenario_and_result(case: CostCase) -> None:
    base = case.fixture.scenario
    original = assess(case.engine, base)[2]
    before = canonical_json(original)
    old = next(
        i
        for i in case.fixture.inputs
        if i.role is CostInputRole.MODEL_VALUE and i.as_of_ns == 40
    )
    value = replace(old, value=(old.value or 0) + 100, revision="corrected2")
    case.engine.publish_input(value)
    revised = corrected_input(base, old.fingerprint, value)
    new = assess(case.engine, revised)[2]
    assert old.fingerprint != value.fingerprint and base.fingerprint != revised.fingerprint
    assert original.fingerprint != new.fingerprint and original.net_sum != new.net_sum
    assert canonical_json(case.repo.get_any(original.fingerprint)) == before


def test_test_seal_target_perturbation_not_cost_tuning(case: CostCase) -> None:
    ids = supplied_test_sources(case.repo, case.fixture)
    samples = tuple(
        s.fingerprint
        for s in case.repo.partition_samples(case.fixture.scenario.fold_id, Partition.TEST)
    )
    spec = replace(case.fixture.upstream.spec, sample_ids=samples, forecast_ids=ids)
    scenario, _ = declare_scenario(case.repo, spec)
    path, totals = case.engine.estimate(scenario.fingerprint, 100)
    with pytest.raises(ContractError, match="TEST assessment identity"):
        case.engine.evaluate(path.fingerprint, tuple(t.fingerprint for t in totals), 100, 100)
    result = case.engine.evaluate(
        path.fingerprint, tuple(t.fingerprint for t in totals), 100, 100, "frozen-cost-test"
    )
    assert result.test_evaluation_id is not None
    scenario_bytes = canonical_json(scenario)
    test_sample = case.repo.get(ResearchSample, min(scenario.sample_ids))
    assert test_sample.target_id is not None
    test_truth = case.repo.get(TargetVintage, test_sample.target_id)
    assert test_truth.endpoint_bar_id is not None
    bar_id = test_truth.endpoint_bar_id
    bar = case.repo.get(TargetBar, bar_id)
    with case.repo.transaction():
        case.repo.put(replace(bar, close=(bar.close or 0) + 999, predecessor_id=bar_id))
    replay = case.engine.estimate(scenario.fingerprint, 100)
    assert canonical_json(replay[0]) == canonical_json(path)
    assert canonical_json(case.repo.get_any(scenario.fingerprint)) == scenario_bytes
    assert case.repo.get_any(result.fingerprint) == result
    with pytest.raises(ContractError, match="held-out"):
        case.engine.declare(replace(scenario, scenario_id="after-test", declared_ns=100))

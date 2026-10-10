"""Native cost/stability context remains descriptive and cannot refit fusion."""

from dataclasses import replace

import pytest

from afre.costs import CostResearchEngine
from afre.fusion import FusedForecast, FusionArtifact, FusionEngine, FusionRepository
from afre.fusion.metadata import FusionMetadata
from afre.invariance import (
    EnvironmentDefinition,
    EnvironmentKind,
    EnvironmentRule,
    EnvironmentSet,
    InvarianceEngine,
    StabilityAnalysisSpec,
    StabilityMetricName,
    StabilityTimeWindow,
)
from afre.research_datasets.samples import ResearchSample
from afre.schema import ContractError
from afre.serialization import canonical_json
from afre.statistical_models.artifacts import PointForecast
from afre.target_engine.definitions import TargetDefinition
from examples.costs_fixture import declare_scenario
from examples.fusion_fixture import FusionFixture, apply_partition
from examples.fusion_native import fuse_sources


def test_cost_evaluation_and_stability_context(
    fusion_case: tuple[FusionRepository, FusionFixture],
) -> None:
    repo, f = fusion_case
    e = FusionEngine(repo)
    artifact = e.fit(f.spec, 0, 0, 0)
    ids = apply_partition(repo, f, artifact.fingerprint, f.validation)
    target = repo.get(TargetDefinition, f.spec.target_id)
    anchors = tuple(
        row[0]
        for row in repo._connection.execute(
            "SELECT fingerprint FROM m_artifacts WHERE type_name='PointForecast'"
        )
    )
    assert len(anchors) == len(f.validation)
    environment = EnvironmentDefinition(
        "fusion-context",
        EnvironmentKind.TIME_WINDOW,
        "synthetic",
        "1",
        "AFRE-declared",
        EnvironmentRule.TIME,
        target,
        40,
        window=StabilityTimeWindow(40, 61),
    )
    inv = InvarianceEngine(repo)
    envset = inv.declare(EnvironmentSet((environment,), 40))
    spec = StabilityAnalysisSpec(
        target,
        f.spec.fold_id,
        envset.fingerprint,
        f.validation,
        anchors,
        (StabilityMetricName.MSE,),
        40,
        minimum_count=1,
    )
    inv.register(spec)
    members = tuple(
        inv.bind(environment.fingerprint, s, constructed_ns=40).fingerprint
        for s in f.validation
    )
    metric = inv.evaluate(spec.fingerprint, members, 100, 100)[0]
    assert metric.sample_ids
    native = repo.get(PointForecast, metric.forecast_ids[0])
    fused_id = fuse_sources(repo, "stability-context", (native.fingerprint,))
    before = canonical_json(
        repo.get(FusionArtifact, repo.get(FusedForecast, fused_id).artifact_id)
    )
    metadata = FusionMetadata(fused_id, (metric.fingerprint,), 100)
    e._publish((metadata,))
    assert repo.resolve(FusionMetadata, metadata.fingerprint) == metadata
    assert (
        canonical_json(repo.get(FusionArtifact, repo.get(FusedForecast, fused_id).artifact_id))
        == before
    )
    with pytest.raises(ContractError, match="stability metadata"):
        e._publish((FusionMetadata(fused_id, (f.spec.fingerprint,), 100),))
    cost_spec = replace(spec, forecast_ids=ids)
    scenario, _ = declare_scenario(repo, cost_spec)
    cost = CostResearchEngine(repo)
    path, totals = cost.estimate(scenario.fingerprint, 100)
    result = cost.evaluate(path.fingerprint, tuple(t.fingerprint for t in totals), 100, 100)
    assert len(result.included_sample_ids) == len(f.validation)
    assert repo.get(FusionArtifact, artifact.fingerprint) == artifact
    assert all(repo.get(ResearchSample, s).target_id for s in result.included_sample_ids)

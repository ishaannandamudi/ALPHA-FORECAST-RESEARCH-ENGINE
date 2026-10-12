"""Native research staging retains final service layout and all configured bounds."""

from dataclasses import replace

from afre.fusion import FusedForecast, FusionArtifact, FusionEngine
from afre.fusion.snapshots import frozen_copy as fusion_copy
from afre.selection.snapshots import frozen_copy as selection_copy
from afre.service import ServiceRepository
from tests.service.conftest import ServiceCase


def test_native_staging_preserves_final_layout(service_case: ServiceCase) -> None:
    repo = service_case.repo
    repo.model_bounds = replace(repo.model_bounds, predictions=17)
    repo.service_bounds = replace(repo.service_bounds, contexts=7)
    for create in (fusion_copy, lambda r: selection_copy(r, None)):
        with create(repo) as stage:
            assert isinstance(stage, ServiceRepository)
            assert stage.model_bounds == repo.model_bounds
            assert stage.service_bounds == repo.service_bounds
            assert stage.selection_bounds == repo.selection_bounds
            assert stage.fusion_bounds == repo.fusion_bounds
            assert stage._connection.execute("PRAGMA user_version").fetchone()[0] == 25
            stage._validate_layout()


def test_fusion_trial_pool_on_final_store(service_case: ServiceCase) -> None:
    c = service_case
    identity = c.fixture.context_cases[3][0]
    value = c.repo.get(FusedForecast, identity)
    model = c.repo.get(FusionArtifact, value.artifact_id)
    pool = FusionEngine(c.repo).trial_pool(((model.spec_id, (identity,)),))
    assert pool.plan_ids
    assert FusionEngine(c.repo).trial_pool(((model.spec_id, (identity,)),)) == pool

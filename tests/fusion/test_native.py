"""Actual native family, residual and independent real-hour/day integrations."""

from afre.fusion import FusedForecast, FusionArtifact, FusionEngine, FusionRepository
from afre.fusion.metadata import FusionMetadata
from afre.serialization import canonical_json
from examples.fusion_native import horizon_fixture, native_fixture


def test_all_actual_native_sources() -> None:
    with FusionRepository(":memory:") as repo:
        result = native_fixture(repo)
        assert {n for n, _ in result.outputs} == {
            "point",
            "gaussian",
            "calibrated",
            "event",
            "hard-regime",
            "mixture",
            "nonlinear",
            "sequence",
            "orthogonal",
        }
        for name, i in result.outputs:
            forecast = repo.resolve(FusedForecast, i)
            assert forecast.value is not None
            if name == "orthogonal":
                assert forecast.contributions[0].value == forecast.value
        law = repo.resolve(FusedForecast, result.probability_id).law
        assert law is not None and len(law.components) >= 3
        metadata = repo.resolve(FusionMetadata, result.metadata_id)
        point = repo.get(FusedForecast, metadata.forecast_id)
        artifact = repo.get(FusionArtifact, point.artifact_id)
        frozen = canonical_json(artifact)
        assert artifact.weights[0][1] == 1.0
        assert canonical_json(repo.resolve(FusionArtifact, point.artifact_id)) == frozen
        audit = FusionEngine(repo).audit(point.fingerprint)
        assert artifact.fingerprint in audit.node_ids


def test_actual_hour_day_remain_independent() -> None:
    with FusionRepository(":memory:") as repo:
        results = horizon_fixture(repo)
        assert {d for d, _ in results} == {3600 * 10**9, 86400 * 10**9}
        forecasts = tuple(repo.resolve(FusedForecast, i) for _, i in results)
        assert len({f.horizon_id for f in forecasts}) == 2
        assert len({f.target_id for f in forecasts}) == 2
        assert len({f.artifact_id for f in forecasts}) == 2

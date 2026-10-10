"""Monitor a completed AFRE20 decision after additive health migration."""

from pathlib import Path

from afre.health import HealthDiagnostic, HealthEngine, HealthRepository, ModelHealthSnapshot
from afre.selection import SelectionEngine, SelectionRepository
from afre.serialization import canonical_json
from afre.statistical_models import ModelEngine, PredictionScope
from afre.statistical_models.artifacts import FittedModelArtifact
from examples.health_native import declared_spec
from examples.selection_fixture import small_fixture


def selected_monitor(path: Path) -> tuple[ModelHealthSnapshot, str]:
    with SelectionRepository(path) as prior:
        fixture = small_fixture(prior)
        result, registry = SelectionEngine(prior).select(fixture.space, 100, 100)
        assert result.selected_model_id is not None
        outputs = ModelEngine(prior).predict_samples(
            result.selected_model_id,
            fixture.space.validation_sample_ids,
            PredictionScope.VALIDATION,
        )
        before = canonical_json(prior.get(FittedModelArtifact, result.selected_model_id))
    with HealthRepository(path) as repo:
        engine = HealthEngine(repo)
        ref = engine.monitor(result.fingerprint)
        rows = tuple(engine.observe(ref.fingerprint, p.fingerprint, 120) for p in outputs)
        spec, rules = declared_spec(
            repo,
            ref,
            rows,
            (HealthDiagnostic.PREDICTION_MEAN,),
            declaration=100,
            predeclared=False,
            context=(result.fingerprint, *(v.trial_id for v in registry.entries)),
        )
        engine.declare(spec, rules)
        snapshot = engine.evaluate(spec.fingerprint, 120)
        assert canonical_json(repo.get(FittedModelArtifact, result.selected_model_id)) == before
        return snapshot, before

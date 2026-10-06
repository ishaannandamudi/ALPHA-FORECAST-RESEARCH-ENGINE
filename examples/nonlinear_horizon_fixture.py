"""Independent nonlinear product research on actual 1h and 1d AFRE-8 architectures."""

from afre.cross_sectional.engine import CrossSectionEngine
from afre.nonlinear import (
    InteractionDefinition,
    InteractionSet,
    InteractionTransform,
    NonlinearEngine,
    NonlinearFamily,
    NonlinearForecast,
    NonlinearInput,
    NonlinearModelArtifact,
    NonlinearModelSpec,
    NonlinearRepository,
    ScalarFeatureDefinition,
    TransformParameters,
)
from afre.nonlinear.definitions import output_unit
from afre.regime_conditioned.artifacts import RegimeConditionedModel
from afre.regime_conditioned.definitions import RegimeConditioningSpec
from afre.research_datasets.schema import Partition
from afre.statistical_models.artifacts import FittedModelArtifact
from afre.statistical_models.definitions import BaselineModelSpec
from examples.nonlinear_demo import signal
from examples.regime_horizon_fixture import real_horizons


def horizon_interactions(
    repo: NonlinearRepository,
) -> tuple[tuple[NonlinearModelArtifact, tuple[NonlinearForecast, ...]], ...]:
    outputs = []
    engine = NonlinearEngine(repo)
    for native_model, _ in real_horizons(repo):
        assert isinstance(native_model, RegimeConditionedModel)
        native_spec = repo.get(RegimeConditioningSpec, native_model.spec_id)
        base = repo.get(FittedModelArtifact, native_spec.base_model_id)
        baseline = repo.get(BaselineModelSpec, base.spec_id)
        fold = repo.resolve_fold(baseline.fold_id)
        packets: dict[Partition, list[NonlinearInput]] = {
            Partition.TRAIN: [],
            Partition.VALIDATION: [],
        }
        features: tuple[ScalarFeatureDefinition, ...] = ()
        for partition in packets:
            for sample in repo.partition_samples(baseline.fold_id, partition):
                assert sample.origin is not None
                scalars = []
                for name, value in (
                    ("microstructure.hour-day", 1 + sample.timestamp_ns / 1e12),
                    ("context.hour-day", 2.0),
                ):
                    source = signal(sample, name, value)
                    CrossSectionEngine(repo).publish_external(source)
                    scalars.append(engine.scalar(source.fingerprint, sample.origin))
                features = tuple(s.definition for s in scalars)
                packets[partition].append(
                    engine.input(sample.fingerprint, tuple(s.fingerprint for s in scalars))
                )
        definition = InteractionDefinition(
            "micro-context",
            features,
            InteractionTransform.PRODUCT,
            TransformParameters(),
            "micro-context",
            output_unit(InteractionTransform.PRODUCT, features),
        )
        spec = NonlinearModelSpec(
            InteractionSet((definition,), baseline.target),
            NonlinearFamily.LINEAR_ON_INTERACTIONS,
            (),
            baseline.fold_id,
            fold.training_cutoff_ns,
            0,
            ridge_penalty=0.01,
        )
        at = fold.training_cutoff_ns
        matrix = engine.matrix(
            spec, tuple(p.fingerprint for p in packets[Partition.TRAIN]), (), at
        )
        model = engine.fit(spec, matrix.fingerprint, at, at, at)
        forecasts = tuple(
            engine.predict(model.fingerprint, p.fingerprint, p.origin.timestamp_ns)
            for p in packets[Partition.VALIDATION]
        )
        outputs.append((model, forecasts))
    return tuple(outputs)

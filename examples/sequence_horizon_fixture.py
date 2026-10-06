"""Separate sequence readouts on actual one-hour and one-day target contracts."""

from afre.cross_sectional.engine import CrossSectionEngine
from afre.nonlinear import NonlinearEngine
from afre.regime_conditioned.artifacts import RegimeConditionedModel
from afre.regime_conditioned.definitions import RegimeConditioningSpec
from afre.research_datasets.schema import Partition
from afre.sequence import (
    SequenceEngine,
    SequenceFamily,
    SequenceFeatureDefinition,
    SequenceForecast,
    SequenceModelArtifact,
    SequenceModelSpec,
    SequenceRepository,
    SequenceWindowMode,
    SequenceWindowSpec,
)
from afre.statistical_models.artifacts import FittedModelArtifact
from afre.statistical_models.definitions import BaselineModelSpec
from examples.nonlinear_demo import signal
from examples.regime_horizon_fixture import real_horizons


def horizon_sequences(
    repo: SequenceRepository,
) -> tuple[tuple[SequenceModelArtifact, tuple[SequenceForecast, ...]], ...]:
    outputs = []
    engine, neutral = SequenceEngine(repo), NonlinearEngine(repo)
    for native, _ in real_horizons(repo):
        assert isinstance(native, RegimeConditionedModel)
        conditioned = repo.get(RegimeConditioningSpec, native.spec_id)
        baseline = repo.get(
            BaselineModelSpec, repo.get(FittedModelArtifact, conditioned.base_model_id).spec_id
        )
        fold = repo.resolve_fold(baseline.fold_id)
        samples = {
            p: repo.partition_samples(baseline.fold_id, p)
            for p in (Partition.TRAIN, Partition.VALIDATION)
        }
        feature = None
        for partition in samples:
            for sample in samples[partition]:
                assert sample.origin is not None
                source = signal(
                    sample, "microstructure.hour-day", 1 + sample.timestamp_ns / 1e12
                )
                CrossSectionEngine(repo).publish_external(source)
                scalar = neutral.scalar(source.fingerprint, sample.origin)
                feature = SequenceFeatureDefinition(
                    scalar.definition.fingerprint,
                    "history.hour-day",
                    "1",
                    scalar.definition.unit,
                )
                engine.observation(feature, scalar.fingerprint)
        assert feature is not None
        window = SequenceWindowSpec(SequenceWindowMode.FIXED_OBSERVATION_COUNT, 3)
        spec = SequenceModelSpec(
            baseline.target,
            (feature,),
            window,
            SequenceFamily.EXPONENTIAL_DECAY_LINEAR,
            baseline.fold_id,
            fold.training_cutoff_ns,
            0,
            decay_rate_per_second=1e-6,
            ridge_penalty=0.01,
        )
        bindings = []
        for sample in samples[Partition.TRAIN]:
            assert sample.origin is not None
            snap = engine.snapshot(sample.origin, spec.features, window, spec.cutoff_ns)
            bindings.append((sample.fingerprint, snap.fingerprint))
        at = spec.cutoff_ns
        state = engine.fit_transform(spec, tuple(bindings), at, at, at)
        dataset = engine.dataset(spec, state.fingerprint, at)
        model = engine.fit(spec, dataset.fingerprint, at, at, at)
        forecasts = []
        for sample in samples[Partition.VALIDATION]:
            assert sample.origin is not None
            snap = engine.snapshot(sample.origin, spec.features, window, sample.timestamp_ns)
            forecasts.append(
                engine.predict(
                    model.fingerprint, sample.fingerprint, snap.fingerprint, sample.timestamp_ns
                )
            )
        outputs.append((model, tuple(forecasts)))
    return tuple(outputs)

"""Actual 1h/1d mixture contracts over the completed AFRE-8 horizon architecture."""

from afre.mixture import (
    ExpertKind,
    ExpertOutput,
    ExpertReference,
    MixtureEngine,
    MixtureForecast,
    MixtureRepository,
    MixtureRequest,
)
from afre.regime_conditioned.definitions import RegimeConditioningSpec
from afre.research_datasets.samples import ResearchSample
from afre.statistical_models.artifacts import FittedModelArtifact
from afre.statistical_models.definitions import BaselineModelSpec
from examples.cross_sectional_demo import provider_source
from examples.mixture_demo import external_binding, external_reference, fixed_gate
from examples.regime_horizon_fixture import real_horizons


def horizon_mixtures(repo: MixtureRepository) -> tuple[tuple[MixtureForecast, ...], ...]:
    outputs = []
    engine = MixtureEngine(repo)
    source = provider_source("AFRE")
    for model, forecasts in real_horizons(repo):
        spec = repo.get(RegimeConditioningSpec, model.spec_id)
        base = repo.get(FittedModelArtifact, spec.base_model_id)
        fold_id = repo.get(BaselineModelSpec, base.spec_id).fold_id
        native = ExpertReference(
            "real-regime",
            ExpertKind.AFRE_REGIME,
            "AFRE",
            source.provenance.source_version,
            "1.0",
            spec.target,
            model.fingerprint,
            ExpertOutput.POINT,
            model.available_ns,
            source,
        )
        external = external_reference(spec.target, ExpertKind.EXTERNAL_OPTIONS, "real-options")
        gate = fixed_gate(repo, (native, external))
        result = []
        for forecast in forecasts:
            binding = engine.bind(native.fingerprint, forecast.fingerprint)
            assert binding.sample_id is not None
            sample = repo.get(ResearchSample, binding.sample_id)
            external_id = external_binding(repo, external, sample, 0.01)
            request = MixtureRequest(
                gate.expert_set.fingerprint,
                gate.fingerprint,
                fold_id,
                sample.fingerprint,
                (
                    (native.fingerprint, binding.fingerprint),
                    (external.fingerprint, external_id),
                ),
                (),
                sample.timestamp_ns,
            )
            result.append(engine.forecast(request))
        outputs.append(tuple(result))
    assert outputs[0][0].request.gate_id != outputs[1][0].request.gate_id
    assert outputs[0][0].target_definition_id != outputs[1][0].target_definition_id
    return tuple(outputs)

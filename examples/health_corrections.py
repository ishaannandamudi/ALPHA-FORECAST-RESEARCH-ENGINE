"""Explicit native revisions preserve existing producer and snapshot bytes."""

from dataclasses import replace

from afre.fusion import (
    ExternalFusionDefinition,
    ExternalFusionOutput,
    FusedForecast,
    FusionEngine,
)
from afre.health import HealthRepository


def corrected_output(repo: HealthRepository, output_id: str) -> str:
    output = repo.get(FusedForecast, output_id)
    contribution = output.contributions[0]
    assert contribution.output_id is not None
    original = repo.get(ExternalFusionOutput, contribution.output_id)
    revised = replace(
        original, value=(original.value or 0) + 10.0, revision="health-correction"
    )
    definition = repo.get(ExternalFusionDefinition, original.definition_id)
    engine = FusionEngine(repo)
    engine.external(definition, (revised,))
    observation = engine.observe(contribution.source_id, revised.fingerprint)
    return engine.apply(
        output.artifact_id,
        output.sample_id,
        (observation.fingerprint,),
        output.origin.timestamp_ns,
    ).fingerprint

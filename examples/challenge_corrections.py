"""Synthetic native source revisions and honest later received truth corrections."""

from dataclasses import replace

from afre.challenger import ChallengeRepository, ShadowForecast
from afre.fusion import (
    ExternalFusionDefinition,
    ExternalFusionOutput,
    FusedForecast,
    FusionEngine,
)
from afre.probabilistic.artifacts import DistributionParameters
from afre.target_engine import TargetEngine
from afre.target_engine.builders import build_vintage
from afre.target_engine.market_data import TargetBar, TargetSourceBuild
from afre.target_engine.models import TargetVintage
from examples.feature_store_demo import clocks


def source_correction(repo: ChallengeRepository, shadow: ShadowForecast) -> str:
    source = repo.get(FusedForecast, shadow.source_id)
    raw_id = source.contributions[0].output_id
    assert raw_id is not None
    original = repo.get(ExternalFusionOutput, raw_id)
    assert isinstance(original.law, DistributionParameters) and original.value is not None
    corrected = replace(
        original,
        value=original.value + 0.2,
        law=replace(original.law, location=original.value + 0.2),
        revision="challenge-source-correction",
    )
    definition = repo.get(ExternalFusionDefinition, original.definition_id)
    engine = FusionEngine(repo)
    engine.external(definition, (corrected,))
    row = engine.observe(source.contributions[0].source_id, corrected.fingerprint)
    return engine.apply(
        source.artifact_id, source.sample_id, (row.fingerprint,), source.origin.timestamp_ns
    ).fingerprint


def truth_correction(repo: ChallengeRepository, truth_id: str) -> str:
    old = repo.get(TargetVintage, truth_id)
    assert old.endpoint_bar_id is not None
    endpoint = repo.get(TargetBar, old.endpoint_bar_id)
    assert endpoint.close is not None
    with repo.transaction():
        repo.put(
            replace(
                endpoint,
                close=endpoint.close + 1.0,
                predecessor_id=endpoint.fingerprint,
                clocks=clocks(121),
            )
        )
    source = repo.get(TargetSourceBuild, old.source_build_id)
    build = TargetEngine(repo).freeze_source(source.source, source.calendar, 122)
    corrected = build_vintage(repo, old.definition, old.origin, build, clocks(122), True)
    with repo.transaction():
        repo.put(corrected)
    return corrected.fingerprint

"""Exact neutral projections retain upstream clocks, revision identity and lineage."""

from typing import TYPE_CHECKING

from afre.cross_sectional.external import ExternalSignal
from afre.event_conditioned.events import EventReference
from afre.feature_store.models import FeatureVintage
from afre.mixture.artifacts import MixtureForecast
from afre.mixture.experts import (
    ExpertForecastBinding,
    ExternalExpertForecast,
    GatingFeatureReference,
)
from afre.nonlinear.artifacts import InteractionValue, ScalarInput
from afre.nonlinear.definitions import InteractionDefinition
from afre.regime_conditioned.regimes import RegimeSnapshot
from afre.schema import require
from afre.sequence.artifacts import SequenceObservation
from afre.sequence.definitions import SequenceFeatureDefinition
from afre.sequence.schema import SequenceObservationQuality

if TYPE_CHECKING:
    from afre.sequence.repository import SequenceRepository


def binding_ready(repo: "SequenceRepository", binding: ExpertForecastBinding) -> int:
    forecast = repo.get_any(binding.forecast_id)
    if isinstance(forecast, ExternalExpertForecast):
        return forecast.clocks.afre_computed_ns
    return binding.available_ns


def actual_ready(repo: "SequenceRepository", scalar: ScalarInput) -> int:
    upstream = repo.get_any(scalar.source_id)
    if isinstance(upstream, ExpertForecastBinding):
        return binding_ready(repo, upstream)
    if isinstance(upstream, MixtureForecast):
        ready = [upstream.request.computed_ns, upstream.available_ns]
        ready.extend(
            binding_ready(repo, repo.resolve(ExpertForecastBinding, identity))
            for _, identity in upstream.request.expert_inputs
            if identity is not None
        )
        for identity in upstream.request.gating_feature_ids:
            reference = repo.resolve(GatingFeatureReference, identity)
            source = repo.get_any(reference.source_id)
            require(
                isinstance(source, (FeatureVintage, ExternalSignal, RegimeSnapshot)),
                "closed gating processing clocks",
            )
            assert isinstance(source, (FeatureVintage, ExternalSignal, RegimeSnapshot))
            ready.append(source.clocks.afre_computed_ns)
        return max(ready)
    require(
        isinstance(upstream, (FeatureVintage, ExternalSignal, EventReference, RegimeSnapshot)),
        "closed source processing clocks",
    )
    assert isinstance(
        upstream, (FeatureVintage, ExternalSignal, EventReference, RegimeSnapshot)
    )
    return upstream.clocks.afre_computed_ns


def observation_for(
    repo: "SequenceRepository", feature: SequenceFeatureDefinition, source_id: str
) -> SequenceObservation:
    source = repo.get_any(source_id)
    repo._validate_links(source)
    if isinstance(source, ScalarInput):
        require(
            feature.source_definition_id == source.definition.fingerprint
            and feature.unit == source.definition.unit,
            "sequence exact scalar semantics/unit",
        )
        upstream = repo.get_any(source.source_id)
        if isinstance(upstream, FeatureVintage):
            timestamp = upstream.effective_ns
        elif isinstance(upstream, ExternalSignal):
            timestamp = upstream.as_of_ns
        elif isinstance(upstream, EventReference):
            require(
                upstream.occurrence_ns is not None,
                "event sequence requires exact occurrence time",
            )
            assert upstream.occurrence_ns is not None
            timestamp = upstream.occurrence_ns
        elif isinstance(upstream, RegimeSnapshot):
            timestamp = upstream.as_of_ns
        else:
            require(
                isinstance(upstream, (ExpertForecastBinding, MixtureForecast)),
                "closed neutral expert source",
            )
            timestamp = source.origin.timestamp_ns
        quality = SequenceObservationQuality.PRESENT
        if source.value is None:
            if isinstance(upstream, FeatureVintage):
                raw_quality = upstream.state.value
            else:
                require(
                    isinstance(
                        upstream,
                        (ExternalSignal, EventReference, RegimeSnapshot, ExpertForecastBinding),
                    ),
                    "missing neutral source quality",
                )
                assert isinstance(
                    upstream,
                    (ExternalSignal, EventReference, RegimeSnapshot, ExpertForecastBinding),
                )
                raw_quality = upstream.quality.value
            quality = {
                "stale": SequenceObservationQuality.STALE,
                "missing": SequenceObservationQuality.MISSING,
                "invalid": SequenceObservationQuality.INVALID,
            }.get(raw_quality, SequenceObservationQuality.WITHHELD)
        return SequenceObservation(
            feature.fingerprint,
            source.fingerprint,
            source.origin.instrument,
            timestamp,
            source.available_ns,
            source.value,
            source.value is None,
            source.source_id,
            actual_ready(repo, source),
            quality,
        )
    require(
        isinstance(source, InteractionValue),
        "sequence input must be neutral scalar or interaction",
    )
    assert isinstance(source, InteractionValue)
    definition = repo.resolve(InteractionDefinition, source.definition_id)
    require(
        feature.source_definition_id == definition.fingerprint
        and feature.unit == definition.unit,
        "sequence exact nonlinear definition/unit",
    )
    scalars = tuple(repo.resolve(ScalarInput, i) for i in source.input_ids)
    require(len({s.origin for s in scalars}) == 1, "nonlinear source origin agreement")
    return SequenceObservation(
        feature.fingerprint,
        source.fingerprint,
        scalars[0].origin.instrument,
        scalars[0].origin.timestamp_ns,
        source.available_ns,
        source.value,
        source.value is None,
        source.fingerprint,
        max(source.computed_ns, *(actual_ready(repo, scalar) for scalar in scalars)),
        SequenceObservationQuality.MISSING
        if source.value is None
        else SequenceObservationQuality.PRESENT,
    )


def source_attestors(repo: "SequenceRepository", value: SequenceObservation) -> tuple[str, ...]:
    source = repo.get_any(value.source_id)
    if isinstance(source, ScalarInput):
        return source.approved_attestors
    assert isinstance(source, InteractionValue)
    return tuple(
        sorted(
            {
                a
                for i in source.input_ids
                for a in repo.resolve(ScalarInput, i).approved_attestors
            }
        )
    )

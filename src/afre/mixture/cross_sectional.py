"""Explicit neutral score bridge into unchanged AFRE-9 ranking contracts."""

from dataclasses import replace
from typing import TYPE_CHECKING

from afre.cross_sectional.artifacts import CrossSectionRanking
from afre.cross_sectional.definitions import CrossSectionSpec, ScoreSpec, origin_context
from afre.cross_sectional.external import ExternalSignal
from afre.cross_sectional.schema import ScoreSource, SignalQuality
from afre.feature_store.models import AvailabilityEvidence, SourceReference
from afre.hashing import bytes_digest
from afre.lineage import ProvenanceRef
from afre.mixture.artifacts import MixtureForecast, MixtureRanking
from afre.schema import require
from afre.serialization import canonical_json

if TYPE_CHECKING:
    from afre.mixture.repository import MixtureRepository


def mixture_signal(forecast: MixtureForecast) -> ExternalSignal:
    source = SourceReference(
        ProvenanceRef(
            "AFRE-mixture",
            forecast.fingerprint,
            forecast.request.gate_id,
            bytes_digest(canonical_json(forecast).encode()),
        ),
        ProvenanceRef(
            "AFRE-mixture",
            "conditioned-score-dataset",
            forecast.request.expert_set_id,
            bytes_digest(forecast.request.expert_set_id.encode()),
        ).fingerprint,
    )
    at = forecast.available_ns
    return ExternalSignal(
        "AFRE-mixture",
        forecast.request.gate_id,
        "1.0",
        forecast.security,
        "derived.mixture_score",
        "1",
        "point-target-location:" + forecast.target_definition_id,
        forecast.origin.timestamp_ns,
        AvailabilityEvidence(at, at, at, at),
        forecast.value,
        "exact-target-unit:" + forecast.target_definition_id,
        SignalQuality.VALID,
        source,
    )


def ranking_spec(template: CrossSectionSpec, forecast: MixtureForecast) -> CrossSectionSpec:
    require(
        template.identity.target.fingerprint == forecast.target_definition_id,
        "mixture ranking target/horizon mismatch",
    )
    require(
        origin_context(template.identity.anchor_origin) == origin_context(forecast.origin),
        "mixture ranking full origin mismatch",
    )
    signal = mixture_signal(forecast)
    return replace(
        template,
        score=ScoreSpec(
            ScoreSource.EXTERNAL_SIGNAL,
            provider_name=signal.provider_name,
            provider_version=signal.provider_version,
            provider_schema=signal.provider_schema,
            signal_name=signal.signal_name,
            signal_version=signal.signal_version,
            signal_semantics=signal.signal_semantics,
            unit=signal.unit,
        ),
    )


def ranking_for(
    repo: "MixtureRepository", ranking_id: str, ids: tuple[str, ...]
) -> MixtureRanking:
    require(
        0 < len(ids) <= repo.mixture_bounds.forecasts and len(set(ids)) == len(ids),
        "mixture rank count",
    )
    forecasts = tuple(repo.resolve(MixtureForecast, i) for i in sorted(ids))
    ranking = repo.resolve(CrossSectionRanking, ranking_id)
    spec = repo.resolve(CrossSectionSpec, ranking.spec_id)
    require(
        all(
            f.request.gate_id == forecasts[0].request.gate_id and spec == ranking_spec(spec, f)
            for f in forecasts
        ),
        "mixture ranking comparable model/statistic",
    )
    require(
        len({f.security for f in forecasts}) == len(forecasts),
        "duplicate mixture ranking security",
    )
    expected = {f.security.fingerprint: mixture_signal(f).fingerprint for f in forecasts}
    from afre.cross_sectional.artifacts import CrossSectionObservation

    actual = {
        e.security.fingerprint: repo.resolve(
            CrossSectionObservation, e.observation_id
        ).source_id
        for e in ranking.entries
        if repo.resolve(CrossSectionObservation, e.observation_id).source_id is not None
    }
    require(actual == expected, "mixture rank exact forecast/signal source grid")
    return MixtureRanking(ranking_id, tuple(sorted(ids)), tuple(sorted(expected.values())))

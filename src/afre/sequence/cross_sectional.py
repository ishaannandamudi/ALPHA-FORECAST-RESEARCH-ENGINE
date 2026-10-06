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
from afre.schema import require
from afre.sequence.artifacts import SequenceForecast, SequenceRanking
from afre.serialization import canonical_json

if TYPE_CHECKING:
    from afre.sequence.repository import SequenceRepository


def sequence_signal(forecast: SequenceForecast) -> ExternalSignal:
    source = SourceReference(
        ProvenanceRef(
            "AFRE-sequence",
            forecast.fingerprint,
            forecast.model_id,
            bytes_digest(canonical_json(forecast).encode()),
        ),
        ProvenanceRef(
            "AFRE-sequence",
            "conditioned-score-dataset",
            forecast.spec_id,
            bytes_digest(forecast.spec_id.encode()),
        ).fingerprint,
    )
    at = forecast.available_ns
    return ExternalSignal(
        "AFRE-sequence",
        forecast.model_id,
        "1.0",
        forecast.security,
        "derived.sequence_score",
        "1",
        "point-target-location:" + forecast.target_definition_id,
        forecast.origin.timestamp_ns,
        AvailabilityEvidence(at, at, at, at),
        forecast.value,
        "exact-target-unit:" + forecast.target_definition_id,
        SignalQuality.VALID,
        source,
    )


def ranking_spec(template: CrossSectionSpec, forecast: SequenceForecast) -> CrossSectionSpec:
    require(
        template.identity.target.fingerprint == forecast.target_definition_id,
        "sequence ranking target/horizon mismatch",
    )
    require(
        origin_context(template.identity.anchor_origin) == origin_context(forecast.origin),
        "sequence ranking full origin mismatch",
    )
    signal = sequence_signal(forecast)
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
    repo: "SequenceRepository", ranking_id: str, ids: tuple[str, ...]
) -> SequenceRanking:
    require(
        0 < len(ids) <= repo.sequence_bounds.forecasts and len(set(ids)) == len(ids),
        "sequence rank count",
    )
    forecasts = tuple(repo.resolve(SequenceForecast, i) for i in sorted(ids))
    ranking = repo.resolve(CrossSectionRanking, ranking_id)
    spec = repo.resolve(CrossSectionSpec, ranking.spec_id)
    require(
        all(
            f.model_id == forecasts[0].model_id and spec == ranking_spec(spec, f)
            for f in forecasts
        ),
        "sequence ranking comparable model/statistic",
    )
    require(
        len({f.security for f in forecasts}) == len(forecasts),
        "duplicate sequence ranking security",
    )
    expected = {f.security.fingerprint: sequence_signal(f).fingerprint for f in forecasts}
    from afre.cross_sectional.artifacts import CrossSectionObservation

    actual = {
        e.security.fingerprint: repo.resolve(
            CrossSectionObservation, e.observation_id
        ).source_id
        for e in ranking.entries
        if repo.resolve(CrossSectionObservation, e.observation_id).source_id is not None
    }
    require(actual == expected, "sequence rank exact forecast/signal source grid")
    return SequenceRanking(ranking_id, tuple(sorted(ids)), tuple(sorted(expected.values())))

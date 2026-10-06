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
from afre.nonlinear.artifacts import NonlinearForecast, NonlinearRanking
from afre.schema import require
from afre.serialization import canonical_json

if TYPE_CHECKING:
    from afre.nonlinear.repository import NonlinearRepository


def nonlinear_signal(forecast: NonlinearForecast) -> ExternalSignal:
    source = SourceReference(
        ProvenanceRef(
            "AFRE-nonlinear",
            forecast.fingerprint,
            forecast.model_id,
            bytes_digest(canonical_json(forecast).encode()),
        ),
        ProvenanceRef(
            "AFRE-nonlinear",
            "conditioned-score-dataset",
            forecast.spec_id,
            bytes_digest(forecast.spec_id.encode()),
        ).fingerprint,
    )
    at = forecast.available_ns
    return ExternalSignal(
        "AFRE-nonlinear",
        forecast.model_id,
        "1.0",
        forecast.security,
        "derived.nonlinear_score",
        "1",
        "point-target-location:" + forecast.target_definition_id,
        forecast.origin.timestamp_ns,
        AvailabilityEvidence(at, at, at, at),
        forecast.value,
        "exact-target-unit:" + forecast.target_definition_id,
        SignalQuality.VALID,
        source,
    )


def ranking_spec(template: CrossSectionSpec, forecast: NonlinearForecast) -> CrossSectionSpec:
    require(
        template.identity.target.fingerprint == forecast.target_definition_id,
        "nonlinear ranking target/horizon mismatch",
    )
    require(
        origin_context(template.identity.anchor_origin) == origin_context(forecast.origin),
        "nonlinear ranking full origin mismatch",
    )
    signal = nonlinear_signal(forecast)
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
    repo: "NonlinearRepository", ranking_id: str, ids: tuple[str, ...]
) -> NonlinearRanking:
    require(
        0 < len(ids) <= repo.nonlinear_bounds.forecasts and len(set(ids)) == len(ids),
        "nonlinear rank count",
    )
    forecasts = tuple(repo.resolve(NonlinearForecast, i) for i in sorted(ids))
    ranking = repo.resolve(CrossSectionRanking, ranking_id)
    spec = repo.resolve(CrossSectionSpec, ranking.spec_id)
    require(
        all(
            f.model_id == forecasts[0].model_id and spec == ranking_spec(spec, f)
            for f in forecasts
        ),
        "nonlinear ranking comparable model/statistic",
    )
    require(
        len({f.security for f in forecasts}) == len(forecasts),
        "duplicate mixture ranking security",
    )
    expected = {f.security.fingerprint: nonlinear_signal(f).fingerprint for f in forecasts}
    from afre.cross_sectional.artifacts import CrossSectionObservation

    actual = {
        e.security.fingerprint: repo.resolve(
            CrossSectionObservation, e.observation_id
        ).source_id
        for e in ranking.entries
        if repo.resolve(CrossSectionObservation, e.observation_id).source_id is not None
    }
    require(actual == expected, "nonlinear rank exact forecast/signal source grid")
    return NonlinearRanking(ranking_id, tuple(sorted(ids)), tuple(sorted(expected.values())))

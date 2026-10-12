"""Offline illustrative consumer: explicit identity/clocks, no provider or trading imports."""

from dataclasses import dataclass

from afre.feature_store import (
    AvailabilityEvidence,
    FeatureVintage,
    RegisteredFeatureDefinition,
    SourceReference,
)
from afre.features import DataQuality, MissingState
from afre.service import (
    ForecastServiceProvider,
    ForecastSnapshot,
    ServiceStatus,
    StableSecurityId,
    VersionInfo,
    canonical_json,
    deserialize,
)


@dataclass(frozen=True)
class NeutralObservation:
    security: StableSecurityId
    effective_utc_ns: int
    value: float
    unit: str
    quality: DataQuality
    upstream_publication_utc_ns: int | None
    upstream_available_utc_ns: int | None
    observed_utc_ns: int
    ingested_utc_ns: int
    computed_utc_ns: int
    final_available_utc_ns: int


def adapt_observation(
    observation: NeutralObservation,
    feature: RegisteredFeatureDefinition,
    source: SourceReference,
) -> FeatureVintage:
    """Map an explicit stable ID; provider publication never substitutes for receipt."""
    if observation.unit != feature.definition.unit:
        raise ValueError("source unit does not match the declared feature")
    clocks = AvailabilityEvidence(
        observation.observed_utc_ns,
        observation.ingested_utc_ns,
        observation.computed_utc_ns,
        observation.final_available_utc_ns,
        observation.upstream_publication_utc_ns,
        observation.upstream_available_utc_ns,
    )
    return FeatureVintage(
        feature,
        observation.security.instrument,
        observation.effective_utc_ns,
        clocks,
        source,
        observation.value,
        MissingState.PRESENT,
        observation.quality,
    )


def consume(provider: ForecastServiceProvider, snapshot_id: str) -> ForecastSnapshot:
    versions = provider.get_version_info()
    if not isinstance(versions.value, VersionInfo) or versions.value.api != "1.0":
        raise ValueError("unsupported AFRE API")
    reply = provider.get_snapshot(snapshot_id)
    if reply.status is not ServiceStatus.AVAILABLE or not isinstance(
        reply.value, ForecastSnapshot
    ):
        raise ValueError("snapshot unavailable")
    assert deserialize(canonical_json(reply)) == reply
    snapshot = reply.value
    if snapshot.output.probability is not None:
        law = snapshot.output.probability
        if law.kind != "QUANTILES":
            probability = law.threshold_probability(0.0, "GT")
            assert 0.0 <= probability <= 1.0
    assert (
        provider.get_snapshot(snapshot_id, ("EXECUTION",)).status is ServiceStatus.UNAVAILABLE
    )
    return snapshot


def compare_correction(
    provider: ForecastServiceProvider, original_id: str, corrected_id: str
) -> tuple[ForecastSnapshot, ForecastSnapshot]:
    original, corrected = consume(provider, original_id), consume(provider, corrected_id)
    if original.snapshot_id == corrected.snapshot_id:
        raise ValueError("a correction must have a new immutable identity")
    assert consume(provider, original_id) == original
    return original, corrected

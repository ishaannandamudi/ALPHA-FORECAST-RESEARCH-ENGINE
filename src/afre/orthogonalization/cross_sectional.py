"""Explicit residual bridge to unchanged AFRE-9 PIT universe and historical group ranking."""

from dataclasses import replace
from typing import TYPE_CHECKING

from afre.cross_sectional.definitions import CrossSectionSpec, ScoreSpec, origin_context
from afre.cross_sectional.external import ExternalSignal
from afre.cross_sectional.schema import ScoreSource, SignalQuality
from afre.feature_store.models import AvailabilityEvidence, SourceReference
from afre.hashing import bytes_digest
from afre.lineage import ProvenanceRef
from afre.orthogonalization.artifacts import OrthogonalSignalValue
from afre.schema import require
from afre.serialization import canonical_json
from afre.universe.identity import StableSecurityId

if TYPE_CHECKING:
    from afre.orthogonalization.repository import OrthogonalizationRepository


def residual_signal(
    repo: "OrthogonalizationRepository", value: OrthogonalSignalValue
) -> ExternalSignal:
    from afre.research_datasets.samples import ResearchSample

    sample = repo.resolve(ResearchSample, value.sample_id)
    source = SourceReference(
        ProvenanceRef(
            "AFRE-orthogonalization",
            value.fingerprint,
            value.projection_id,
            bytes_digest(canonical_json(value).encode()),
        ),
        ProvenanceRef(
            "AFRE-orthogonalization",
            "orthogonal-score-dataset",
            value.projection_id,
            bytes_digest(value.projection_id.encode()),
        ).fingerprint,
    )
    security: StableSecurityId = sample.security
    return ExternalSignal(
        "AFRE-orthogonalization",
        value.projection_id,
        "1.0",
        security,
        "derived.orthogonal_signal",
        "1",
        "frozen-TRAIN-linear-residual:" + value.projection_id,
        value.origin.timestamp_ns,
        AvailabilityEvidence(
            value.available_ns, value.available_ns, value.computed_ns, value.available_ns
        ),
        value.residual,
        value.unit,
        SignalQuality.VALID if value.residual is not None else SignalQuality.MISSING,
        source,
    )


def ranking_spec(
    repo: "OrthogonalizationRepository",
    template: CrossSectionSpec,
    value: OrthogonalSignalValue,
) -> CrossSectionSpec:
    from afre.orthogonalization.artifacts import ProjectionArtifact
    from afre.orthogonalization.definitions import OrthogonalizationSpec

    projection = repo.resolve(ProjectionArtifact, value.projection_id)
    policy = repo.resolve(OrthogonalizationSpec, projection.spec_id)
    require(
        template.identity.target == policy.target
        and origin_context(template.identity.anchor_origin) == origin_context(value.origin),
        "orthogonal ranking exact target/horizon/full origin",
    )
    s = residual_signal(repo, value)
    return replace(
        template,
        score=ScoreSpec(
            ScoreSource.EXTERNAL_SIGNAL,
            provider_name=s.provider_name,
            provider_version=s.provider_version,
            provider_schema=s.provider_schema,
            signal_name=s.signal_name,
            signal_version=s.signal_version,
            signal_semantics=s.signal_semantics,
            unit=s.unit,
        ),
    )

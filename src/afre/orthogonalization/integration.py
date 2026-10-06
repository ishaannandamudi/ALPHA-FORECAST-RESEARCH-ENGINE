"""Caller-named AFRE-1 source-vintage export with exact transform identity and actual clocks."""

from afre.feature_store.models import (
    AvailabilityEvidence,
    FeatureVintage,
    RegisteredFeatureDefinition,
)
from afre.features import AvailabilityRule, DataQuality, MissingState
from afre.orthogonalization.artifacts import OrthogonalSignalValue
from afre.orthogonalization.cross_sectional import residual_signal
from afre.orthogonalization.repository import OrthogonalizationRepository
from afre.schema import require


def residual_vintage(
    repo: OrthogonalizationRepository, identity: str, definition: RegisteredFeatureDefinition
) -> FeatureVintage:
    with repo.feature_only(), repo.read_snapshot(), repo.validation_cache():
        value = repo.resolve(OrthogonalSignalValue, identity)
        source = residual_signal(repo, value).source
        require(
            definition.definition.unit == value.unit
            and definition.definition.transformation_version == value.projection_id
            and definition.definition.version == value.projection_id
            and definition.definition.availability_rule is AvailabilityRule.SOURCE_PUBLICATION,
            "export requires explicit caller definition pinning exact projection/unit",
        )
        return FeatureVintage(
            definition,
            value.origin.instrument,
            value.origin.timestamp_ns,
            AvailabilityEvidence(
                value.available_ns, value.available_ns, value.computed_ns, value.available_ns
            ),
            source,
            value.residual,
            MissingState.PRESENT if value.residual is not None else MissingState.MISSING,
            DataQuality.UNVERIFIED,
        )

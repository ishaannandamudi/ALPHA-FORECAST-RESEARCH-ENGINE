"""Exact native feature-grid observation; receipt semantics stay in the upstream join."""

from typing import TYPE_CHECKING, cast

from afre.feature_store.materialization import PointInTimeJoinResult
from afre.health.artifacts import HealthObservation
from afre.health.definitions import MonitoredArtifactReference
from afre.research_datasets.samples import ResearchSample
from afre.schema import require

if TYPE_CHECKING:
    from afre.health.repository import HealthRepository


def input_for(
    repo: "HealthRepository",
    ref: MonitoredArtifactReference,
    join_id: str,
    sample_id: str,
    constructed_ns: int,
) -> HealthObservation:
    join = repo.resolve(PointInTimeJoinResult, join_id)
    sample = repo.resolve(ResearchSample, sample_id)
    require(
        sample.origin == join.row.origin
        and sample.target_definition_id == ref.target_id
        and not sample.dropped,
        "health exact native feature/sample/origin",
    )
    quality = tuple(sorted({"input-grid", *("feature:" + a.state.value for a in join.audits)}))
    return HealthObservation(
        ref.fingerprint,
        join_id,
        sample.timestamp_ns,
        max((v.available_ns for v in join.row.features), default=sample.timestamp_ns),
        tuple(
            (
                v.definition.fingerprint,
                float(cast(float | int, v.value)) if type(v.value) in (float, int) else None,
            )
            for v in join.row.features
        ),
        "feature-definition-unit-grid-v1",
        quality,
        sample_id,
        sample.security.instrument.fingerprint,
        None,
        constructed_ns,
    )

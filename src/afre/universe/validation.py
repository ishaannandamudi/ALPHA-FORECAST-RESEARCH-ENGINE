"""Exact causal manifest projection and bounded provenance edges."""

from afre.datasets import UniverseManifest, UniverseMembership, UniversePolicy
from afre.forecast import ForecastOrigin
from afre.schema import Artifact, require
from afre.time import MAX_TIMESTAMP_NS, TimeRange
from afre.universe.definitions import UniverseDefinition
from afre.universe.membership import MembershipSelection
from afre.universe.models import (
    EligibilityResult,
    UniverseAudit,
    UniverseInputBuild,
    UniverseSnapshot,
)
from afre.universe.repository import RECORD_TYPES, evidence_of
from afre.universe.schema import EligibilityState, SnapshotCompleteness


def to_universe_manifest(snapshot: UniverseSnapshot) -> UniverseManifest:
    require(
        snapshot.completeness is SnapshotCompleteness.COMPLETE,
        "uncertain universe snapshot cannot become a causal dataset manifest",
    )
    require(
        snapshot.known_as_of_ns <= snapshot.valid_at_ns < MAX_TIMESTAMP_NS,
        "future knowledge cannot be projected into a historical origin",
    )
    members = tuple(
        UniverseMembership(
            value.membership.security.instrument,
            TimeRange(snapshot.valid_at_ns, snapshot.valid_at_ns + 1),
            snapshot.known_as_of_ns,
            snapshot.fingerprint,
        )
        for value in snapshot.eligibility
        if value.state is EligibilityState.ELIGIBLE
    )
    require(bool(members), "empty eligible universe cannot project to foundation manifest")
    return UniverseManifest(
        snapshot.definition.name,
        snapshot.fingerprint,
        snapshot.builder_version,
        UniversePolicy.POINT_IN_TIME,
        members,
    )


def validate_snapshot_origin(
    snapshot: UniverseSnapshot, manifest: UniverseManifest, origin: ForecastOrigin
) -> None:
    require(manifest == to_universe_manifest(snapshot), "snapshot/universe manifest mismatch")
    require(
        origin.timestamp_ns == snapshot.valid_at_ns
        and origin.availability_cutoff_ns == snapshot.known_as_of_ns
        and origin.universe_id == manifest.fingerprint
        and manifest.eligible(origin),
        "snapshot/security/origin compatibility mismatch",
    )


def lineage_edges(value: Artifact) -> tuple[str, ...]:
    if type(value) in RECORD_TYPES:
        evidence = evidence_of(value)
        edges: tuple[str, ...] = (evidence.source.fingerprint,)
        if evidence.predecessor_id is not None:
            edges += (evidence.predecessor_id,)
        return edges
    if isinstance(value, UniverseDefinition):
        return (value.source.fingerprint, value.calendar.fingerprint)
    if isinstance(value, MembershipSelection):
        return (
            value.definition_id,
            value.input_build_id,
            *value.record_ids,
            *value.future_record_ids,
            *((value.coverage_id,) if value.coverage_id else ()),
        )
    if isinstance(value, EligibilityResult):
        return (value.membership.fingerprint, *value.record_ids, *value.market_ids)
    if isinstance(value, UniverseSnapshot):
        return (
            value.definition.fingerprint,
            value.input_build_id,
            *(x.fingerprint for x in value.eligibility),
        )
    if isinstance(value, UniverseAudit):
        return (value.eligibility.fingerprint,)
    if isinstance(value, UniverseInputBuild):
        # The compact exact input manifest is retained; audits expand used evidence.
        return ()
    return ()

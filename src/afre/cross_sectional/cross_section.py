"""Frozen eligible grid and target-free causal ranking materialization."""

from typing import TYPE_CHECKING

from afre.cross_sectional.artifacts import (
    CrossSectionObservation,
    CrossSectionRanking,
    PeerState,
    RankEntry,
    RawScore,
)
from afre.cross_sectional.definitions import CrossSectionSpec
from afre.cross_sectional.groups import GroupMembership
from afre.cross_sectional.normalization import peer_state
from afre.cross_sectional.ranks import rank_values
from afre.cross_sectional.schema import (
    CrossSectionQuality,
    CrossSectionScoreState,
    MissingScorePolicy,
    PeerTransform,
    RankDirection,
    RankingLayer,
)
from afre.cross_sectional.scoring import score_for
from afre.schema import require
from afre.universe.models import UniverseSnapshot
from afre.universe.schema import EligibilityState, MembershipState
from afre.universe.validation import to_universe_manifest, validate_snapshot_origin

if TYPE_CHECKING:
    from afre.cross_sectional.repository import CrossSectionRepository


def eligible_grid(repo: "CrossSectionRepository", spec: CrossSectionSpec) -> UniverseSnapshot:
    snapshot = repo.resolve(UniverseSnapshot, spec.identity.snapshot_id)
    repo._validate_links(snapshot)
    origin = spec.identity.anchor_origin
    validate_snapshot_origin(snapshot, to_universe_manifest(snapshot), origin)
    require(
        spec.identity.eligibility_policy_id == snapshot.definition.eligibility.fingerprint,
        "cross-section eligibility policy mismatch",
    )
    require(
        len(snapshot.eligibility) <= repo.cross_section_bounds.securities,
        "cross-section universe security bound",
    )
    return snapshot


def ranking_for(
    repo: "CrossSectionRepository",
    spec: CrossSectionSpec,
    observations: tuple[CrossSectionObservation, ...],
    computed_ns: int,
) -> tuple[CrossSectionRanking, tuple[RawScore, ...], PeerState, PeerState | None]:
    snapshot = eligible_grid(repo, spec)
    eligible = {
        e.membership.security
        for e in snapshot.eligibility
        if e.state is EligibilityState.ELIGIBLE
        and e.membership.state is MembershipState.INCLUDED
    }
    require(
        len(observations) == len(eligible) and {o.security for o in observations} == eligible,
        "cross-section requires exact eligible grid; duplicates/ineligible/missing security",
    )
    require(
        computed_ns >= spec.identity.anchor_origin.timestamp_ns
        and computed_ns <= spec.identity.anchor_origin.availability_cutoff_ns,
        "causal ranking computation must be available at origin",
    )
    ordered = tuple(sorted(observations, key=lambda o: o.security.fingerprint))
    scores = tuple(score_for(repo, spec, o) for o in ordered)
    require(
        spec.missing is not MissingScorePolicy.FAIL_ON_MISSING
        or all(s.state is CrossSectionScoreState.AVAILABLE for s in scores),
        "missing score policy failed",
    )
    groups = tuple(repo.resolve(GroupMembership, o.group_id) for o in ordered if o.group_id)
    require(len({g.security for g in groups}) == len(groups), "duplicate group security")
    for observation in ordered:
        if observation.group_id:
            group = repo.resolve(GroupMembership, observation.group_id)
            repo.approved(group.clocks.historical_delivery, spec.approved_delivery_attestors)
            require(
                spec.group is not None
                and group.security == observation.security
                and group.matches(
                    spec.group,
                    observation.origin.timestamp_ns,
                    observation.origin.availability_cutoff_ns,
                ),
                "group not PIT valid/available or wrong taxonomy/security",
            )
    require(
        len({g.group_id for g in groups}) <= repo.cross_section_bounds.groups,
        "cross-section group bound",
    )
    normalized = peer_state(spec, scores, computed_ns)
    neutral = peer_state(spec, scores, computed_ns, groups, True) if spec.group else None
    raw_map = {s.security.fingerprint: s.value for s in scores if s.value is not None}
    global_map = dict(normalized.values)
    group_map = dict(neutral.values) if neutral else {}
    selection = (
        raw_map
        if spec.ranking_layer is RankingLayer.RAW
        else global_map
        if spec.ranking_layer is RankingLayer.NORMALIZED
        else group_map
    )
    quality = normalized.quality
    if len(raw_map) < spec.normalization.minimum_count:
        selection = {}
    if len(selection) < spec.normalization.minimum_count:
        if quality is CrossSectionQuality.VALID:
            quality = (
                CrossSectionQuality.TOO_SMALL if selection else CrossSectionQuality.UNAVAILABLE
            )
        selection = {}
    missing_fraction = (1 - len(selection) / len(ordered)) if ordered else 1.0
    if missing_fraction > spec.maximum_missing_fraction:
        quality, selection = CrossSectionQuality.EXCESSIVE_MISSINGNESS, {}
    # Percentile transform already encodes the declared best direction.
    direction = (
        RankDirection.HIGHER_BETTER
        if spec.ranking_layer is RankingLayer.NORMALIZED
        and spec.normalization.transform is PeerTransform.PERCENTILE
        else spec.direction
    )
    ranked = {
        k: (r, p) for k, r, p in rank_values(tuple(selection.items()), direction, spec.ties)
    }
    entries = tuple(
        RankEntry(
            o.security,
            o.fingerprint,
            s.fingerprint,
            s.value,
            global_map.get(o.security.fingerprint),
            group_map.get(o.security.fingerprint),
            ranked.get(o.security.fingerprint, (None, None))[0],
            ranked.get(o.security.fingerprint, (None, None))[1],
            s.state
            if o.security.fingerprint in ranked
            or s.state is not CrossSectionScoreState.AVAILABLE
            else CrossSectionScoreState.GROUP_UNAVAILABLE
            if spec.ranking_layer is RankingLayer.GROUP_NEUTRAL
            else CrossSectionScoreState.UNSUPPORTED,
            s.reason
            if o.security.fingerprint in ranked
            or s.state is not CrossSectionScoreState.AVAILABLE
            else "peer-transform-unavailable-or-quality-policy",
        )
        for o, s in zip(ordered, scores, strict=True)
    )
    count = len(ranked)
    ranking = CrossSectionRanking(
        spec.fingerprint,
        entries,
        normalized.fingerprint,
        neutral.fingerprint if neutral else None,
        len(ordered),
        count,
        count / len(ordered) if ordered else 0.0,
        quality,
        computed_ns,
        computed_ns,
    )
    return ranking, scores, normalized, neutral

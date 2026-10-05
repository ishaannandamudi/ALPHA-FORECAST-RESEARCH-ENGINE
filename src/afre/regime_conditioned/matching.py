"""Explicit reference sets, exact PIT scope and fail-closed selection/replay."""

from typing import TYPE_CHECKING

from afre.cross_sectional.groups import GroupMembership
from afre.regime_conditioned.artifacts import (
    RegimeConditionedSample,
    RegimeMatchSet,
    RegimeTransition,
)
from afre.regime_conditioned.definitions import RegimeConditioningSpec
from afre.regime_conditioned.regimes import RegimeSnapshot, RegimeTaxonomy
from afre.regime_conditioned.schema import (
    RegimeMatchPolicy,
    RegimeQuality,
    RegimeScope,
    RegimeStateSemantics,
)
from afre.regime_conditioned.transitions import transition_for
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.research_datasets.splits import FoldMembership
from afre.schema import require
from afre.statistical_models.artifacts import FittedModelArtifact
from afre.statistical_models.definitions import BaselineModelSpec
from afre.statistical_models.schema import PredictionScope
from afre.universe.models import UniverseSnapshot
from afre.universe.schema import EligibilityState, MembershipState
from afre.universe.validation import to_universe_manifest, validate_snapshot_origin

if TYPE_CHECKING:
    from afre.regime_conditioned.repository import RegimeRepository


def base_context(repo: "RegimeRepository", spec: RegimeConditioningSpec) -> BaselineModelSpec:
    model = repo.resolve(FittedModelArtifact, spec.base_model_id)
    base = repo.resolve(BaselineModelSpec, model.spec_id)
    require(base.target == spec.target, "regime base target/horizon mismatch")
    repo.resolve(RegimeTaxonomy, spec.taxonomy_id)
    if spec.event_model_id:
        from afre.event_conditioned.artifacts import EventConditionedModel
        from afre.event_conditioned.definitions import EventConditioningSpec

        event = repo.resolve(EventConditionedModel, spec.event_model_id)
        event_spec = repo.resolve(EventConditioningSpec, event.spec_id)
        require(
            event_spec.base_model_id == spec.base_model_id
            and event_spec.window.target == spec.target,
            "regime event composition compatibility",
        )
    return base


def sample_scope(
    repo: "RegimeRepository", spec: RegimeConditioningSpec, sample_id: str
) -> PredictionScope:
    rows = repo._connection.execute(
        "SELECT fingerprint FROM r_memberships WHERE fold_id=? AND sample_id=?",
        (base_context(repo, spec).fold_id, sample_id),
    ).fetchall()
    require(len(rows) == 1, "regime sample outside exact fold")
    partition = repo.resolve(FoldMembership, rows[0][0]).partition
    scopes = {
        Partition.TRAIN: PredictionScope.IN_SAMPLE,
        Partition.VALIDATION: PredictionScope.VALIDATION,
        Partition.TEST: PredictionScope.TEST,
    }
    require(partition in scopes, "regime sample purged/embargoed/ineligible")
    return scopes[partition]


def subject_matches(
    repo: "RegimeRepository",
    snapshot: RegimeSnapshot,
    sample: ResearchSample,
    mappings: tuple[str, ...],
    approved: tuple[str, ...],
) -> bool:
    assert sample.origin is not None
    subject, origin = snapshot.subject, sample.origin
    if subject.scope is RegimeScope.GLOBAL:
        return True
    if subject.scope is RegimeScope.SECURITY:
        return subject.security == sample.security
    if subject.scope is RegimeScope.MARKET:
        return (
            repo.resolve(UniverseSnapshot, sample.snapshot_id).definition.fingerprint
            == subject.universe_definition_id
        )
    if subject.scope is RegimeScope.SECTOR:
        matches = []
        for identity in mappings:
            group = repo.resolve(GroupMembership, identity)
            repo.approved(group.clocks.historical_delivery, approved)
            assert subject.group_policy is not None
            if group.security == sample.security and group.matches(
                subject.group_policy, origin.timestamp_ns, origin.availability_cutoff_ns
            ):
                matches.append(group)
        require(len(matches) <= 1, "ambiguous PIT regime sector membership")
        return bool(matches and matches[0].group_id == subject.group_id)
    return False


def matching_for(
    repo: "RegimeRepository",
    spec: RegimeConditioningSpec,
    sample_id: str,
    ids: tuple[str, ...],
    mappings: tuple[str, ...],
) -> RegimeMatchSet:
    require(
        len(ids) <= repo.regime_bounds.snapshots
        and len(mappings) <= repo.regime_bounds.samples,
        "regime matching input bound",
    )
    require(
        len(set(ids)) == len(ids) and len(set(mappings)) == len(mappings),
        "duplicate regime matching input",
    )
    sample = repo.resolve(ResearchSample, sample_id)
    require(
        sample.origin is not None and sample.target_definition_id == spec.target.fingerprint,
        "regime sample exact origin/target",
    )
    assert sample.origin is not None
    sample_scope(repo, spec, sample_id)
    universe = repo.resolve(UniverseSnapshot, sample.snapshot_id)
    repo._validate_links(universe)
    validate_snapshot_origin(universe, to_universe_manifest(universe), sample.origin)
    require(
        any(
            e.membership.security == sample.security
            and e.state is EligibilityState.ELIGIBLE
            and e.membership.state is MembershipState.INCLUDED
            for e in universe.eligibility
        ),
        "regime sample not PIT eligible",
    )
    for identity in mappings:
        repo.resolve(GroupMembership, identity)
    admissible, excluded = [], []
    for identity in sorted(ids):
        value = repo.resolve(RegimeSnapshot, identity)
        repo._validate_links(value)
        reason = None
        if (
            value.taxonomy.fingerprint != spec.taxonomy_id
            or value.subject.scope is not spec.scope
        ):
            reason = "taxonomy-or-scope-mismatch"
        elif value.subject.scope in (RegimeScope.VENUE, RegimeScope.CUSTOM):
            reason = "unsupported-scope"
        elif not subject_matches(
            repo, value, sample, mappings, spec.approved_delivery_attestors
        ):
            reason = "subject-mismatch"
        elif value.semantics is not RegimeStateSemantics.FILTERED:
            reason = "unsupported-retrospective-state"
        elif value.quality is not RegimeQuality.VALID:
            reason = value.quality.value
        elif value.membership.kind not in spec.allowed_memberships:
            reason = "unsupported-membership"
        elif value.as_of_ns > sample.origin.timestamp_ns:
            reason = "future-observation"
        elif value.clocks.final_available_ns > sample.origin.availability_cutoff_ns:
            reason = "not-received-or-available-at-origin"
        elif sample.origin.timestamp_ns - value.as_of_ns > spec.maximum_age_ns:
            reason = "stale"
        else:
            repo.approved(value.clocks.historical_delivery, spec.approved_delivery_attestors)
        if reason:
            excluded.append((identity, reason))
        else:
            admissible.append(value)
    selectable = [
        s
        for s in admissible
        if spec.matching is not RegimeMatchPolicy.EXACT_AS_OF
        or s.as_of_ns == sample.origin.timestamp_ns
    ]
    if spec.matching in (RegimeMatchPolicy.EXACT_AS_OF, RegimeMatchPolicy.FAIL_ON_MULTIPLE):
        require(len(selectable) <= 1, "multiple admissible regime snapshots")
    selectable.sort(key=lambda s: (s.clocks.final_available_ns, s.as_of_ns), reverse=True)
    if len(selectable) > 1:
        a, b = selectable[:2]
        require(
            (a.clocks.final_available_ns, a.as_of_ns)
            != (b.clocks.final_available_ns, b.as_of_ns),
            "ambiguous latest regime revision",
        )
    selected = selectable[0].fingerprint if selectable else None
    reasons = {reason for _, reason in excluded}
    state = (
        "matched"
        if selected
        else "stale"
        if "stale" in reasons
        else "invalid"
        if "invalid" in reasons
        else "unsupported"
        if any(r.startswith("unsupported") for r in reasons)
        else "unmatched"
    )
    return RegimeMatchSet(
        spec.fingerprint,
        sample_id,
        ids,
        mappings,
        selected,
        tuple(s.fingerprint for s in admissible),
        tuple(excluded),
        state,
    )


def observation_for(
    repo: "RegimeRepository", match: RegimeMatchSet
) -> tuple[RegimeConditionedSample, tuple[RegimeTransition, ...]]:
    spec = repo.resolve(RegimeConditioningSpec, match.spec_id)
    sample = repo.resolve(ResearchSample, match.sample_id)
    assert sample.origin is not None
    selected = repo.resolve(RegimeSnapshot, match.selected_id) if match.selected_id else None
    transitions: tuple[RegimeTransition, ...] = ()
    duration = None
    status = "unknown"
    if selected:
        supplied = tuple(
            s
            for i in match.admissible_ids
            if (s := repo.resolve(RegimeSnapshot, i)).subject == selected.subject
            and s.as_of_ns <= selected.as_of_ns
        )
        revisions: dict[int, RegimeSnapshot] = {}
        for s in sorted(supplied, key=lambda s: (s.as_of_ns, s.clocks.final_available_ns)):
            previous = revisions.get(s.as_of_ns)
            require(
                previous is None
                or previous.clocks.final_available_ns != s.clocks.final_available_ns,
                "ambiguous consecutive regime history",
            )
            revisions[s.as_of_ns] = s
        history = [revisions[at] for at in sorted(revisions)]
        require(history[-1] == selected, "selected regime not terminal supplied history")
        transitions = tuple(
            transition_for(a, b) for a, b in zip(history, history[1:], strict=False)
        )
        require(len(transitions) <= repo.regime_bounds.transitions, "regime transition bound")
        require(
            all(t.available_ns <= sample.origin.availability_cutoff_ns for t in transitions),
            "future transition knowledge",
        )
        changed = [t for t in transitions if t.changed]
        status = (
            "transition"
            if changed and changed[-1].transition_ns == sample.origin.timestamp_ns
            else "recent"
            if changed
            and sample.origin.timestamp_ns - changed[-1].transition_ns
            <= spec.transition_recent_ns
            else "stable"
            if transitions
            else "unknown"
        )
        duration = sample.origin.timestamp_ns - (
            changed[-1].transition_ns if changed else history[0].as_of_ns
        )
    return RegimeConditionedSample(
        match.fingerprint,
        spec.fingerprint,
        sample.fingerprint,
        sample.security,
        sample.origin,
        sample.snapshot_id,
        match.selected_id,
        selected.membership if selected else None,
        sample.target_id,
        sample.target_available_ns,
        sample_scope(repo, spec, sample.fingerprint),
        match.state,
        tuple(t.fingerprint for t in transitions),
        duration,
        status,
    ), transitions

"""Exact reference matching with causal evidence and honest later construction clocks."""

from typing import TYPE_CHECKING

from afre.cross_sectional.groups import GroupMembership
from afre.cross_sectional.schema import SignalQuality
from afre.event_conditioned.events import EventReference
from afre.event_conditioned.matching import subject_matches as event_subject_matches
from afre.event_conditioned.windows import window_distance
from afre.invariance.artifacts import EnvironmentMembership, NeutralEnvironmentLabel
from afre.invariance.definitions import EnvironmentDefinition, EnvironmentSet
from afre.invariance.schema import EnvironmentRule, EnvironmentState
from afre.regime_conditioned.matching import subject_matches as regime_subject_matches
from afre.regime_conditioned.regimes import RegimeSnapshot, RegimeTaxonomy
from afre.regime_conditioned.schema import (
    RegimeMembershipKind,
    RegimeQuality,
    RegimeStateSemantics,
)
from afre.research_datasets.samples import ResearchSample
from afre.schema import require
from afre.universe.models import UniverseSnapshot
from afre.universe.schema import EligibilityState, MembershipState
from afre.universe.validation import to_universe_manifest, validate_snapshot_origin

if TYPE_CHECKING:
    from afre.invariance.repository import InvarianceRepository


def sample_for(repo: "InvarianceRepository", sample_id: str) -> ResearchSample:
    s = repo.resolve(ResearchSample, sample_id)
    require(
        s.origin is not None and not s.dropped, "environment requires admitted exact origin"
    )
    assert s.origin is not None
    snapshot = repo.resolve(UniverseSnapshot, s.snapshot_id)
    validate_snapshot_origin(snapshot, to_universe_manifest(snapshot), s.origin)
    require(
        any(
            e.membership.security == s.security
            and e.state is EligibilityState.ELIGIBLE
            and e.membership.state is MembershipState.INCLUDED
            for e in snapshot.eligibility
        ),
        "environment PIT eligible security",
    )
    return s


def validate_definition(repo: "InvarianceRepository", d: EnvironmentDefinition) -> None:
    repo.get_any(d.target.fingerprint)
    if d.taxonomy_id:
        t = repo.resolve(RegimeTaxonomy, d.taxonomy_id)
        require(
            d.state_label in t.states and d.provider == t.provider.provider,
            "environment exact regime taxonomy/provider/state",
        )
    if d.universe_definition_id:
        repo.get_any(d.universe_definition_id)
    for identity in d.component_ids:
        c = repo.resolve(EnvironmentDefinition, identity)
        require(
            c.target == d.target and c.declared_ns <= d.declared_ns and not c.component_ids,
            "compound compatible predeclared base",
        )


def validate_set(repo: "InvarianceRepository", value: EnvironmentSet) -> None:
    b = repo.invariance_bounds
    require(
        len(value.definitions) <= b.environments
        and sum(bool(d.component_ids) for d in value.definitions) <= b.compounds
        and sum(d.window is not None for d in value.definitions) <= b.windows,
        "environment/window/compound repository bound",
    )
    require(
        all(repo.resolve(EnvironmentDefinition, d.fingerprint) == d for d in value.definitions),
        "persisted environment set",
    )


def membership_for(
    repo: "InvarianceRepository",
    environment_id: str,
    sample_id: str,
    source_ids: tuple[str, ...],
    mapping_ids: tuple[str, ...],
    constructed_ns: int,
) -> EnvironmentMembership:
    require(
        len(source_ids) + len(mapping_ids) <= repo.invariance_bounds.samples
        and len(set(source_ids)) == len(source_ids)
        and len(set(mapping_ids)) == len(mapping_ids),
        "membership input bound/duplicates",
    )
    d = repo.resolve(EnvironmentDefinition, environment_id)
    s = sample_for(repo, sample_id)
    assert s.origin is not None
    origin = s.origin
    require(s.target_definition_id == d.target.fingerprint, "environment sample target/horizon")
    cutoff = origin.availability_cutoff_ns
    weight, soft, reason, evidence_ns = 0.0, False, "outside-declared-environment", 0
    selected: tuple[str, ...] = ()
    unavailable = False
    rule = d.rule
    if rule is EnvironmentRule.TIME:
        require(
            not source_ids and not mapping_ids, "time environment has no external predicate"
        )
        assert d.window is not None
        weight = float(d.window.contains(origin.timestamp_ns))
    elif rule is EnvironmentRule.UNIVERSE:
        require(not source_ids and not mapping_ids, "universe uses exact admitted snapshot")
        u = repo.resolve(UniverseSnapshot, s.snapshot_id)
        weight = float(u.definition.fingerprint == d.universe_definition_id)
        evidence_ns = u.known_as_of_ns
    elif rule is EnvironmentRule.GROUP:
        require(not mapping_ids, "group exact sources only")
        assert d.group_policy is not None
        groups = tuple(repo.resolve(GroupMembership, i) for i in source_ids)
        matches = tuple(
            g
            for g in groups
            if g.security == s.security
            and g.matches(d.group_policy, origin.timestamp_ns, cutoff)
        )
        require(len(matches) <= 1, "ambiguous PIT classification; supply exact vintage")
        if matches:
            g = matches[0]
            repo.approved(g.clocks.historical_delivery, d.approved_delivery_attestors)
            weight = float(g.group_id == d.group_id)
            selected, evidence_ns = (g.fingerprint,), g.clocks.final_available_ns
        else:
            unavailable, reason = True, "group-not-known-at-origin"
    elif rule is EnvironmentRule.REGIME_STATE:
        candidates = []
        for identity in source_ids:
            v = repo.resolve(RegimeSnapshot, identity)
            require(
                v.semantics is RegimeStateSemantics.FILTERED,
                "retrospective regime cannot define causal membership",
            )
            if (
                v.taxonomy.fingerprint == d.taxonomy_id
                and v.membership.kind is d.membership_kind
                and v.quality is RegimeQuality.VALID
                and v.as_of_ns <= origin.timestamp_ns
                and origin.timestamp_ns - v.as_of_ns <= d.maximum_age_ns
                and v.clocks.final_available_ns <= cutoff
                and regime_subject_matches(
                    repo, v, s, mapping_ids, d.approved_delivery_attestors
                )
            ):
                repo.approved(v.clocks.historical_delivery, d.approved_delivery_attestors)
                candidates.append(v)
        candidates.sort(key=lambda v: (v.clocks.final_available_ns, v.as_of_ns, v.fingerprint))
        if candidates:
            v = candidates[-1]
            require(
                len(candidates) == 1
                or (candidates[-2].clocks.final_available_ns, candidates[-2].as_of_ns)
                != (v.clocks.final_available_ns, v.as_of_ns),
                "ambiguous regime revision",
            )
            assert d.state_label is not None
            weight = v.membership.weights[v.membership.states.index(d.state_label)]
            soft = v.membership.kind is RegimeMembershipKind.SOFT
            selected, evidence_ns = (v.fingerprint,), v.clocks.final_available_ns
        else:
            unavailable, reason = True, "regime-not-known-at-origin"
    elif rule is EnvironmentRule.EVENT_COHORT:
        assert d.event_window is not None
        event_candidates = []
        for identity in source_ids:
            e = repo.resolve(EventReference, identity)
            if not (
                e.provider == d.provider
                and e.event_class in d.event_classes
                and e.quality is SignalQuality.VALID
                and e.clocks.final_available_ns <= cutoff
                and event_subject_matches(
                    repo, e, s, mapping_ids, d.approved_delivery_attestors
                )
                and window_distance(e, d.event_window, origin.timestamp_ns) is not None
            ):
                continue
            repo.approved(e.clocks.historical_delivery, d.approved_delivery_attestors)
            require(
                e.clocks.historical_delivery is None
                or e.clocks.historical_delivery.entity == s.security.instrument,
                "event qualified delivery entity",
            )
            at, valid = e.clocks.final_available_ns, True
            for criterion in d.event_value_rules:
                attribute = getattr(e, criterion.key)
                if attribute is None:
                    valid = False
                    continue
                clocks = (
                    (attribute.actual.clocks, attribute.expected.clocks)
                    if criterion.key == "surprise"
                    else (attribute.clocks,)
                )
                for c in clocks:
                    repo.approved(c.historical_delivery, d.approved_delivery_attestors)
                    require(
                        c.historical_delivery is None
                        or c.historical_delivery.entity == s.security.instrument,
                        "event attribute qualified entity",
                    )
                when = (
                    attribute.available_ns
                    if criterion.key == "surprise"
                    else attribute.clocks.final_available_ns
                )
                valid = (
                    valid
                    and attribute.semantic_key == criterion.semantic_key
                    and when <= cutoff
                    and (criterion.minimum is None or attribute.value >= criterion.minimum)
                    and (criterion.maximum is None or attribute.value <= criterion.maximum)
                )
                at = max(at, when)
            if valid:
                event_candidates.append((e.fingerprint, at))
        selected = tuple(i for i, _ in event_candidates)
        weight, evidence_ns = (
            float(bool(event_candidates)),
            max((at for _, at in event_candidates), default=0),
        )
    elif rule is EnvironmentRule.QUALITY:
        from afre.invariance.forecasts import forecast_source

        require(
            len(source_ids) == 1 and not mapping_ids, "quality requires exact forecast evidence"
        )
        f = forecast_source(repo, source_ids[0])
        require(
            f.sample_id == s.fingerprint and f.origin == origin and f.available_ns <= cutoff,
            "quality evidence causal exact sample",
        )
        weight = float(d.quality_label in f.quality)
        selected, evidence_ns = source_ids, f.available_ns
    elif rule is EnvironmentRule.LABEL:
        require(len(source_ids) <= 1 and not mapping_ids, "neutral label exact single revision")
        if source_ids:
            label = repo.resolve(NeutralEnvironmentLabel, source_ids[0])
            require(
                label.sample_id == sample_id and label.origin == origin,
                "neutral label sample/origin",
            )
            if (
                label.provider == d.provider
                and label.version == d.version
                and label.clocks.final_available_ns <= cutoff
                and label.validity.start_ns <= origin.timestamp_ns < label.validity.end_ns
            ):
                repo.approved(label.clocks.historical_delivery, d.approved_delivery_attestors)
                selected, evidence_ns = source_ids, label.clocks.final_available_ns
                weight = float(label.label == d.neutral_label)
            else:
                unavailable, reason = True, "label-not-known-or-compatible-at-origin"
        else:
            unavailable, reason = True, "label-unavailable"
    else:
        require(not mapping_ids and len(source_ids) == 2, "compound exact two memberships")
        parts = tuple(repo.resolve(EnvironmentMembership, i) for i in source_ids)
        require(
            {m.environment_id for m in parts} == set(d.component_ids)
            and all(m.sample_id == sample_id and m.origin == origin for m in parts),
            "compound exact base/sample",
        )
        # Only one component is a regime; this is a conditional cohort weight, not independence.
        soft = any(m.soft for m in parts)
        weight = parts[0].weight * parts[1].weight
        unavailable = any(m.state is EnvironmentState.UNAVAILABLE for m in parts)
        selected = source_ids
        evidence_ns = max(m.evidence_available_ns for m in parts)
        require(
            constructed_ns >= max(m.constructed_ns for m in parts),
            "compound actual construction order",
        )
    state = (
        EnvironmentState.INCLUDED
        if weight > 0
        else EnvironmentState.UNAVAILABLE
        if unavailable
        else EnvironmentState.EXCLUDED
    )
    reason = (
        "declared-soft-weight"
        if weight > 0 and soft
        else "declared-hard-match"
        if weight > 0
        else reason
    )
    return EnvironmentMembership(
        environment_id,
        sample_id,
        origin,
        source_ids,
        mapping_ids,
        selected,
        state,
        weight,
        soft,
        reason,
        evidence_ns,
        constructed_ns,
        max(constructed_ns, evidence_ns, d.declared_ns),
    )

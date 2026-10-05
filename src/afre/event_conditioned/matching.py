"""Bounded exact-reference matching; historical subjects and every exclusion are pinned."""

from typing import TYPE_CHECKING

from afre.cross_sectional.external import ExternalSignal
from afre.cross_sectional.groups import GroupMembership
from afre.cross_sectional.schema import SignalQuality
from afre.event_conditioned.artifacts import EventConditionedObservation, EventMatchSet
from afre.event_conditioned.definitions import EventConditioningSpec
from afre.event_conditioned.events import EventReference
from afre.event_conditioned.schema import EventOverlapPolicy, EventRelation, EventScope
from afre.event_conditioned.windows import event_anchor, window_distance
from afre.feature_store.models import AvailabilityEvidence
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.schema import require
from afre.statistical_models.artifacts import FittedModelArtifact
from afre.statistical_models.definitions import BaselineModelSpec
from afre.statistical_models.schema import PredictionScope
from afre.universe.models import UniverseSnapshot
from afre.universe.schema import EligibilityState, MembershipState
from afre.universe.securities import SecurityRecord
from afre.universe.validation import to_universe_manifest, validate_snapshot_origin

if TYPE_CHECKING:
    from afre.event_conditioned.repository import EventRepository


def base_context(repo: "EventRepository", spec: EventConditioningSpec) -> BaselineModelSpec:
    model = repo.resolve(FittedModelArtifact, spec.base_model_id)
    base = repo.resolve(BaselineModelSpec, model.spec_id)
    require(base.target == spec.window.target, "event base target/horizon mismatch")
    return base


def sample_scope(
    repo: "EventRepository", spec: EventConditioningSpec, sample_id: str
) -> PredictionScope:
    base = base_context(repo, spec)
    rows = repo._connection.execute(
        "SELECT fingerprint FROM r_memberships WHERE fold_id=? AND sample_id=?",
        (base.fold_id, sample_id),
    ).fetchall()
    require(len(rows) == 1, "event sample outside exact fold")
    from afre.research_datasets.splits import FoldMembership

    partition = repo.resolve(FoldMembership, rows[0][0]).partition
    scopes = {
        Partition.TRAIN: PredictionScope.IN_SAMPLE,
        Partition.VALIDATION: PredictionScope.VALIDATION,
        Partition.TEST: PredictionScope.TEST,
    }
    require(partition in scopes, "event sample purged/embargoed/ineligible")
    return scopes[partition]


def subject_matches(
    repo: "EventRepository",
    event: EventReference,
    sample: ResearchSample,
    mapping_ids: tuple[str, ...],
    approved: tuple[str, ...],
) -> bool:
    assert sample.origin is not None
    origin, subject = sample.origin, event.subject
    if subject.scope is EventScope.SECURITY:
        return subject.security == sample.security
    if subject.scope is EventScope.MACRO:
        return True
    if subject.scope is EventScope.MARKET:
        return (
            repo.resolve(UniverseSnapshot, sample.snapshot_id).definition.fingerprint
            == subject.universe_definition_id
        )
    matches = []
    for identity in mapping_ids:
        value = repo.get_any(identity)
        if isinstance(value, SecurityRecord) and subject.scope is EventScope.ISSUER:
            repo.approved(value.evidence.clocks.historical_delivery, approved)
            matches.append(
                value.security == sample.security
                and value.issuer == subject.issuer
                and value.evidence.known(origin.availability_cutoff_ns)
                and value.evidence.validity.start_ns
                <= origin.timestamp_ns
                < value.evidence.validity.end_ns
            )
        elif isinstance(value, GroupMembership) and subject.scope is EventScope.SECTOR:
            repo.approved(value.clocks.historical_delivery, approved)
            matches.append(
                value.security == sample.security
                and value.group_id == subject.group_id
                and subject.group_policy is not None
                and value.matches(
                    subject.group_policy, origin.timestamp_ns, origin.availability_cutoff_ns
                )
            )
    return any(matches)


def matching_for(
    repo: "EventRepository",
    spec: EventConditioningSpec,
    sample_id: str,
    event_ids: tuple[str, ...],
    reaction_ids: tuple[str, ...],
    mapping_ids: tuple[str, ...],
) -> EventMatchSet:
    b = repo.event_bounds
    require(
        len(event_ids) <= b.events
        and len(reaction_ids) <= b.reaction_features * b.matches_per_sample
        and len(mapping_ids) <= b.events,
        "event input count bound",
    )
    require(
        len(set(event_ids)) == len(event_ids)
        and len(set(reaction_ids)) == len(reaction_ids)
        and len(set(mapping_ids)) == len(mapping_ids),
        "duplicate matching input",
    )
    sample = repo.resolve(ResearchSample, sample_id)
    require(
        sample.origin is not None
        and sample.target_definition_id == spec.window.target.fingerprint,
        "event sample origin/target mismatch",
    )
    assert sample.origin is not None
    scope = sample_scope(repo, spec, sample_id)
    require(
        scope in (PredictionScope.IN_SAMPLE, PredictionScope.VALIDATION, PredictionScope.TEST),
        "event sample scope",
    )
    snapshot = repo.resolve(UniverseSnapshot, sample.snapshot_id)
    repo._validate_links(snapshot)
    validate_snapshot_origin(snapshot, to_universe_manifest(snapshot), sample.origin)
    require(
        any(
            e.membership.security == sample.security
            and e.state is EligibilityState.ELIGIBLE
            and e.membership.state is MembershipState.INCLUDED
            for e in snapshot.eligibility
        ),
        "event sample not PIT eligible",
    )
    for identity in mapping_ids:
        require(
            isinstance(repo.get_any(identity), (SecurityRecord, GroupMembership)),
            "unsupported event subject evidence; custom mapping unavailable",
        )
    reactions = tuple(repo.resolve(ExternalSignal, i) for i in reaction_ids)
    for delivered in reactions:
        repo.approved(delivered.clocks.historical_delivery, spec.approved_delivery_attestors)
    excluded, distances, values, refs = [], [], [], []
    cutoff = sample.origin.availability_cutoff_ns

    def qualified_entity(clock: AvailabilityEvidence) -> None:
        proof = clock.historical_delivery
        require(
            proof is None or proof.entity == sample.security.instrument,
            "event historical delivery entity mismatch",
        )

    for identity in sorted(event_ids):
        event = repo.resolve(EventReference, identity)
        repo.approved(event.clocks.historical_delivery, spec.approved_delivery_attestors)
        qualified_entity(event.clocks)
        reason = None
        if event.quality is not SignalQuality.VALID:
            reason = "event-quality-unavailable"
        elif event.clocks.final_available_ns > cutoff:
            reason = "event-not-received-by-origin"
        elif (
            event.event_class not in spec.classes
            or event.subject.scope not in spec.scopes
            or (spec.subtypes and event.subtype not in spec.subtypes)
        ):
            reason = "event-class-subtype-scope-mismatch"
        elif not subject_matches(
            repo, event, sample, mapping_ids, spec.approved_delivery_attestors
        ):
            reason = "event-subject-not-historically-affected"
        distance = window_distance(event, spec.window, sample.origin.timestamp_ns)
        if reason is None and distance is None:
            reason = "event-outside-declared-window-or-unknown-anchor"
        supplied: list[tuple[str, float]] = []
        for rule in spec.value_rules:
            attribute = getattr(event, rule.key)
            if attribute is None:
                reason = reason or "event-attribute-missing"
                continue
            clocks = (
                (attribute.actual.clocks, attribute.expected.clocks)
                if rule.key == "surprise"
                else (attribute.clocks,)
            )
            for clock in clocks:
                repo.approved(clock.historical_delivery, spec.approved_delivery_attestors)
                qualified_entity(clock)
            at = (
                attribute.available_ns
                if rule.key == "surprise"
                else attribute.clocks.final_available_ns
            )
            if attribute.semantic_key != rule.semantic_key or at > cutoff:
                reason = reason or "event-attribute-semantics-or-availability"
            elif (rule.minimum is not None and attribute.value < rule.minimum) or (
                rule.maximum is not None and attribute.value > rule.maximum
            ):
                reason = reason or "event-attribute-threshold"
            else:
                supplied.append((rule.key, float(attribute.value)))
        used = []
        for reaction in spec.reaction_specs:
            key = (
                reaction.provider_name,
                reaction.provider_version,
                reaction.provider_schema,
                reaction.signal_name,
                reaction.signal_version,
                reaction.signal_semantics,
                reaction.unit,
            )
            anchor = event_anchor(event, spec.window)
            candidates = tuple(
                s
                for s in reactions
                if s.security == sample.security
                and s.semantic_key == key
                and s.clocks.final_available_ns <= cutoff
                and anchor is not None
                and anchor <= s.as_of_ns <= sample.origin.timestamp_ns
                and (event.occurrence_ns is None or event.occurrence_ns <= s.as_of_ns)
                and (
                    reaction.maximum_age_ns is None
                    or sample.origin.timestamp_ns - s.as_of_ns <= reaction.maximum_age_ns
                )
            )
            require(len(candidates) <= 1, "ambiguous reaction vintage; supply exact reference")
            signal = candidates[0] if candidates else None
            if (
                spec.window.relation is EventRelation.PRE_EVENT
                or signal is None
                or signal.quality is not SignalQuality.VALID
                or type(signal.value) not in (int, float)
            ):
                reason = reason or "reaction-missing-late-invalid-or-pre-event"
            else:
                assert isinstance(signal.value, (int, float))
                supplied.append(("reaction:" + reaction.fingerprint, float(signal.value)))
                used.append(signal.fingerprint)
        if reason:
            excluded.append((identity, reason))
        else:
            assert distance is not None
            distances.append((identity, distance))
            values.append((identity, tuple(sorted(supplied))))
            refs.append((identity, tuple(sorted(used))))
    require(len(distances) <= b.matches_per_sample, "matching events per sample bound")
    selected = tuple(i for i, _ in distances)
    if len(selected) > 1:
        require(
            spec.overlap is not EventOverlapPolicy.FAIL_ON_MULTIPLE, "multiple matching events"
        )
        if spec.overlap is EventOverlapPolicy.NEAREST_EVENT:
            best = min(distances, key=lambda x: (abs(x[1]), x[0]))[0]
            excluded.extend((i, "overlap-nearest-not-selected") for i in selected if i != best)
            selected = (best,)
    return EventMatchSet(
        spec.fingerprint,
        sample_id,
        event_ids,
        reaction_ids,
        mapping_ids,
        selected,
        tuple(excluded),
        tuple(distances),
        tuple(values),
        tuple(refs),
    )


def observations_for(
    repo: "EventRepository", matches: EventMatchSet
) -> tuple[EventConditionedObservation, ...]:
    sample = repo.resolve(ResearchSample, matches.sample_id)
    assert sample.origin is not None
    spec = repo.resolve(EventConditioningSpec, matches.spec_id)
    distances, values, refs = (
        dict(matches.distances),
        dict(matches.values),
        dict(matches.reaction_refs),
    )
    return tuple(
        EventConditionedObservation(
            matches.fingerprint,
            matches.spec_id,
            sample.fingerprint,
            sample.security,
            sample.origin,
            sample.snapshot_id,
            identity,
            distances[identity] if identity else None,
            values[identity] if identity else (),
            refs[identity] if identity else (),
            sample.target_id,
            sample.target_available_ns,
            sample_scope(repo, spec, sample.fingerprint),
            "affected" if identity else "unaffected",
        )
        for identity in matches.selected_ids or (None,)
    )

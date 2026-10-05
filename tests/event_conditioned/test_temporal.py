"""Boundary oracles, independent delivery, subject mapping and explicit overlap."""

from dataclasses import replace

import pytest

from afre.cross_sectional import CrossSectionEngine, GroupMembership
from afre.event_conditioned import (
    EventAnchor,
    EventClass,
    EventConditionedForecast,
    EventConditionedObservation,
    EventModelFamily,
    EventOverlapPolicy,
    EventReference,
    EventRelation,
    EventScope,
    EventSubject,
    EventSurprise,
    EventValueRule,
    EventWindowSpec,
)
from afre.event_conditioned.artifacts import EventMatchSet
from afre.event_conditioned.queries import event_as_of
from afre.event_conditioned.windows import window_distance
from afre.feature_store.models import AvailabilityEvidence
from afre.research_datasets.samples import ResearchSample
from afre.schema import ContractError
from afre.universe.models import UniverseSnapshot
from afre.universe.securities import SecurityRecord
from examples.cross_sectional_demo import external, group
from examples.event_conditioned_demo import event, value
from tests.event_conditioned.conftest import Case


def sample_for(case: Case) -> ResearchSample:
    forecast = case.repo.get(EventConditionedForecast, case.fixture.forecast_ids[0])
    return case.repo.get(
        ResearchSample,
        case.repo.get(EventConditionedObservation, forecast.observation_id).sample_id,
    )


@pytest.mark.parametrize("anchor", [EventAnchor.PUBLICATION, EventAnchor.FINAL_AVAILABILITY])
def test_reaction_cannot_precede_known_occurrence_with_alternate_anchor(
    case: Case, anchor: EventAnchor
) -> None:
    sample = sample_for(case)
    e = replace(event(sample, "scheduled-reaction", at=50), occurrence_ns=59)
    identity = case.engine.publish_event(e)
    reaction = external(sample.security, 55, 0.1, 55)
    CrossSectionEngine(case.repo).publish_external(reaction)
    spec = replace(
        case.fixture.spec,
        family=EventModelFamily.EVENT_FEATURE_LINEAR,
        reaction_specs=(case.fixture.upstream.spec.score,),
        window=replace(
            case.fixture.spec.window,
            anchor=anchor,
            relation=EventRelation.POST_EVENT,
            post_maximum_age_ns=20,
        ),
    )
    observed = case.engine.observe(
        spec, sample.fingerprint, (identity,), (reaction.fingerprint,)
    )[0]
    assert observed.event_id is None and not observed.reaction_ids


@pytest.mark.parametrize("relation", list(EventRelation))
@pytest.mark.parametrize("anchor", list(EventAnchor))
@pytest.mark.parametrize("inclusive", [True, False])
def test_window_boundaries(
    case: Case, relation: EventRelation, anchor: EventAnchor, inclusive: bool
) -> None:
    sample = sample_for(case)
    e = event(sample, "window", at=50)
    window = EventWindowSpec(
        case.fixture.spec.window.target, relation, anchor, 10, 2, 10, inclusive, inclusive
    )
    actual = tuple(window_distance(e, window, t) for t in (39, 40, 49, 50, 51, 52, 60, 61))
    expected: tuple[int | None, ...]
    if relation is EventRelation.PRE_EVENT:
        expected = (None, -10 if inclusive else None, -1, None, None, None, None, None)
    elif relation is EventRelation.AT_EVENT:
        expected = (None, None, None, 0, None, None, None, None)
    else:
        expected = (
            None,
            None,
            None,
            None,
            None,
            2 if inclusive else None,
            10 if inclusive else None,
            None,
        )
    assert actual == expected


@pytest.mark.parametrize(
    "case_type",
    [
        "same-time",
        "late",
        "wrong-class",
        "wrong-subtype",
        "wrong-security",
        "unknown-occurrence",
    ],
)
def test_event_selection(case: Case, case_type: str) -> None:
    sample = sample_for(case)
    e = event(sample, "selection", received=62 if case_type == "late" else 60)
    spec = case.fixture.spec
    if case_type == "wrong-class":
        spec = replace(spec, classes=(EventClass.MACRO,))
    elif case_type == "wrong-subtype":
        spec = replace(spec, subtypes=("different",))
    elif case_type == "wrong-security":
        other = case.repo.get(EventConditionedForecast, case.fixture.forecast_ids[-1]).security
        if other == sample.security:
            other = case.repo.get(
                EventConditionedForecast, case.fixture.forecast_ids[1]
            ).security
        e = replace(e, subject=EventSubject(EventScope.SECURITY, security=other))
    elif case_type == "unknown-occurrence":
        e = replace(e, occurrence_ns=None)
    identity = case.engine.publish_event(e)
    observed = case.engine.observe(spec, sample.fingerprint, (identity,))[0]
    assert bool(observed.event_id) == (case_type == "same-time")


def test_publication_receipt_and_pre_event_leak(case: Case) -> None:
    sample = sample_for(case)
    e = event(sample, "published-earlier", at=59, received=62)
    identity = case.engine.publish_event(e)
    spec = replace(
        case.fixture.spec,
        window=replace(
            case.fixture.spec.window, relation=EventRelation.POST_EVENT, post_maximum_age_ns=10
        ),
    )
    observation = case.engine.observe(spec, sample.fingerprint, (identity,))[0]
    assert observation.event_id is None
    prior = replace(
        spec, window=replace(spec.window, relation=EventRelation.PRE_EVENT, pre_lookback_ns=10)
    )
    later = case.engine.publish_event(event(sample, "future-content", at=65))
    observed = case.engine.observe(prior, sample.fingerprint, (later,))[0]
    assert observed.event_id is None and not observed.values and not observed.reaction_ids


@pytest.mark.parametrize("late", [False, True])
def test_reaction_own_clock(case: Case, late: bool) -> None:
    sample = sample_for(case)
    identity = case.engine.publish_event(event(sample, "reaction-event", at=59))
    s = external(sample.security, 60, 0.2, 61 if late else 60)
    CrossSectionEngine(case.repo).publish_external(s)
    spec = replace(
        case.fixture.spec,
        family=EventModelFamily.EVENT_FEATURE_LINEAR,
        window=replace(
            case.fixture.spec.window, relation=EventRelation.POST_EVENT, post_maximum_age_ns=10
        ),
        reaction_specs=(case.fixture.upstream.spec.score,),
    )
    observed = case.engine.observe(spec, sample.fingerprint, (identity,), (s.fingerprint,))[0]
    assert bool(observed.event_id) == (not late)
    assert observed.reaction_ids == (() if late else (s.fingerprint,))


def test_surprise_requires_both_inputs(case: Case) -> None:
    actual, expected = value(1.0, 60, "unit", "actual"), value(0.2, 62, "unit", "expectation")
    with pytest.raises(ContractError, match="both actual"):
        EventSurprise(actual, expected, 1.0, "actual-minus-expectation-v1", 60, 60)
    surprise = EventSurprise(actual, expected, 2.0, "actual-minus-expectation-v1", 62, 62)
    assert surprise.value == pytest.approx(0.4)
    sample = sample_for(case)
    e = replace(event(sample, "late-surprise"), surprise=surprise)
    identity = case.engine.publish_event(e)
    spec = replace(
        case.fixture.spec,
        family=EventModelFamily.SURPRISE_LINEAR,
        value_rules=(EventValueRule("surprise", surprise.semantic_key, use_as_feature=True),),
    )
    assert not case.engine.observe(spec, sample.fingerprint, (identity,))[0].event_id


@pytest.mark.parametrize("kind", ["materiality", "novelty", "surprise"])
def test_attribute_semantics_and_threshold(case: Case, kind: str) -> None:
    sample = sample_for(case)
    e = event(sample, "attributes", score=0.2)
    attribute = getattr(e, kind)
    spec = replace(
        case.fixture.spec,
        value_rules=(EventValueRule(kind, attribute.semantic_key, minimum=0.8),),
    )
    identity = case.engine.publish_event(e)
    assert not case.engine.observe(spec, sample.fingerprint, (identity,))[0].event_id
    spec = replace(spec, value_rules=(replace(spec.value_rules[0], minimum=None),))
    assert case.engine.observe(spec, sample.fingerprint, (identity,))[0].event_id
    wrong = replace(
        spec, value_rules=(replace(spec.value_rules[0], semantic_key=("bad",) * 4),)
    )
    assert not case.engine.observe(wrong, sample.fingerprint, (identity,))[0].event_id


@pytest.mark.parametrize(
    "scope",
    [
        EventScope.SECURITY,
        EventScope.ISSUER,
        EventScope.SECTOR,
        EventScope.MARKET,
        EventScope.MACRO,
    ],
)
def test_pit_subjects(case: Case, scope: EventScope) -> None:
    sample = sample_for(case)
    mappings: tuple[str, ...] = ()
    if scope is EventScope.SECURITY:
        subject = EventSubject(scope, security=sample.security)
    elif scope is EventScope.ISSUER:
        records = tuple(
            case.repo.get(SecurityRecord, r[0])
            for r in case.repo._connection.execute(
                "SELECT fingerprint FROM u_records WHERE type_name='SecurityRecord'"
            )
        )
        record = next(r for r in records if r.security == sample.security)
        subject = EventSubject(scope, issuer=record.issuer)
        mappings = (record.fingerprint,)
    elif scope is EventScope.SECTOR:
        g = case.repo.get(
            GroupMembership, dict(case.fixture.upstream.group_refs)[sample.security.fingerprint]
        )
        subject = EventSubject(
            scope, group_policy=case.fixture.upstream.spec.group, group_id=g.group_id
        )
        mappings = (g.fingerprint,)
    elif scope is EventScope.MARKET:
        subject = EventSubject(
            scope,
            universe_definition_id=case.repo.get(
                UniverseSnapshot, sample.snapshot_id
            ).definition.fingerprint,
        )
    else:
        subject = EventSubject(scope)
    identity = case.engine.publish_event(event(sample, "subject", subject=subject))
    observed = case.engine.observe(
        case.fixture.spec, sample.fingerprint, (identity,), mapping_ids=mappings
    )[0]
    assert observed.event_id == identity
    if scope is EventScope.SECTOR:
        later = group(sample.security, "reclassified", 90)
        CrossSectionEngine(case.repo).publish_group(later)
        assert (
            case.engine.observe(
                case.fixture.spec, sample.fingerprint, (identity,), mapping_ids=mappings
            )[0]
            == observed
        )
        assert not case.engine.observe(
            case.fixture.spec, sample.fingerprint, (identity,), mapping_ids=(later.fingerprint,)
        )[0].event_id


@pytest.mark.parametrize("policy", list(EventOverlapPolicy))
def test_overlap_policy(case: Case, policy: EventOverlapPolicy) -> None:
    sample = sample_for(case)
    ids = tuple(
        case.engine.publish_event(event(sample, name)) for name in ("event-a", "event-b")
    )
    spec = replace(case.fixture.spec, overlap=policy)
    if policy is EventOverlapPolicy.FAIL_ON_MULTIPLE:
        with pytest.raises(ContractError, match="multiple"):
            case.engine.observe(spec, sample.fingerprint, ids)
    else:
        observed = case.engine.observe(spec, sample.fingerprint, tuple(reversed(ids)))
        assert len(observed) == (2 if policy is EventOverlapPolicy.ALL_EVENTS_SEPARATE else 1)
        match = case.repo.get(EventMatchSet, observed[0].matches_id)
        assert match.selected_ids == (
            tuple(sorted(ids))
            if policy is EventOverlapPolicy.ALL_EVENTS_SEPARATE
            else (min(ids),)
        )


def test_indexed_event_revision_lookup(case: Case) -> None:
    sample = sample_for(case)
    first = event(sample, "history")
    case.engine.publish_event(first)
    assert event_as_of(case.repo, first.provider, first.event_id, 59) is None
    assert event_as_of(case.repo, first.provider, first.event_id, 60) == first
    corrected = replace(
        first,
        revision="later",
        clocks=replace(
            clocks_for(first),
            afre_received_ns=90,
            afre_ingested_ns=90,
            afre_computed_ns=90,
            final_available_ns=90,
        ),
    )
    case.engine.publish_event(corrected)
    assert event_as_of(case.repo, first.provider, first.event_id, 100) == corrected
    case.engine.publish_event(replace(first, revision="ambiguous"))
    with pytest.raises(ContractError, match="ambiguous"):
        event_as_of(case.repo, first.provider, first.event_id, 60)


def clocks_for(e: EventReference) -> AvailabilityEvidence:
    return e.clocks

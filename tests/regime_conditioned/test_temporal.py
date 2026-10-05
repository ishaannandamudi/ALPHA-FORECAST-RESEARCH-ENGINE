"""Publication/receipt, reconstruction, staleness, exact selection and PIT subjects."""

from dataclasses import replace

import pytest

from afre.cross_sectional import CrossSectionEngine, GroupMembership
from afre.feature_store.models import QualifiedHistoricalDelivery
from afre.feature_store.schema import AvailabilityMode, DeliveryEvidenceKind
from afre.ids import InstrumentId
from afre.regime_conditioned import (
    RegimeConditionedForecast,
    RegimeConditionedSample,
    RegimeMatchPolicy,
    RegimeMatchSet,
    RegimeQuality,
    RegimeScope,
    RegimeSnapshot,
    RegimeStateSemantics,
    RegimeSubject,
)
from afre.regime_conditioned.queries import snapshots_known
from afre.regime_conditioned.transitions import transition_for
from afre.research_datasets.samples import ResearchSample
from afre.schema import ContractError
from afre.serialization import canonical_json
from examples.cross_sectional_demo import group
from examples.feature_store_demo import clocks
from examples.regime_conditioned_demo import snapshot
from tests.regime_conditioned.conftest import Case


def context(case: Case) -> tuple[RegimeConditionedForecast, ResearchSample, RegimeSnapshot]:
    f = next(
        case.repo.get(RegimeConditionedForecast, i)
        for i in case.hard.forecast_ids
        if case.repo.get(RegimeConditionedForecast, i).regime_snapshot_id
    )
    o = case.repo.get(RegimeConditionedSample, f.observation_id)
    return (
        f,
        case.repo.get(ResearchSample, o.sample_id),
        case.repo.get(RegimeSnapshot, f.regime_snapshot_id or ""),
    )


def observe(case: Case, s: RegimeSnapshot) -> RegimeConditionedSample:
    _, sample, _ = context(case)
    return case.engine.observe(
        case.hard.spec, sample.fingerprint, (case.engine.publish_snapshot(s),)
    )


@pytest.mark.parametrize(
    "received,expected",
    [(59, "matched"), (60, "matched"), (61, "unmatched"), (10_000, "unmatched")],
)
def test_receipt_gate(case: Case, received: int, expected: str) -> None:
    _, sample, old = context(case)
    s = snapshot(old.taxonomy, sample, at=59, received=received)
    o = observe(case, s)
    assert o.state == expected
    assert s.clocks.upstream_publication_ns == 59


def test_publication_not_receipt_exact_origin_1001(case: Case) -> None:
    # Scale-free UTC ns: publication 10:00 / origin 10:01 / receipt 10:02.
    _, sample, old = context(case)
    late = snapshot(old.taxonomy, sample, at=59, received=61)
    assert observe(case, late).regime_snapshot_id is None
    with pytest.raises(ContractError, match="backdated"):
        replace(late.clocks, final_available_ns=59)


@pytest.mark.parametrize(
    "semantics", [RegimeStateSemantics.SMOOTHED, RegimeStateSemantics.EX_POST]
)
def test_retro_states_research_only(case: Case, semantics: RegimeStateSemantics) -> None:
    _, _, s = context(case)
    result = observe(case, replace(s, semantics=semantics))
    assert result.state == "unsupported" and result.regime_snapshot_id is None


@pytest.mark.parametrize("quality", [q for q in RegimeQuality if q is not RegimeQuality.VALID])
def test_quality_exclusions(case: Case, quality: RegimeQuality) -> None:
    _, _, s = context(case)
    result = observe(case, replace(s, quality=quality))
    match = case.repo.get(RegimeMatchSet, result.matches_id)
    assert not result.regime_snapshot_id and match.exclusions[0][1] == quality.value


@pytest.mark.parametrize("age,expected", [(0, "matched"), (10, "matched"), (11, "stale")])
def test_age_boundary(case: Case, age: int, expected: str) -> None:
    _, sample, s = context(case)
    assert observe(case, snapshot(s.taxonomy, sample, at=60 - age)).state == expected


def test_unqualified_archive_and_qualified_reconstruction(case: Case) -> None:
    _, sample, s = context(case)
    late = snapshot(s.taxonomy, sample, at=59, received=100_000)
    late = replace(late, clocks=replace(late.clocks, mode=AvailabilityMode.RECONSTRUCTED))
    assert observe(case, late).state == "unmatched"
    proof = QualifiedHistoricalDelivery(
        s.source.fingerprint,
        s.subject.entity,
        DeliveryEvidenceKind.AFRE_DELIVERY_LOG,
        59,
        59,
        59,
        100_000,
        "local-review",
        "recorded-channel",
        "1",
        s.source.provenance,
    )
    qualified = replace(
        late, clocks=replace(late.clocks, historical_delivery=proof, final_available_ns=59)
    )
    identity = case.engine.publish_snapshot(qualified)
    with pytest.raises(ContractError, match="approved"):
        case.engine.observe(case.hard.spec, sample.fingerprint, (identity,))
    o = case.engine.observe(
        replace(case.hard.spec, approved_delivery_attestors=("local-review",)),
        sample.fingerprint,
        (identity,),
    )
    assert o.regime_snapshot_id == identity and qualified.clocks.afre_received_ns == 100_000
    assert qualified.clocks.final_available_ns == 59
    with pytest.raises(ContractError, match="binding"):
        replace(
            qualified,
            subject=replace(
                s.subject,
                entity=InstrumentId("other", "entity"),
                security=None,
                scope=RegimeScope.GLOBAL,
            ),
        )


def test_multiple_snapshot_policies(case: Case) -> None:
    _, sample, s = context(case)
    ids = tuple(
        case.engine.publish_snapshot(snapshot(s.taxonomy, sample, at=at, state=state))
        for at, state in ((59, "A"), (60, "B"))
    )
    o = case.engine.observe(case.hard.spec, sample.fingerprint, tuple(reversed(ids)))
    assert o.regime_snapshot_id == ids[1] and len(o.transition_ids) == 1
    exact = case.engine.observe(
        replace(case.hard.spec, matching=RegimeMatchPolicy.EXACT_AS_OF), sample.fingerprint, ids
    )
    assert exact.regime_snapshot_id == ids[1]
    no_exact = case.engine.observe(
        replace(case.hard.spec, matching=RegimeMatchPolicy.EXACT_AS_OF),
        sample.fingerprint,
        ids[:1],
    )
    assert no_exact.regime_snapshot_id is None
    with pytest.raises(ContractError, match="multiple"):
        case.engine.observe(
            replace(case.hard.spec, matching=RegimeMatchPolicy.FAIL_ON_MULTIPLE),
            sample.fingerprint,
            ids,
        )
    revised = case.engine.publish_snapshot(
        replace(case.repo.get(RegimeSnapshot, ids[1]), revision="2")
    )
    with pytest.raises(ContractError, match="ambiguous"):
        case.engine.observe(case.hard.spec, sample.fingerprint, (ids[1], revised))


def test_causal_hard_soft_transitions_duration(case: Case) -> None:
    _, sample, s = context(case)
    ids = tuple(
        case.engine.publish_snapshot(snapshot(s.taxonomy, sample, at=at, state=state))
        for at, state in ((57, "A"), (58, "B"), (59, "B"), (61, "A"))
    )
    o = case.engine.observe(case.hard.spec, sample.fingerprint, ids)
    assert len(o.transition_ids) == 2 and o.elapsed_observed_state_ns == 2
    assert o.transition_status == "recent"
    from afre.regime_conditioned import RegimeTransition

    transitions = tuple(case.repo.get(RegimeTransition, i) for i in o.transition_ids)
    assert [t.changed for t in transitions] == [True, False]
    assert transitions[0].probability_mass_change == 1.0
    a, b = (
        snapshot(s.taxonomy, sample, at=58, soft=(0.8, 0.2)),
        snapshot(s.taxonomy, sample, at=59, soft=(0.3, 0.7)),
    )
    t = transition_for(a, b)
    assert t.current.probabilities == (("A", 0.3), ("B", 0.7))
    assert t.probability_mass_change == pytest.approx(0.5)
    assert t.current.hard_state is None
    with pytest.raises(ContractError):
        transition_for(b, a)


def test_pit_sector_reclassification_frozen(case: Case) -> None:
    _, sample, s = context(case)
    group_id = next(
        i
        for security, i in case.hard.upstream.group_refs
        if security == sample.security.fingerprint
    )
    g = case.repo.get(GroupMembership, group_id)
    policy = case.hard.upstream.spec.group
    assert policy is not None
    subject = RegimeSubject(
        RegimeScope.SECTOR,
        InstrumentId("sector", g.group_id),
        group_policy=policy,
        group_id=g.group_id,
    )
    sid = case.engine.publish_snapshot(replace(s, subject=subject))
    spec = replace(case.hard.spec, scope=RegimeScope.SECTOR)
    old = case.engine.observe(spec, sample.fingerprint, (sid,), (group_id,))
    frozen = canonical_json(old)
    late = CrossSectionEngine(case.repo).publish_group(
        group(sample.security, "new-sector", received=61)
    )
    again = case.engine.observe(spec, sample.fingerprint, (sid,), (group_id, late))
    assert (
        again.regime_snapshot_id == sid
        and canonical_json(case.repo.get_any(old.fingerprint)) == frozen
    )
    duplicate = CrossSectionEngine(case.repo).publish_group(
        group(sample.security, "conflict", received=60)
    )
    with pytest.raises(ContractError, match="ambiguous"):
        case.engine.observe(spec, sample.fingerprint, (sid,), (group_id, duplicate))


@pytest.mark.parametrize(
    "scope", [RegimeScope.GLOBAL, RegimeScope.MARKET, RegimeScope.VENUE, RegimeScope.CUSTOM]
)
def test_scope_matching(case: Case, scope: RegimeScope) -> None:
    _, sample, s = context(case)
    from afre.universe.models import UniverseSnapshot

    subject = RegimeSubject(
        scope,
        InstrumentId("regime", "subject"),
        universe_definition_id=case.repo.get(
            UniverseSnapshot, sample.snapshot_id
        ).definition.fingerprint
        if scope is RegimeScope.MARKET
        else None,
    )
    sid = case.engine.publish_snapshot(replace(s, subject=subject))
    o = case.engine.observe(replace(case.hard.spec, scope=scope), sample.fingerprint, (sid,))
    assert (o.regime_snapshot_id is not None) == (
        scope in (RegimeScope.GLOBAL, RegimeScope.MARKET)
    )
    assert snapshots_known(
        case.repo, s.taxonomy.provider.provider, s.taxonomy.fingerprint, subject, 60
    )


def test_latest_revision_history_and_stable_metadata(case: Case) -> None:
    _, sample, s = context(case)
    early = snapshot(s.taxonomy, sample, at=58, received=58, state="A")
    revised = replace(
        early,
        clocks=replace(
            early.clocks,
            afre_received_ns=59,
            afre_ingested_ns=59,
            afre_computed_ns=59,
            final_available_ns=59,
        ),
        revision="2",
    )
    now = snapshot(s.taxonomy, sample, at=60, state="B")
    ids = tuple(case.engine.publish_snapshot(x) for x in (early, revised, now))
    observation = case.engine.observe(case.hard.spec, sample.fingerprint, tuple(reversed(ids)))
    from afre.regime_conditioned import RegimeTransition

    transition = case.repo.get(RegimeTransition, observation.transition_ids[0])
    assert transition.previous_id == revised.fingerprint
    metadata = replace(
        now, as_of_ns=61, clocks=clocks(61), membership=replace(now.membership, tolerance=1e-11)
    )
    assert not transition_for(now, metadata).changed

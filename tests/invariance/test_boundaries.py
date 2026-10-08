"""PIT evidence, explicit neutral labels and bounded, non-executable environments."""

from dataclasses import FrozenInstanceError, fields, replace
from typing import cast

import pytest

from afre.cross_sectional import CrossSectionEngine
from afre.event_conditioned import EventEngine
from afre.event_conditioned.definitions import EventValueRule
from afre.invariance import (
    EnvironmentKind,
    EnvironmentMembership,
    EnvironmentRule,
    EnvironmentSet,
    EnvironmentState,
    InvarianceBounds,
    InvarianceRepository,
    NeutralEnvironmentLabel,
)
from afre.regime_conditioned import RegimeEngine, RegimeStateSemantics
from afre.research_datasets.samples import ResearchSample
from afre.schema import Artifact, ContractError
from afre.target_engine.models import TargetVintage
from afre.time import TimeRange
from examples.cross_sectional_demo import group, provider_source
from examples.event_conditioned_demo import event
from examples.feature_store_demo import clocks
from examples.invariance_cohorts import build_cohorts
from tests.invariance.conftest import Case


def test_all_declared_native_cohorts_and_compounds(case: Case) -> None:
    cohorts = build_cohorts(case.repo, case.fixture)
    ms = tuple(case.repo.get(EnvironmentMembership, i) for i in cohorts.membership_ids)
    assert {d.kind for d in cohorts.environment_set.definitions} == set(EnvironmentKind) - {
        EnvironmentKind.TIME_WINDOW
    }
    for d in cohorts.environment_set.definitions:
        members = [m for m in ms if m.environment_id == d.fingerprint]
        weights = [m.weight for m in members]
        assert len(members) == 12
        assert sum(w > 0 for w in weights) == (
            12 if d.environment_id in ("soft-A", "historical-universe", "source-quality") else 6
        )


@pytest.mark.parametrize("kind", ["regime", "event", "group", "label"])
def test_late_receipt_and_later_reconstruction_not_backdated(case: Case, kind: str) -> None:
    cohorts = build_cohorts(case.repo, case.fixture)
    names = {d.environment_id: d for d in cohorts.environment_set.definitions}
    s = case.repo.get(ResearchSample, case.fixture.spec.sample_ids[0])
    assert s.origin is not None
    v: Artifact
    if kind == "regime":
        from examples.regime_conditioned_demo import snapshot, taxonomy

        v = snapshot(taxonomy(), s, received=s.timestamp_ns + 2)
        RegimeEngine(case.repo).publish_snapshot(v)
        d = names["hard-A"]
    elif kind == "event":
        v = event(s, "late-event", received=s.timestamp_ns + 2)
        EventEngine(case.repo).publish_event(v)
        d = names["earnings"]
    elif kind == "group":
        v = group(s.security, "S", received=s.timestamp_ns + 2)
        CrossSectionEngine(case.repo).publish_group(v)
        d = names["sector-S"]
    else:
        d = names["neutral-label"]
        v = NeutralEnvironmentLabel(
            s.fingerprint,
            s.origin,
            d.provider,
            "open",
            "1",
            TimeRange(0, 1000),
            replace(clocks(s.timestamp_ns + 2), upstream_publication_ns=s.timestamp_ns),
            provider_source(d.provider),
        )
        case.engine.publish_label(v)
    m = case.engine.bind(
        d.fingerprint, s.fingerprint, (v.fingerprint,), constructed_ns=s.timestamp_ns
    )
    assert m.state is not EnvironmentState.INCLUDED and m.weight == 0


def test_smoothed_regime_rejected(case: Case) -> None:
    from examples.regime_conditioned_demo import snapshot, taxonomy

    cohorts = build_cohorts(case.repo, case.fixture)
    d = next(d for d in cohorts.environment_set.definitions if d.environment_id == "hard-A")
    s = case.repo.get(ResearchSample, case.fixture.spec.sample_ids[0])
    v = replace(snapshot(taxonomy(), s), semantics=RegimeStateSemantics.SMOOTHED)
    RegimeEngine(case.repo).publish_snapshot(v)
    with pytest.raises(ContractError, match="retrospective"):
        case.engine.bind(
            d.fingerprint, s.fingerprint, (v.fingerprint,), constructed_ns=s.timestamp_ns
        )


def test_event_exact_materiality_novelty_surprise_rules(case: Case) -> None:
    cohorts = build_cohorts(case.repo, case.fixture)
    original = next(
        d for d in cohorts.environment_set.definitions if d.environment_id == "earnings"
    )
    s = next(
        case.repo.get(ResearchSample, i)
        for i in case.fixture.spec.sample_ids
        if int(case.repo.get(ResearchSample, i).security.value) == 1
    )
    ev = event(s, "valued-event")
    EventEngine(case.repo).publish_event(ev)
    assert ev.materiality and ev.novelty and ev.surprise
    rules = tuple(
        EventValueRule(k, getattr(ev, k).semantic_key, minimum=0.0, maximum=1.0)
        for k in ("materiality", "novelty", "surprise")
    )
    d = replace(original, environment_id="event-values", event_value_rules=rules)
    case.engine.declare(EnvironmentSet((d,), 40))
    m = case.engine.bind(
        d.fingerprint, s.fingerprint, (ev.fingerprint,), constructed_ns=s.timestamp_ns
    )
    assert m.state is EnvironmentState.INCLUDED
    changed = replace(
        d,
        environment_id="incompatible-event-unit",
        event_value_rules=(
            replace(rules[0], semantic_key=("other", "method", "version", "units")),
        ),
    )
    case.engine.declare(EnvironmentSet((changed,), 40))
    assert (
        case.engine.bind(
            changed.fingerprint, s.fingerprint, (ev.fingerprint,), constructed_ns=s.timestamp_ns
        ).weight
        == 0
    )


def test_PIT_sector_reclassification_cannot_replace_history(case: Case) -> None:
    cohorts = build_cohorts(case.repo, case.fixture)
    d = next(d for d in cohorts.environment_set.definitions if d.environment_id == "sector-S")
    s = next(
        case.repo.get(ResearchSample, i)
        for i in case.fixture.spec.sample_ids
        if int(case.repo.get(ResearchSample, i).security.value) == 1
    )
    old = group(s.security, "S")
    correction = group(s.security, "T", received=90)
    CrossSectionEngine(case.repo).publish_group(correction)
    m = case.engine.bind(
        d.fingerprint,
        s.fingerprint,
        (old.fingerprint, correction.fingerprint),
        constructed_ns=100,
    )
    assert m.weight == 1 and m.selected_ids == (old.fingerprint,)
    with pytest.raises(ContractError, match="actually constructed"):
        case.engine.metadata(m.fingerprint, m.origin)


def test_forecast_metadata_guard_even_after_cache(case: Case) -> None:
    f = case.fixture
    metrics = case.engine.evaluate(f.spec.fingerprint, f.membership_ids, 100, 100)
    sample = case.repo.get(ResearchSample, f.spec.sample_ids[0])
    with case.repo.read_snapshot(), case.repo.validation_cache():
        case.repo.get_any(metrics[0].fingerprint)
        with case.repo.feature_only():
            with pytest.raises(ContractError):
                case.repo.get_any(metrics[0].fingerprint)
            with pytest.raises(ContractError):
                case.repo.resolve(TargetVintage, sample.target_id or "")
    for i in f.membership_ids:
        m = case.repo.get(EnvironmentMembership, i)
        case.engine.metadata(i, m.origin)


@pytest.mark.parametrize("field", [f.name for f in fields(InvarianceBounds)])
def test_hard_bounds_reject_escalation(field: str) -> None:
    with pytest.raises(ContractError):
        replace(InvarianceBounds(), **{field: 0})
    with pytest.raises(ContractError):
        replace(InvarianceBounds(), **{field: getattr(InvarianceBounds(), field) + 1})


def test_compound_bounds_read_and_write(case: Case) -> None:
    cohorts = build_cohorts(case.repo, case.fixture)
    path = case.repo._connection.execute("PRAGMA database_list").fetchone()[2]
    with (
        InvarianceRepository(path, InvarianceBounds(compounds=1)) as bounded,
        pytest.raises(ContractError, match="compound"),
    ):
        bounded.get(EnvironmentSet, cohorts.environment_set.fingerprint)
    with pytest.raises(FrozenInstanceError):
        field = "minimum_count"
        setattr(case.fixture.spec, field, 1)


def test_neutral_rules_cannot_be_executable(case: Case) -> None:
    d = case.fixture.environment_set.definitions[0]
    with pytest.raises(ContractError):
        replace(d, rule=cast(EnvironmentRule, lambda: True))
    with pytest.raises(ContractError):
        replace(
            d,
            kind=EnvironmentKind.CUSTOM,
            rule=EnvironmentRule.COMPOUND,
            window=None,
            component_ids=(d.fingerprint,),
        )

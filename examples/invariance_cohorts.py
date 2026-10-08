"""Neutral causal cohorts, including an explicitly supplied event by regime compound."""

from dataclasses import dataclass, replace
from typing import TypedDict

from afre.cross_sectional import CrossSectionEngine, GroupPolicy, GroupType
from afre.event_conditioned import EventEngine
from afre.event_conditioned.definitions import EventWindowSpec
from afre.event_conditioned.schema import EventClass, EventRelation
from afre.invariance import (
    EnvironmentDefinition,
    EnvironmentKind,
    EnvironmentRule,
    EnvironmentSet,
    InvarianceEngine,
    InvarianceRepository,
    NeutralEnvironmentLabel,
)
from afre.regime_conditioned import RegimeEngine, RegimeMembershipKind
from afre.research_datasets.samples import ResearchSample
from afre.target_engine.definitions import TargetDefinition
from afre.time import TimeRange
from afre.universe.models import UniverseSnapshot
from examples.cross_sectional_demo import group, provider_source
from examples.event_conditioned_demo import event
from examples.feature_store_demo import clocks
from examples.invariance_fixture import InvarianceFixture
from examples.regime_conditioned_demo import snapshot, taxonomy


class DefinitionBase(TypedDict):
    target: TargetDefinition
    declared_ns: int
    version: str
    minimum_count: int


@dataclass(frozen=True)
class Cohorts:
    environment_set: EnvironmentSet
    membership_ids: tuple[str, ...]
    evidence: tuple[tuple[str, str, tuple[str, ...]], ...]


def build_cohorts(
    repo: InvarianceRepository, fixture: InvarianceFixture, reverse: bool = False
) -> Cohorts:
    engine, regime, events, cross = (
        InvarianceEngine(repo),
        RegimeEngine(repo),
        EventEngine(repo),
        CrossSectionEngine(repo),
    )
    tax = taxonomy()
    regime.publish_taxonomy(tax)
    target = fixture.spec.target
    base: DefinitionBase = dict(target=target, declared_ns=40, version="1", minimum_count=2)
    hard = EnvironmentDefinition(
        "hard-A",
        EnvironmentKind.REGIME,
        "hard A",
        provider=tax.provider.provider,
        rule=EnvironmentRule.REGIME_STATE,
        taxonomy_id=tax.fingerprint,
        state_label="A",
        membership_kind=RegimeMembershipKind.HARD,
        **base,
    )
    soft = replace(
        hard, environment_id="soft-A", label="soft A", membership_kind=RegimeMembershipKind.SOFT
    )
    ev = EnvironmentDefinition(
        "earnings",
        EnvironmentKind.EVENT,
        "earnings cohort",
        provider="synthetic-event-provider",
        rule=EnvironmentRule.EVENT_COHORT,
        event_window=EventWindowSpec(target, EventRelation.AT_EVENT),
        event_classes=(EventClass.EARNINGS,),
        **base,
    )
    policy = GroupPolicy(GroupType.SECTOR, "synthetic-classifier", "synthetic-taxonomy", "1")
    sector = EnvironmentDefinition(
        "sector-S",
        EnvironmentKind.SECTOR,
        "sector S",
        provider=policy.provider,
        rule=EnvironmentRule.GROUP,
        group_policy=policy,
        group_id="S",
        **base,
    )
    industry = replace(
        sector,
        environment_id="industry-S",
        label="industry S",
        kind=EnvironmentKind.INDUSTRY,
        group_policy=replace(policy, group_type=GroupType.INDUSTRY),
    )
    sample = repo.get(ResearchSample, fixture.spec.sample_ids[0])
    universe = EnvironmentDefinition(
        "historical-universe",
        EnvironmentKind.UNIVERSE,
        "historical universe",
        provider="AFRE-declared",
        rule=EnvironmentRule.UNIVERSE,
        universe_definition_id=repo.get(
            UniverseSnapshot, sample.snapshot_id
        ).definition.fingerprint,
        **base,
    )
    quality = EnvironmentDefinition(
        "source-quality",
        EnvironmentKind.DATA_QUALITY,
        "native probability source",
        provider="AFRE-native",
        rule=EnvironmentRule.QUALITY,
        quality_label="source:ProbabilisticForecast",
        **base,
    )
    custom = EnvironmentDefinition(
        "neutral-label",
        EnvironmentKind.CUSTOM,
        "neutral state",
        provider="neutral-environment-provider",
        rule=EnvironmentRule.LABEL,
        neutral_label="open",
        **base,
    )
    market = replace(
        custom,
        environment_id="market-label",
        label="market state",
        kind=EnvironmentKind.MARKET_STATE,
    )
    compound = EnvironmentDefinition(
        "earnings-by-A",
        EnvironmentKind.CUSTOM,
        "earnings by hard A",
        provider="AFRE-declared",
        rule=EnvironmentRule.COMPOUND,
        component_ids=(ev.fingerprint, hard.fingerprint),
        **base,
    )
    sector_compound = replace(
        compound,
        environment_id="sector-by-A",
        label="sector S by hard A",
        component_ids=(sector.fingerprint, hard.fingerprint),
    )
    definitions = (
        hard,
        soft,
        ev,
        sector,
        industry,
        universe,
        quality,
        custom,
        market,
        compound,
        sector_compound,
    )
    envset = engine.declare(
        EnvironmentSet(tuple(reversed(definitions)) if reverse else definitions, 40)
    )
    from afre.invariance.forecasts import forecast_source

    forecast_by_sample = {
        forecast_source(repo, i).sample_id: i for i in fixture.spec.forecast_ids
    }
    memberships, evidence = [], []
    samples = tuple(repo.get(ResearchSample, i) for i in fixture.spec.sample_ids)
    for s in reversed(samples) if reverse else samples:
        assert s.origin is not None
        index = int(s.security.value)
        rs = snapshot(tax, s, state="A" if index <= 2 else "B")
        ss = snapshot(tax, s, soft=(0.2 + index * 0.1, 0.8 - index * 0.1))
        eid = events.publish_event(
            replace(
                event(s, "invariance-event:" + s.fingerprint),
                event_class=EventClass.EARNINGS if index <= 2 else EventClass.GUIDANCE,
            )
        )
        gid = cross.publish_group(group(s.security, "S" if index <= 2 else "T"))
        group_i = replace(
            group(s.security, "S" if index <= 2 else "T"), group_type=GroupType.INDUSTRY
        )
        iid = cross.publish_group(group_i)
        regime.publish_snapshot(rs)
        regime.publish_snapshot(ss)
        label = engine.publish_label(
            NeutralEnvironmentLabel(
                s.fingerprint,
                s.origin,
                custom.provider,
                "open" if index <= 2 else "closed",
                "1",
                TimeRange(0, 1000),
                clocks(s.timestamp_ns),
                provider_source(custom.provider),
            )
        )
        source_by_env = {
            hard: (rs.fingerprint,),
            soft: (ss.fingerprint,),
            ev: (eid,),
            sector: (gid,),
            industry: (iid,),
            universe: (),
            quality: (forecast_by_sample[s.fingerprint],),
            custom: (label.fingerprint,),
            market: (label.fingerprint,),
        }
        built = {}
        for d in reversed(definitions[:9]) if reverse else definitions[:9]:
            sources = source_by_env[d]
            m = engine.bind(
                d.fingerprint,
                s.fingerprint,
                tuple(reversed(sources)) if reverse else sources,
                constructed_ns=s.timestamp_ns,
            )
            built[d.fingerprint] = m.fingerprint
            memberships.append(m.fingerprint)
            evidence.append((d.fingerprint, s.fingerprint, sources))
        for d in (sector_compound, compound) if reverse else (compound, sector_compound):
            m = engine.bind(
                d.fingerprint,
                s.fingerprint,
                tuple(built[i] for i in d.component_ids),
                constructed_ns=s.timestamp_ns,
            )
            memberships.append(m.fingerprint)
    return Cohorts(envset, tuple(sorted(memberships)), tuple(sorted(evidence)))

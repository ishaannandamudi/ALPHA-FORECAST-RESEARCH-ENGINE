"""Offline neutral hard/soft regimes, causal transitions, matched research and replay."""

from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory

from afre.cross_sectional.artifacts import CrossSectionEvaluation
from afre.cross_sectional.groups import GroupMembership
from afre.ids import InstrumentId
from afre.probabilistic.artifacts import ProbabilisticForecast
from afre.regime_conditioned import (
    RegimeCategory,
    RegimeConditionedForecast,
    RegimeConditionedModel,
    RegimeConditionedSample,
    RegimeConditioningSpec,
    RegimeEngine,
    RegimeMembership,
    RegimeMembershipKind,
    RegimeModelFamily,
    RegimeProviderReference,
    RegimeQuality,
    RegimeRepository,
    RegimeScope,
    RegimeSnapshot,
    RegimeStateSemantics,
    RegimeSubject,
    RegimeTaxonomy,
)
from afre.research_datasets.samples import ResearchSample
from afre.serialization import canonical_json
from afre.statistical_models.artifacts import DesignMatrix, FittedModelArtifact, ModelFitInputs
from examples.cross_sectional_demo import CrossSectionFixture, cross_fixture, provider_source
from examples.feature_store_demo import clocks


def taxonomy(liquidity: bool = False) -> RegimeTaxonomy:
    provider = "synthetic-liquidity-provider" if liquidity else "synthetic-market-provider"
    return RegimeTaxonomy(
        RegimeProviderReference(
            provider,
            "1",
            "1.0",
            "liquidity" if liquidity else "market",
            "1",
            provider_source(provider),
            "offline-fixture",
        ),
        ("A", "B"),
        ("first state", "second state"),
        ("supplied state A", "supplied state B"),
        RegimeCategory.LIQUIDITY if liquidity else RegimeCategory.MARKET_CONTEXT,
        2,
    )


def snapshot(
    tax: RegimeTaxonomy,
    sample: ResearchSample,
    at: int | None = None,
    received: int | None = None,
    state: str = "A",
    soft: tuple[float, ...] | None = None,
    subject: RegimeSubject | None = None,
) -> RegimeSnapshot:
    at = sample.timestamp_ns if at is None else at
    received = at if received is None else received
    membership = (
        RegimeMembership(RegimeMembershipKind.HARD, tax.states, state)
        if soft is None
        else RegimeMembership(
            RegimeMembershipKind.SOFT,
            tax.states,
            probabilities=tuple(zip(tax.states, soft, strict=True)),
        )
    )
    return RegimeSnapshot(
        tax,
        subject
        or RegimeSubject(
            RegimeScope.SECURITY, sample.security.instrument, security=sample.security
        ),
        at,
        replace(clocks(received), upstream_publication_ns=at, upstream_available_ns=at),
        membership,
        RegimeStateSemantics.FILTERED,
        RegimeQuality.VALID,
        provider_source(tax.provider.provider),
    )


@dataclass(frozen=True)
class RegimeFixture:
    upstream: CrossSectionFixture
    spec: RegimeConditioningSpec
    model: RegimeConditionedModel
    training_ids: tuple[str, ...]
    snapshot_ids: tuple[str, ...]
    forecast_ids: tuple[str, ...]
    test_ids: tuple[str, ...]


def build_fixture(
    repo: RegimeRepository,
    reverse: bool = False,
    upstream: CrossSectionFixture | None = None,
    soft: bool = False,
    scope: RegimeScope = RegimeScope.SECURITY,
    horizon_index: int = 0,
    family: RegimeModelFamily | None = None,
) -> RegimeFixture:
    upstream = upstream or cross_fixture(repo, reverse)
    binding = upstream.upstream.spec.bindings[horizon_index]
    engine = RegimeEngine(repo)
    tax = taxonomy(soft)
    engine.publish_taxonomy(tax)
    spec = RegimeConditioningSpec(
        binding.point_model_id,
        upstream.upstream.spec.horizon_set.targets[horizon_index],
        tax.fingerprint,
        scope,
        family
        or (
            RegimeModelFamily.SOFT_REGIME_WEIGHTED_OFFSET
            if soft
            else RegimeModelFamily.REGIME_RESIDUAL_OFFSET
        ),
        allowed_memberships=(RegimeMembershipKind.HARD, RegimeMembershipKind.SOFT)
        if soft
        else (RegimeMembershipKind.HARD,),
        maximum_age_ns=10,
        transition_recent_ns=2,
    )
    base = repo.get(FittedModelArtifact, binding.point_model_id)
    matrix = repo.get(DesignMatrix, repo.get(ModelFitInputs, base.fit_inputs_id).matrix_id)
    observations, snapshots = [], set()
    rows = tuple(reversed(matrix.rows)) if reverse else matrix.rows

    def subject(sample: ResearchSample) -> RegimeSubject | None:
        return (
            RegimeSubject(RegimeScope.GLOBAL, InstrumentId("regime", "global"))
            if scope is RegimeScope.GLOBAL
            else None
        )

    for row in rows:
        sample = repo.get(ResearchSample, row.sample_id)
        state = "A" if row.origin.timestamp_ns == 20 else "B"
        s = (
            snapshot(
                tax,
                sample,
                state=state,
                soft=(0.8, 0.2) if state == "A" else (0.25, 0.75) if soft else None,
                subject=subject(sample),
            )
            if soft
            else snapshot(tax, sample, state=state, subject=subject(sample))
        )
        identity = engine.publish_snapshot(s)
        snapshots.add(identity)
        observations.append(engine.observe(spec, sample.fingerprint, (identity,)))
    model = engine.fit(spec, tuple(o.fingerprint for o in observations), 40, 40, 40)
    outputs: list[tuple[str, ...]] = []
    for raws in (
        upstream.upstream.deployment[horizon_index],
        upstream.upstream.tests[horizon_index],
    ):
        forecasts = []
        for raw in tuple(reversed(raws)) if reverse else raws:
            sample = repo.get(ResearchSample, raw.input.sample_id or "")
            state = "A" if int(sample.security.value) % 2 else "B"
            if scope is RegimeScope.GLOBAL:
                state = "A"
            late = (
                sample.timestamp_ns == 60
                and sample.security.value == "0004"
                and scope is not RegimeScope.GLOBAL
            )
            s = snapshot(
                tax,
                sample,
                received=sample.timestamp_ns + 1 if late else sample.timestamp_ns,
                state=state,
                soft=(0.7, 0.3) if soft else None,
                subject=subject(sample),
            )
            identity = engine.publish_snapshot(s)
            snapshots.add(identity)
            observation = engine.observe(spec, sample.fingerprint, (identity,))
            forecasts.append(
                engine.forecast(
                    model.fingerprint,
                    observation.fingerprint,
                    raw.point_forecast_id,
                    sample.timestamp_ns,
                    raw.fingerprint,
                ).fingerprint
            )
        outputs.append(tuple(sorted(forecasts)))
    return RegimeFixture(
        upstream,
        spec,
        model,
        tuple(sorted(o.fingerprint for o in observations)),
        tuple(sorted(snapshots)),
        outputs[0],
        outputs[1],
    )


def demonstration(repo: RegimeRepository) -> tuple[tuple[str, object], ...]:
    """At least thirty-two checked steps; every provider is synthetic."""
    f = build_fixture(repo)
    soft = build_fixture(repo, upstream=f.upstream, soft=True)
    global_f = build_fixture(repo, upstream=f.upstream, scope=RegimeScope.GLOBAL)
    engine = RegimeEngine(repo)
    forecasts = tuple(repo.get(RegimeConditionedForecast, i) for i in f.forecast_ids)
    first = next(p for p in forecasts if p.regime_snapshot_id)
    o = repo.get(RegimeConditionedSample, first.observation_id)
    sample = repo.get(ResearchSample, o.sample_id)
    tax = repo.get(RegimeSnapshot, first.regime_snapshot_id or "").taxonomy
    steps: list[tuple[str, object]] = []

    def record(name: str, value: object) -> None:
        steps.append((name, value))

    record("neutral market taxonomy", tax.fingerprint)
    record("neutral liquidity taxonomy", soft.spec.taxonomy_id)
    record("hard TRAIN observations", len(f.training_ids))
    record("soft TRAIN observations", len(soft.training_ids))
    record("hard TRAIN offsets", tuple(s.value for s in f.model.state_fits))
    record("soft TRAIN offsets", tuple(s.value for s in soft.model.state_fits))
    assert any(p.regime_snapshot_id is None for p in forecasts)
    record("late receipt excluded", True)
    assert first.regime_snapshot_id
    record("same-time equality admitted", True)
    smoothed = replace(snapshot(tax, sample), semantics=RegimeStateSemantics.SMOOTHED)
    oid = engine.observe(f.spec, sample.fingerprint, (engine.publish_snapshot(smoothed),))
    assert oid.state == "unsupported"
    record("smoothed rejected for forecasting", oid.state)
    stale = snapshot(tax, sample, at=sample.timestamp_ns - 11)
    assert (
        engine.observe(f.spec, sample.fingerprint, (engine.publish_snapshot(stale),)).state
        == "stale"
    )
    record("staleness explicit", True)
    record("hard point application", first.value)
    sp = repo.get(RegimeConditionedForecast, soft.forecast_ids[0])
    record("soft weighted shift", sp.shift)
    raw = repo.get(ProbabilisticForecast, first.base_probability_id or "")
    assert first.distribution is not None and raw.distribution.scale == first.distribution.scale
    record("probability shape preserved", True)
    record(
        "explicit fallback", next(p.state for p in forecasts if p.regime_snapshot_id is None)
    )
    rank = engine.rank(f.upstream.spec, f.forecast_ids, f.upstream.group_refs)
    record("security-specific ranking", rank.fingerprint)
    global_rank = engine.rank(f.upstream.spec, global_f.forecast_ids, f.upstream.group_refs)
    record("GLOBAL same-origin ranking", global_rank.fingerprint)
    history = tuple(
        engine.publish_snapshot(snapshot(tax, sample, at=at, state=state))
        for at, state in ((58, "A"), (59, "B"), (60, "B"), (61, "A"))
    )
    observed = engine.observe(f.spec, sample.fingerprint, history)
    assert len(observed.transition_ids) == 2 and observed.elapsed_observed_state_ns == 1
    record("hard transitions and elapsed observed duration", observed.elapsed_observed_state_ns)
    record("future transition invisible", len(observed.transition_ids))
    soft_sample = repo.get(
        ResearchSample, repo.get(RegimeConditionedSample, sp.observation_id).sample_id
    )
    soft_tax = repo.get(RegimeSnapshot, next(i for i in soft.snapshot_ids)).taxonomy
    soft_history = tuple(
        engine.publish_snapshot(snapshot(soft_tax, soft_sample, at=at, soft=w))
        for at, w in ((58, (0.8, 0.2)), (60, (0.3, 0.7)))
    )
    soft_obs = engine.observe(soft.spec, soft_sample.fingerprint, soft_history)
    assert soft_obs.transition_ids
    record("soft vector transition", soft_obs.transition_ids)
    evaluation = engine.evaluate(f.forecast_ids, 100, 100)
    record("matched baseline truth", len(evaluation.pairs))
    record("hard state subgroup counts", tuple((g.key, g.count) for g in evaluation.groups))
    transition_forecasts = tuple(
        engine.forecast(
            f.model.fingerprint,
            engine.observe(
                f.spec,
                repo.get(RegimeConditionedSample, p.observation_id).sample_id,
                tuple(
                    engine.publish_snapshot(
                        snapshot(
                            tax,
                            repo.get(
                                ResearchSample,
                                repo.get(RegimeConditionedSample, p.observation_id).sample_id,
                            ),
                            at=at,
                            state=state,
                        )
                    )
                    for at, state in ((58, "A"), (60, "B"))
                ),
            ).fingerprint,
            p.base_forecast_id,
            60,
            p.base_probability_id,
        ).fingerprint
        for p in forecasts
    )
    transition_eval = engine.evaluate(transition_forecasts, 100, 100)
    record(
        "transition-origin cohort",
        tuple(g.count for g in transition_eval.groups if g.key.startswith("transition:")),
    )
    ranked = engine.evaluate_rank(rank.fingerprint, 100, 100)
    record(
        "cross-sectional IC",
        repo.get(CrossSectionEvaluation, ranked.cross_section_evaluation_id).pearson.value,
    )
    test_eval = engine.evaluate(f.test_ids, 100, 100, "offline-regime-demo-test")
    old_model = canonical_json(f.model)
    drift = engine.drift(evaluation.fingerprint, test_eval.fingerprint, 100)
    assert canonical_json(repo.get(RegimeConditionedModel, f.model.fingerprint)) == old_model
    record("descriptive drift without refit", drift.status)
    record("TEST seal", test_eval.test_evaluation_id)
    old = canonical_json(first)
    corrected = engine.publish_snapshot(
        replace(repo.get(RegimeSnapshot, first.regime_snapshot_id or ""), revision="2")
    )
    revised = engine.forecast(
        f.model.fingerprint,
        engine.observe(f.spec, sample.fingerprint, (corrected,)).fingerprint,
        first.base_forecast_id,
        60,
        first.base_probability_id,
    )
    assert (
        revised.fingerprint != first.fingerprint
        and canonical_json(repo.get_any(first.fingerprint)) == old
    )
    record("correction creates new forecast identity", revised.fingerprint)
    record("old forecast bytes frozen", True)
    assessment = engine.assess_calibration(first.fingerprint, (), 100)
    record("separate calibration assessment", assessment.status.value)
    scarce_spec = replace(f.spec, minimum_state_samples=100)
    scarce_train = tuple(
        engine.observe(scarce_spec, obs.sample_id, (obs.regime_snapshot_id or "",))
        for obs in (repo.get(RegimeConditionedSample, i) for i in f.training_ids)
    )
    scarce_model = engine.fit(
        scarce_spec, tuple(obs.fingerprint for obs in scarce_train), 40, 40, 40
    )
    scarce_observation = engine.observe(
        scarce_spec, sample.fingerprint, (first.regime_snapshot_id or "",)
    )
    scarce = engine.forecast(
        scarce_model.fingerprint,
        scarce_observation.fingerprint,
        first.base_forecast_id,
        60,
        first.base_probability_id,
    )
    assert scarce.state == "fallback:use_base" and scarce.value == first.base_value
    record("insufficient-state fallback", scarce.state)
    sector_id = next(i for s, i in f.upstream.group_refs if s == sample.security.fingerprint)
    sector = repo.get(GroupMembership, sector_id)
    assert f.upstream.spec.group is not None
    sector_snapshot = snapshot(
        tax,
        sample,
        subject=RegimeSubject(
            RegimeScope.SECTOR,
            InstrumentId("sector", sector.group_id),
            group_policy=f.upstream.spec.group,
            group_id=sector.group_id,
        ),
    )
    assert engine.observe(
        replace(f.spec, scope=RegimeScope.SECTOR),
        sample.fingerprint,
        (engine.publish_snapshot(sector_snapshot),),
        (sector_id,),
    ).regime_snapshot_id
    record("PIT sector membership", sector_id)
    other = build_fixture(repo, upstream=f.upstream, horizon_index=1)
    assert other.model.fingerprint != f.model.fingerprint
    record("independent horizon identities", other.model.fingerprint)
    audit = engine.audit_lineage(ranked.fingerprint)
    record("bounded unified lineage", len(audit.evidence_ids))
    record("immutable base forecast", canonical_json(repo.get_any(first.base_forecast_id)))
    record(
        "store 1.11 / SQLite12", repo._connection.execute("PRAGMA user_version").fetchone()[0]
    )
    composed, composed_tests = event_composition(repo, f)
    composed_eval = engine.evaluate(composed, 100, 100)
    composed_test_eval = engine.evaluate(composed_tests, 100, 100, "regime-event-demo-TEST")
    assert composed_eval.probability_scores and composed_test_eval.test_evaluation_id
    record("explicit base-event-regime composition", composed_eval.fingerprint)
    record("event-regime TEST evidence", composed_test_eval.test_evaluation_id)
    from examples.regime_horizon_fixture import real_horizons

    actual = real_horizons(repo)
    record("actual one-hour and one-day models", tuple(m.fingerprint for m, _ in actual))
    assert len(steps) >= 32
    return tuple(steps)


def event_composition(
    repo: RegimeRepository, f: RegimeFixture
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Declared target-mean location replacement after an exact event base."""
    from afre.event_conditioned import EventEngine
    from afre.event_conditioned.artifacts import EventConditionedForecast
    from examples.event_conditioned_demo import build_fixture as event_fixture
    from examples.event_conditioned_demo import event

    ec = event_fixture(repo, upstream=f.upstream)
    ee, engine = EventEngine(repo), RegimeEngine(repo)
    spec = replace(
        f.spec, family=RegimeModelFamily.REGIME_TARGET_MEAN, event_model_id=ec.model.fingerprint
    )
    observations = tuple(
        engine.observe(spec, o.sample_id, (o.regime_snapshot_id or "",))
        for o in (repo.get(RegimeConditionedSample, i) for i in f.training_ids)
    )
    model = engine.fit(spec, tuple(o.fingerprint for o in observations), 40, 40, 40)
    test_events = []
    for raw in f.upstream.upstream.tests[0]:
        sample = repo.get(ResearchSample, raw.input.sample_id or "")
        e = ee.publish_event(event(sample, "regime-composition-TEST:" + sample.fingerprint))
        o = ee.observe(ec.spec, sample.fingerprint, (e,))[0]
        test_events.append(
            ee.forecast(
                ec.model.fingerprint, o.fingerprint, raw.point_forecast_id, 80, raw.fingerprint
            ).fingerprint
        )
    outputs = []
    for event_ids, regime_ids in (
        (ec.forecast_ids, f.forecast_ids),
        (tuple(test_events), f.test_ids),
    ):
        forecasts = []
        for identity in event_ids:
            base = repo.get(EventConditionedForecast, identity)
            regime = next(
                repo.get(RegimeConditionedForecast, i)
                for i in regime_ids
                if repo.get(RegimeConditionedForecast, i).security == base.security
            )
            old = repo.get(RegimeConditionedSample, regime.observation_id)
            observed = engine.observe(
                spec, old.sample_id, (old.regime_snapshot_id,) if old.regime_snapshot_id else ()
            )
            forecasts.append(
                engine.forecast(
                    model.fingerprint,
                    observed.fingerprint,
                    base.fingerprint,
                    base.origin.timestamp_ns,
                    base.base_probability_id,
                ).fingerprint
            )
        outputs.append(tuple(sorted(forecasts)))
    return outputs[0], outputs[1]


def main() -> None:
    with TemporaryDirectory() as folder:
        path = Path(folder) / "regime.sqlite"
        with RegimeRepository(path) as repo:
            steps = demonstration(repo)
            payloads = dict(
                repo._connection.execute("SELECT fingerprint,payload FROM rc_artifacts")
            )
            repo.audit()
        with RegimeRepository(path) as repo:
            assert (
                dict(repo._connection.execute("SELECT fingerprint,payload FROM rc_artifacts"))
                == payloads
            )
            repo.audit()
        for n, (name, value) in enumerate(steps, 1):
            print(f"{n:02d}. {name}: {value}")
        print("Restart: byte-identical immutable artifacts")


if __name__ == "__main__":
    main()

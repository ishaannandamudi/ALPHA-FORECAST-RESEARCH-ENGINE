"""37-step offline native research walkthrough; observational stability is descriptive."""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from afre.invariance import (
    ComparabilityStatus,
    EnvironmentMembership,
    EnvironmentSet,
    InvarianceBounds,
    InvarianceEngine,
    InvarianceRepository,
    SampleIntersectionPolicy,
    StabilityMetricName,
    StabilityWeighting,
)
from afre.nonlinear.artifacts import NonlinearForecast
from afre.orthogonalization import SignalObservation
from afre.research_datasets.schema import Partition
from afre.schema import ContractError
from afre.sequence.artifacts import SequenceForecast
from afre.serialization import canonical_json
from afre.target_engine.market_data import TargetBar
from examples.invariance_cohorts import build_cohorts
from examples.invariance_fixture import InvarianceFixture, build_fixture
from examples.invariance_horizons import horizon_analyses

STEPS = (
    "declare chronological time environments",
    "declare hard regime environments",
    "retain soft regime weights",
    "declare event cohorts",
    "declare PIT sector environments",
    "declare exact PIT universe environments",
    "declare quality cohorts",
    "use supplied frozen forecasts and models",
    "evaluate point metrics",
    "evaluate supported probabilistic metrics",
    "evaluate frozen calibration diagnostics",
    "evaluate same-origin IC and rank IC",
    "compare coefficient signs and magnitudes",
    "inspect tree split and path recurrence",
    "inspect fixed sequence readouts",
    "inspect orthogonal projection stability",
    "inspect native uncertainty evidence",
    "measure input distribution shift",
    "measure missingness shift",
    "measure explicit forecast degradation",
    "persist input shift and error delta separately",
    "declare event by regime compound",
    "enforce compound bound",
    "assess actual independent 1h and 1d horizons",
    "distinguish native and common intersections",
    "retain insufficient environments",
    "keep declarations frozen after TEST-source correction",
    "measure descriptive chronological trend",
    "preserve fitted model artifacts",
    "preserve feature and signal sets",
    "make no promotion decision",
    "publish later corrected regime event and group evidence",
    "preserve old analysis bytes",
    "construct a new explicit analysis identity",
    "persist and restart",
    "replay identical semantic artifacts",
    "trace bounded unified audit and lineage",
)


def run_checks(repo: InvarianceRepository, f: InvarianceFixture) -> tuple[str, ...]:
    e = InvarianceEngine(repo)
    old_tables = tuple(
        row[0]
        for row in repo._connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'inv_%' ORDER BY name"
        )
    )
    old = {
        t: repo._connection.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall()
        for t in old_tables
    }
    cohorts = build_cohorts(repo, f)
    soft_spec = e.register(
        replace(
            f.spec,
            environment_set_id=cohorts.environment_set.fingerprint,
            baseline_environment_id=None,
            weighting=StabilityWeighting.EXPLICIT_MEMBERSHIP,
        )
    )
    soft_metrics = e.evaluate(soft_spec.fingerprint, cohorts.membership_ids, 100, 100)
    assert any(m.counts.effective_count < m.counts.included for m in soft_metrics)
    metrics = e.evaluate(f.spec.fingerprint, f.membership_ids, 100, 100)
    assert all(
        any(m.name is name and m.value is not None for m in metrics)
        for name in (
            StabilityMetricName.MAE,
            StabilityMetricName.CRPS,
            StabilityMetricName.COVERAGE,
            StabilityMetricName.PEARSON_IC,
            StabilityMetricName.RANK_IC,
        )
    )
    envs = (
        f.environment_set.definitions[0].fingerprint,
        f.environment_set.definitions[1].fingerprint,
    )
    for identity in (
        f.upstream.upstream.covariances[0].model_id,
        f.upstream.projection.fingerprint,
    ):
        d = e.models(f.spec.fingerprint, tuple((v, identity) for v in envs), 100, 100, True)
        assert d.summaries
    for name in ("tree", "sequence"):
        artifact = repo.get_any(f.upstream.upstream.ids(name)[0])
        assert isinstance(artifact, (NonlinearForecast, SequenceForecast))
        model_id = artifact.model_id
        assert e.models(
            f.spec.fingerprint, tuple((v, model_id) for v in envs), 100, 100
        ).summaries
    assert e.models(
        f.spec.fingerprint,
        tuple((v, f.upstream.upstream.results("mixture")[0]) for v in envs),
        100,
        100,
    ).summaries
    ref = f.upstream.spec.candidate.fingerprint
    obs = tuple(
        i
        for row in f.upstream.partition(Partition.VALIDATION)
        for i in row.observation_ids
        if repo.get(SignalObservation, i).reference_id == ref
    )
    shift = e.shift(f.spec.fingerprint, ref, envs, f.membership_ids, obs, 100, 100)
    mae = tuple(m for m in metrics if m.name is StabilityMetricName.MAE)
    base = next(m for m in mae if m.environment_id == f.spec.baseline_environment_id)
    other = next(m for m in mae if m.environment_id != f.spec.baseline_environment_id)
    c = e.compare(base.fingerprint, other.fingerprint, 100)
    degradation = e.degradation(c.fingerprint)
    assert shift.fingerprint != degradation.fingerprint and shift.missing_fraction_shift == 0
    missing = next(i for i in obs if repo.get(SignalObservation, i).origin.timestamp_ns == 40)
    missing_shift = e.shift(
        f.spec.fingerprint,
        ref,
        (base.environment_id, other.environment_id),
        f.membership_ids,
        tuple(i for i in obs if i != missing),
        100,
        100,
    )
    assert missing_shift.left.missing_fraction == 0.125
    assert missing_shift.right.missing_fraction == 0.0
    assert missing_shift.missing_fraction_shift == -0.125
    assert any(len(d.component_ids) == 2 for d in cohorts.environment_set.definitions)
    try:
        with InvarianceRepository(
            repo._connection.execute("PRAGMA database_list").fetchone()[2],
            InvarianceBounds(compounds=1),
        ) as bounded:
            bounded.get(EnvironmentSet, cohorts.environment_set.fingerprint)
    except ContractError:
        pass
    else:
        raise AssertionError("compound bound bypassed")
    hours = horizon_analyses(repo)
    assert len({m.horizon_id for m in hours}) == 2
    common = e.register(
        replace(f.spec, intersection=SampleIntersectionPolicy.COMMON_INTERSECTION)
    )
    assert all(
        m.counts.included == 4
        for m in e.evaluate(common.fingerprint, f.membership_ids, 100, 100)
    )
    small = e.register(replace(f.spec, minimum_count=20))
    assert all(
        m.status is ComparabilityStatus.INSUFFICIENT_DATA
        for m in e.evaluate(small.fingerprint, f.membership_ids, 100, 100)
    )
    assert e.trend(tuple(m.fingerprint for m in mae), 100).slope_per_nanosecond is not None
    # The AFRE-17 research calls above never changed existing model/calibrator/feature rows.
    for table in old_tables:
        current = repo._connection.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
        assert all(row in current for row in old[table])
    assert not any(hasattr(e, n) for n in ("refit", "prune", "promote", "select_model"))
    before = (
        canonical_json(f.spec),
        canonical_json(f.environment_set),
        tuple(canonical_json(m) for m in metrics),
    )
    test_sample = repo.partition_samples(f.spec.fold_id, Partition.TEST)[0]
    bars = tuple(
        repo.get(TargetBar, row[0])
        for row in repo._connection.execute(
            "SELECT fingerprint FROM target_artifacts "
            "WHERE type_name='TargetBar' ORDER BY fingerprint"
        )
    )
    bar = next(
        b
        for b in bars
        if b.instrument == test_sample.security.instrument
        and b.period.start_ns >= test_sample.timestamp_ns
        and b.period.start_ns < test_sample.timestamp_ns + 5
    )
    with repo.transaction():
        repo.put(replace(bar, close=(bar.close or 0) + 1, predecessor_id=bar.fingerprint))
    from afre.cross_sectional import CrossSectionEngine
    from afre.event_conditioned import EventEngine
    from afre.regime_conditioned import RegimeEngine
    from afre.research_datasets.samples import ResearchSample
    from examples.cross_sectional_demo import group
    from examples.event_conditioned_demo import event
    from examples.regime_conditioned_demo import snapshot, taxonomy

    s = repo.get(ResearchSample, f.spec.sample_ids[0])
    RegimeEngine(repo).publish_snapshot(
        replace(snapshot(taxonomy(), s, received=90), revision="2")
    )
    EventEngine(repo).publish_event(
        event(s, "later-corrected-event", received=90, revision="2")
    )
    CrossSectionEngine(repo).publish_group(group(s.security, "later-corrected-sector", 90))
    assert before == (
        canonical_json(f.spec),
        canonical_json(f.environment_set),
        tuple(
            canonical_json(m)
            for m in e.evaluate(f.spec.fingerprint, f.membership_ids, 100, 100)
        ),
    )
    new_members = tuple(
        e.bind(m.environment_id, m.sample_id, m.source_ids, m.mapping_ids, 101).fingerprint
        for i in f.membership_ids
        if (m := repo.get(EnvironmentMembership, i))
    )
    rebuilt = e.evaluate(f.spec.fingerprint, new_members, 110, 110)
    assert {m.fingerprint for m in rebuilt}.isdisjoint(m.fingerprint for m in metrics)
    assert metrics == e.evaluate(f.spec.fingerprint, f.membership_ids, 100, 100)
    path = repo._connection.execute("PRAGMA database_list").fetchone()[2]
    with InvarianceRepository(path) as reopened:
        assert all(
            canonical_json(reopened.get_any(m.fingerprint)) == canonical_json(m)
            for m in metrics
        )
    audit = e.audit(c.fingerprint)
    assert (
        f.spec.fingerprint in audit.node_ids
        and len(audit.node_ids) <= repo.invariance_bounds.audit_nodes
    )
    return STEPS


def main() -> None:
    with (
        TemporaryDirectory(prefix="afre17-demo-") as folder,
        InvarianceRepository(Path(folder) / "demo.sqlite") as repo,
    ):
        steps = run_checks(repo, build_fixture(repo))
        assert len(steps) == 37
        for n, label in enumerate(steps, 1):
            print(f"{n:02d} PASS: {label}")
        print(
            "Stability across tested environments is descriptive; "
            "no causal proof, significance or profitability claim."
        )


if __name__ == "__main__":
    main()

"""Actual AFRE families retain source bytes and separate exact monitoring identities."""

from dataclasses import replace
from math import log
from pathlib import Path
from statistics import fmean

import pytest

from afre.fusion import FusionArtifact, FusionEngine
from afre.health import HealthDiagnostic as D
from afre.health import (
    HealthEngine,
    HealthMetric,
    HealthObservation,
    HealthRepository,
    HealthSpec,
    HealthStatus,
)
from afre.invariance.artifacts import EnvironmentMembership
from afre.serialization import canonical_json
from afre.uncertainty.artifacts import ForecastUncertaintyDecomposition
from examples.fusion_native import horizon_fixture
from examples.health_native import (
    NativeHealthFixture,
    cohort_monitor,
    matching_family,
    native_monitor,
    parameter_monitor,
)
from tests.health.conftest import HealthCase

NativeCase = tuple[HealthRepository, NativeHealthFixture]


@pytest.mark.parametrize(
    "family",
    (
        "point",
        "gaussian",
        "empirical",
        "calibrated",
        "event",
        "hard-regime",
        "soft-regime",
        "mixture",
        "nonlinear",
        "tree",
        "sequence",
    ),
)
def test_native_forecast_families(native_health_case: NativeCase, family: str) -> None:
    repo, f = native_health_case
    ids = matching_family(repo, f.upstream.upstream.upstream.ids(family))
    before = tuple(canonical_json(repo.get_any(i)) for i in ids)
    result = native_monitor(repo, ids, (D.PREDICTION_MEAN, D.PREDICTIVE_VARIANCE))
    assert len(result.metric_ids) == 2
    assert tuple(canonical_json(repo.get_any(i)) for i in ids) == before
    assert result.action == "NONE_DESCRIPTIVE_ONLY"
    first = repo.resolve(
        HealthMetric,
        next(
            i for i in result.metric_ids if repo.get(HealthMetric, i).kind is D.PREDICTION_MEAN
        ),
    )
    assert first.reference_count and first.current_count
    assert first.reference_value is not None and first.current_value is not None


@pytest.mark.parametrize("kind", ("EVENT", "REGIME", "SECTOR", "UNIVERSE", "CUSTOM"))
def test_native_pit_cohort(native_health_case: NativeCase, kind: str) -> None:
    repo, f = native_health_case
    environment = next(
        d
        for d in f.cohorts.environment_set.definitions
        if d.kind.name == kind
        and (d.membership_kind is None or d.membership_kind.value == "hard")
    )
    result = cohort_monitor(repo, f, environment.fingerprint)
    metric = repo.resolve(HealthMetric, result.metric_ids[0])
    spec = repo.get(HealthSpec, metric.spec_id)
    assert spec.environment_id == environment.fingerprint
    admitted_samples = set(metric.reference_sample_ids + metric.current_sample_ids)
    expected = {
        repo.get(EnvironmentMembership, i).sample_id
        for i in spec.membership_ids
        if repo.get(EnvironmentMembership, i).weight == 1
    }
    assert admitted_samples <= expected
    assert metric.reference_count >= 2 and metric.current_count >= 2
    assert metric.status is not HealthStatus.INCOMPARABLE


def test_soft_cohort_explicit_incomparable(native_health_case: NativeCase) -> None:
    repo, f = native_health_case
    environment = next(
        d
        for d in f.cohorts.environment_set.definitions
        if d.membership_kind is not None and d.membership_kind.value == "soft"
    )
    result = cohort_monitor(repo, f, environment.fingerprint)
    assert result.status is HealthStatus.INCOMPARABLE


def test_native_uncertainty_oracles(native_health_case: NativeCase) -> None:
    repo, f = native_health_case
    ids = f.upstream.upstream.upstream.results("gaussian")
    result = native_monitor(repo, ids, (D.UNCERTAINTY_VARIANCE,))
    metric = repo.resolve(HealthMetric, result.metric_ids[0])
    for obs_ids, value in (
        (metric.reference_observation_ids, metric.reference_value),
        (metric.current_observation_ids, metric.current_value),
    ):
        expected = tuple(
            repo.get(
                ForecastUncertaintyDecomposition, repo.get(HealthObservation, i).source_id
            ).total_variance
            for i in obs_ids
        )
        assert all(v is not None for v in expected)
        assert value == pytest.approx(
            fmean(float(v) for v in expected if v is not None), abs=1e-14
        )


def test_native_residual_and_cost_oracles(native_health_case: NativeCase) -> None:
    repo, f = native_health_case
    residual = native_monitor(
        repo,
        tuple(r.fingerprint for r in f.upstream.upstream.residuals),
        (D.RESIDUAL_VARIANCE_RATIO, D.RAW_REFERENCE_CORRELATION),
        "raw",
    )
    assert all(
        repo.resolve(HealthMetric, i).current_value is not None for i in residual.metric_ids
    )
    result = native_monitor(
        repo, f.cost_sample_ids, (D.GROSS_EDGE, D.COST, D.NET_EDGE, D.TURNOVER)
    )
    for identity in result.metric_ids:
        m = repo.resolve(HealthMetric, identity)
        column = {
            D.GROSS_EDGE: "gross_contribution",
            D.COST: "total_cost",
            D.NET_EDGE: "net_contribution",
        }
        if m.kind in column:
            for obs_ids, value in (
                (m.reference_observation_ids, m.reference_value),
                (m.current_observation_ids, m.current_value),
            ):
                records = tuple(
                    repo.get_any(repo.get(HealthObservation, i).source_id) for i in obs_ids
                )
                expected = fmean(getattr(r, column[m.kind]) for r in records)
                assert value == pytest.approx(expected, abs=1e-14)


def test_native_fusion_weight_oracles(health_case: HealthCase) -> None:
    c = health_case
    f = c.fixture.upstream
    e = FusionEngine(c.repo)
    a = e.fit(f.spec, 0, 0, 0)
    ids = sorted(f.spec.source_ids)
    spec = replace(
        f.spec, name="explicit-weight-change", weights=((ids[0], 0.25), (ids[1], 0.75))
    )
    b = e.fit(spec, 0, 0, 0)
    before = (canonical_json(a), canonical_json(b))
    result = parameter_monitor(
        c.repo,
        a.fingerprint,
        b.fingerprint,
        (
            D.PARAMETER_L1,
            D.PARAMETER_L2,
            D.PARAMETER_CORRELATION,
            D.FUSION_DOMINANCE,
            D.EFFECTIVE_SOURCE_COUNT,
            D.WEIGHT_ENTROPY,
        ),
        "weight",
    )
    metrics = {
        c.repo.get(HealthMetric, i).kind: c.repo.resolve(HealthMetric, i)
        for i in result.metric_ids
    }
    assert metrics[D.PARAMETER_L1].current_value == pytest.approx(0.5)
    assert metrics[D.PARAMETER_L2].current_value == pytest.approx(0.5)
    assert metrics[D.FUSION_DOMINANCE].delta == pytest.approx(0.25)
    assert metrics[D.EFFECTIVE_SOURCE_COUNT].current_value == pytest.approx(1 / 0.625)
    assert metrics[D.WEIGHT_ENTROPY].current_value == pytest.approx(
        -0.25 * log(0.25) - 0.75 * log(0.75)
    )
    assert (
        canonical_json(c.repo.get(FusionArtifact, a.fingerprint)),
        canonical_json(c.repo.get(FusionArtifact, b.fingerprint)),
    ) == before


def test_actual_hour_day_health(tmp_path: Path) -> None:
    with HealthRepository(tmp_path / "horizons.sqlite") as repo:
        result = []
        e = HealthEngine(repo)
        for duration, identity in horizon_fixture(repo):
            ref = e.monitor(identity)
            # Exact self-comparison declares overlapping windows.
            from afre.fusion import FusedForecast

            raw = repo.get(FusedForecast, identity)
            at = raw.origin.timestamp_ns
            row = e.observe(ref.fingerprint, identity, at)
            from afre.health import (
                HealthDiagnosticRequest,
                HealthDirection,
                HealthRule,
                HealthSpec,
                HealthStatistic,
                MonitoringWindow,
            )

            request = HealthDiagnosticRequest(D.PREDICTION_MEAN, "prediction", 1)
            rule = HealthRule(
                "hour-day-rule",
                D.PREDICTION_MEAN,
                HealthDirection.HIGHER_WORSE,
                HealthStatistic.DELTA,
                1,
                1.0,
                2.0,
                ref.available_ns,
            )
            s = HealthSpec(
                "actual-horizon",
                ref.fingerprint,
                ref.target_id,
                ref.horizon_id,
                MonitoringWindow("ref", at, at + 1, at + 1, 1),
                MonitoringWindow("cur", at, at + 1, at + 1, 1),
                (request,),
                ((request.fingerprint, rule.fingerprint),),
                (row.fingerprint,),
                (row.fingerprint,),
                1,
                ref.available_ns,
                allow_overlap=True,
            )
            e.declare(s, (rule,))
            result.append((duration, e.evaluate(s.fingerprint, at + 1)))
        assert {d for d, _ in result} == {3600000000000, 86400000000000}
        assert result[0][1].spec_id != result[1][1].spec_id


@pytest.mark.parametrize(
    "family,kinds",
    (
        (
            "tree",
            (
                D.TREE_SPLIT_RECURRENCE,
                D.TREE_THRESHOLD,
                D.TREE_PATH_RECURRENCE,
                D.TREE_LEAF_SUPPORT,
            ),
        ),
        ("sequence", (D.SEQUENCE_DECAY, D.PARAMETER_L1)),
        ("nonlinear", (D.PARAMETER_L1, D.PARAMETER_L2)),
    ),
)
def test_native_tree_sequence_readouts(
    native_health_case: NativeCase, family: str, kinds: tuple[D, ...]
) -> None:
    from afre.health.sources import reference_for

    repo, f = native_health_case
    identity = f.upstream.upstream.upstream.ids(family)[0]
    ref = reference_for(repo, identity)
    model = repo.get_any(ref.producer_id)
    before = canonical_json(model)
    result = parameter_monitor(
        repo, model.fingerprint, model.fingerprint, kinds, anchors=(identity, identity)
    )
    metrics = tuple(repo.resolve(HealthMetric, i) for i in result.metric_ids)
    assert all(m.delta in (0.0, None) for m in metrics)
    assert all(
        m.status in (HealthStatus.HEALTHY, HealthStatus.UNAVAILABLE, HealthStatus.INCOMPARABLE)
        for m in metrics
    )
    assert canonical_json(repo.get_any(model.fingerprint)) == before


def test_native_rank_health(native_health_case: NativeCase) -> None:
    repo, _ = native_health_case
    identity = repo._connection.execute(
        "SELECT fingerprint FROM cs_artifacts WHERE type_name='CrossSectionRanking'"
    ).fetchone()[0]
    result = parameter_monitor(
        repo, identity, identity, (D.RANK_DISPLACEMENT, D.TOP_K_OVERLAP, D.SIGN_PERSISTENCE)
    )
    metrics = {
        repo.get(HealthMetric, i).kind: repo.resolve(HealthMetric, i) for i in result.metric_ids
    }
    assert metrics[D.RANK_DISPLACEMENT].current_value == 0.0
    assert metrics[D.TOP_K_OVERLAP].current_value == 1.0
    assert metrics[D.SIGN_PERSISTENCE].current_value == 1.0


def test_native_interval_coverage_oracle(native_health_case: NativeCase) -> None:
    from statistics import NormalDist

    from afre.health.probabilities import interval_for
    from afre.probabilistic.artifacts import DistributionParameters
    from afre.research_datasets.samples import ResearchSample
    from afre.target_engine.models import TargetVintage
    from afre.uncertainty.sources import source_for

    repo, f = native_health_case
    ids = f.upstream.upstream.upstream.ids("gaussian")
    result = native_monitor(repo, ids, (D.COVERAGE, D.COVERAGE_ERROR, D.INTERVAL_WIDTH))
    metrics = {
        repo.get(HealthMetric, i).kind: repo.resolve(HealthMetric, i) for i in result.metric_ids
    }
    coverage = []
    widths = []
    for identity in ids:
        source = source_for(repo, identity)
        assert isinstance(source.law, DistributionParameters)
        law = source.law
        assert law.scale is not None and law.location is not None
        low = law.location + law.scale * NormalDist().inv_cdf(0.05)
        high = law.location + law.scale * NormalDist().inv_cdf(0.95)
        sample = repo.get(ResearchSample, source.sample_id)
        assert sample.target_id is not None
        truth = repo.get(TargetVintage, sample.target_id).value
        assert truth is not None
        coverage.append(float(low <= truth <= high))
        widths.append(high - low)
        assert interval_for(repo, identity, (0.05, 0.95)) == pytest.approx((low, high))
    assert metrics[D.COVERAGE].current_value == pytest.approx(fmean(coverage))
    assert metrics[D.COVERAGE_ERROR].current_value == pytest.approx(abs(fmean(coverage) - 0.9))
    assert metrics[D.INTERVAL_WIDTH].current_value == pytest.approx(fmean(widths))


def test_no_native_calibration_mutation(native_health_case: NativeCase) -> None:
    repo, f = native_health_case
    ids = f.upstream.upstream.upstream.ids("calibrated")
    native = tuple(canonical_json(repo.get_any(i)) for i in ids)
    rows = tuple(
        repo._connection.execute(
            "SELECT fingerprint,payload FROM c_artifacts ORDER BY fingerprint"
        )
    )
    native_monitor(repo, ids, (D.PREDICTION_MEAN, D.INTERVAL_WIDTH))
    assert tuple(canonical_json(repo.get_any(i)) for i in ids) == native
    assert (
        tuple(
            repo._connection.execute(
                "SELECT fingerprint,payload FROM c_artifacts ORDER BY fingerprint"
            )
        )
        == rows
    )


def test_sequence_native_state_columns(native_health_case: NativeCase) -> None:
    from math import hypot

    from afre.sequence import SequenceForecast

    repo, f = native_health_case
    ids = tuple(
        row[0]
        for row in repo._connection.execute(
            "SELECT fingerprint FROM sq_artifacts WHERE type_name='SequenceForecast'"
        )
        if repo.get(SequenceForecast, row[0]).state_trajectory
    )
    result = native_monitor(repo, ids, (D.SEQUENCE_STATE_NORM,))
    metric = repo.resolve(HealthMetric, result.metric_ids[0])
    sources = tuple(
        repo.get(HealthObservation, i).source_id for i in metric.current_observation_ids
    )
    expected = tuple(
        hypot(*repo.get(SequenceForecast, i).state_trajectory[-1]) for i in sources
    )
    assert metric.current_value == pytest.approx(fmean(expected))
    empty = native_monitor(
        repo, f.upstream.upstream.upstream.ids("sequence"), (D.SEQUENCE_STATE_NORM,)
    )
    assert empty.status is HealthStatus.INSUFFICIENT_DATA

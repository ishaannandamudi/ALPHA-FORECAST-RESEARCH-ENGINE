"""Exact native truth/forecast IDs, intersections, support and predeclaration rules."""

from dataclasses import replace
from math import fsum, sqrt

import pytest

from afre.invariance import (
    ComparabilityStatus,
    EnvironmentMembership,
    SampleIntersectionPolicy,
    StabilityMetricName,
    StabilityWeighting,
)
from afre.invariance.forecasts import forecast_source
from afre.regime_conditioned.memberships import effective_support
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.schema import ContractError
from afre.serialization import canonical_json
from afre.statistical_models import ModelEngine, PredictionScope
from afre.target_engine.models import TargetVintage
from examples.invariance_cohorts import build_cohorts
from examples.invariance_fixture import native_forecasts
from tests.invariance.conftest import Case


@pytest.mark.parametrize(
    "name",
    [
        StabilityMetricName.MAE,
        StabilityMetricName.MSE,
        StabilityMetricName.RMSE,
        StabilityMetricName.SIGN_ACCURACY,
    ],
)
def test_native_metrics_independent_oracle(case: Case, name: StabilityMetricName) -> None:
    f = case.fixture
    spec = case.engine.register(replace(f.spec, metrics=(name,)))
    results = case.engine.evaluate(spec.fingerprint, f.membership_ids, 100, 100)
    for m in results:
        pairs = []
        for sid in m.sample_ids:
            forecast = next(
                forecast_source(case.repo, i)
                for i in spec.forecast_ids
                if forecast_source(case.repo, i).sample_id == sid
            )
            sample = case.repo.get(ResearchSample, sid)
            truth = case.repo.get(TargetVintage, sample.target_id or "")
            assert truth.value is not None
            pairs.append((forecast.prediction, truth.value))
        errors = [p - y for p, y in pairs]
        expected = {
            StabilityMetricName.MAE: fsum(abs(e) for e in errors) / len(errors),
            StabilityMetricName.MSE: fsum(e * e for e in errors) / len(errors),
            StabilityMetricName.RMSE: sqrt(fsum(e * e for e in errors) / len(errors)),
            StabilityMetricName.SIGN_ACCURACY: sum(
                (p > 0) - (p < 0) == (y > 0) - (y < 0) for p, y in pairs
            )
            / len(pairs),
        }[name]
        assert m.value == pytest.approx(expected, abs=1e-14)
        assert m.counts.truth_available == m.counts.included == 8


@pytest.mark.parametrize("policy", list(SampleIntersectionPolicy))
def test_intersection_policies_exact(case: Case, policy: SampleIntersectionPolicy) -> None:
    f = case.fixture
    s = case.engine.register(
        replace(f.spec, intersection=policy, metrics=(StabilityMetricName.MAE,))
    )
    ms = case.engine.evaluate(s.fingerprint, tuple(reversed(f.membership_ids)), 100, 100)
    assert [m.counts.included for m in ms] == (
        [8, 8] if policy is SampleIntersectionPolicy.PER_ENVIRONMENT_NATIVE else [4, 4]
    )
    c = case.engine.compare(ms[0].fingerprint, ms[1].fingerprint, 100)
    assert c.delta == pytest.approx((ms[1].value or 0) - (ms[0].value or 0))
    assert c.status is (
        ComparabilityStatus.PARTIALLY_COMPARABLE
        if policy is SampleIntersectionPolicy.PER_ENVIRONMENT_NATIVE
        else ComparabilityStatus.COMPARABLE
    )
    if policy is not SampleIntersectionPolicy.PER_ENVIRONMENT_NATIVE:
        assert ms[0].sample_ids == ms[1].sample_ids and ms[0].target_ids == ms[1].target_ids


def test_insufficient_and_later_missing_truth_explicit(case: Case) -> None:
    f = case.fixture
    s = case.engine.register(replace(f.spec, minimum_count=10))
    assert all(
        m.status is ComparabilityStatus.INSUFFICIENT_DATA and m.value is None
        for m in case.engine.evaluate(s.fingerprint, f.membership_ids, 100, 100)
    )
    ms = case.engine.evaluate(f.spec.fingerprint, f.membership_ids, 60, 60)
    assert any(m.counts.missing > 0 for m in ms)
    assert all(m.counts.excluded == m.counts.eligible - m.counts.included for m in ms)


def test_soft_regime_weighted_native_metric(case: Case) -> None:
    f = case.fixture
    cohorts = build_cohorts(case.repo, f)
    s = case.engine.register(
        replace(
            f.spec,
            environment_set_id=cohorts.environment_set.fingerprint,
            baseline_environment_id=None,
            metrics=(StabilityMetricName.MAE,),
            weighting=StabilityWeighting.EXPLICIT_MEMBERSHIP,
        )
    )
    results = case.engine.evaluate(s.fingerprint, cohorts.membership_ids, 100, 100)
    soft = next(d for d in cohorts.environment_set.definitions if d.environment_id == "soft-A")
    m = next(m for m in results if m.environment_id == soft.fingerprint)
    errors, weights = [], []
    for sid, weight in m.weights:
        fcast = next(
            forecast_source(case.repo, i)
            for i in s.forecast_ids
            if forecast_source(case.repo, i).sample_id == sid
        )
        truth = case.repo.get(TargetVintage, case.repo.get(ResearchSample, sid).target_id or "")
        assert truth.value is not None
        errors.append(abs(fcast.prediction - truth.value))
        weights.append(weight)
    assert m.value == pytest.approx(
        sum(e * w for e, w in zip(errors, weights, strict=True)) / sum(weights)
    )
    assert m.counts.effective_count == pytest.approx(effective_support(tuple(weights)))
    assert len(set(weights)) >= 4 and m.counts.effective_count < m.counts.included
    hard = case.engine.register(replace(s, weighting=StabilityWeighting.HARD_ONLY))
    with pytest.raises(ContractError, match="soft membership"):
        case.engine.evaluate(hard.fingerprint, cohorts.membership_ids, 100, 100)


@pytest.mark.parametrize("case_name", ("late", "baseline", "source"))
def test_heldout_settings_and_exact_sources_fail_closed(case: Case, case_name: str) -> None:
    with pytest.raises((ContractError, KeyError)):
        spec = case.fixture.spec
        value = (
            replace(spec, declared_ns=41)
            if case_name == "late"
            else replace(spec, baseline_environment_id="afre.inv_environment:" + "0" * 64)
            if case_name == "baseline"
            else replace(spec, forecast_ids=("afre.inv_environment:" + "0" * 64,))
        )
        case.engine.register(value)


def test_TEST_requires_seal_and_preserves_declarations(case: Case) -> None:
    f = case.fixture
    ids = native_forecasts(case.repo, f.upstream, partition=Partition.TEST)
    samples = tuple(forecast_source(case.repo, i).sample_id for i in ids)
    s = case.engine.register(replace(f.spec, sample_ids=samples, forecast_ids=ids))
    ms = tuple(
        case.engine.bind(d.fingerprint, sid, constructed_ns=80).fingerprint
        for d in f.environment_set.definitions
        for sid in samples
    )
    before = canonical_json(s), canonical_json(f.environment_set)
    with pytest.raises(ContractError, match="TEST"):
        case.engine.evaluate(s.fingerprint, ms, 100, 100)
    values = case.engine.evaluate(s.fingerprint, ms, 100, 100, test_identity="invariance-test")
    assert all(v.test_evaluation_id for v in values)
    assert before == (canonical_json(s), canonical_json(f.environment_set))


def test_TRAIN_is_later_in_sample_description(case: Case) -> None:
    f = case.fixture
    model_id = f.upstream.upstream.covariances[0].model_id
    sample_ids = tuple(
        s.fingerprint for s in case.repo.partition_samples(f.spec.fold_id, Partition.TRAIN)
    )
    points = ModelEngine(case.repo).predict_samples(
        model_id, sample_ids, PredictionScope.IN_SAMPLE, 40
    )
    s = case.engine.register(
        replace(
            f.spec,
            sample_ids=sample_ids,
            forecast_ids=tuple(p.fingerprint for p in points),
            metrics=(StabilityMetricName.MAE,),
        )
    )
    ms = tuple(
        case.engine.bind(d.fingerprint, sid, constructed_ns=40).fingerprint
        for d in f.environment_set.definitions
        for sid in sample_ids
    )
    results = case.engine.evaluate(s.fingerprint, ms, 100, 100)
    assert all(r.status is ComparabilityStatus.INSUFFICIENT_DATA for r in results)
    assert all(not p.historical_admissible for p in points)
    with pytest.raises(ContractError, match="actually constructed"):
        case.engine.metadata(ms[0], case.repo.get(EnvironmentMembership, ms[0]).origin)


def test_degradation_trend_and_no_universal_score(case: Case) -> None:
    f = case.fixture
    metrics = case.engine.evaluate(f.spec.fingerprint, f.membership_ids, 100, 100)
    early = f.spec.baseline_environment_id
    for name in (
        StabilityMetricName.MAE,
        StabilityMetricName.R_SQUARED,
        StabilityMetricName.WIDTH,
    ):
        a = next(m for m in metrics if m.name is name and m.environment_id == early)
        b = next(m for m in metrics if m.name is name and m.environment_id != early)
        c = case.engine.compare(a.fingerprint, b.fingerprint, 100)
        d = case.engine.degradation(c.fingerprint)
        assert d.delta == (b.value or 0) - (a.value or 0)
        assert d.orientation == (
            "higher-is-worse"
            if name is StabilityMetricName.MAE
            else "lower-is-worse"
            if name is StabilityMetricName.R_SQUARED
            else "descriptive-only"
        )
        trend = case.engine.trend((b.fingerprint, a.fingerprint), 100)
        # Centers45.5 and55.5, denominator exactly10 nanoseconds.
        assert trend.slope_per_nanosecond == pytest.approx(
            ((b.value or 0) - (a.value or 0)) / 10
        )

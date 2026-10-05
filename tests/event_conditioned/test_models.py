"""Independent TRAIN means/regressions, truth-free application and matched diagnostics."""

import statistics
from collections import Counter
from dataclasses import replace
from math import fsum, sqrt

import pytest

from afre.cross_sectional import CrossSectionEvaluation
from afre.event_conditioned import (
    EventClass,
    EventConditionedForecast,
    EventModelFamily,
    EventReference,
    EventValueRule,
)
from afre.event_conditioned.artifacts import EventConditionedObservation
from afre.event_conditioned.forecasts import shifted_distribution
from afre.event_conditioned.schema import EventCalibrationStatus
from afre.probabilistic.artifacts import DistributionParameters, QuantileValue
from afre.probabilistic.schema import DistributionFamily
from afre.research_datasets.samples import ResearchSample
from afre.schema import Artifact, ContractError
from afre.serialization import canonical_json
from afre.statistical_models.artifacts import DesignMatrix, PointForecast
from afre.target_engine.models import TargetVintage
from examples.event_conditioned_demo import build_fixture, event
from tests.event_conditioned.conftest import Case


def first(case: Case) -> EventConditionedForecast:
    return next(
        case.repo.get(EventConditionedForecast, i)
        for i in case.fixture.forecast_ids
        if case.repo.get(EventConditionedForecast, i).event_ids
    )


@pytest.mark.parametrize("reverse", [False, True])
def test_class_mean_independent_target_oracle(case: Case, reverse: bool) -> None:
    f = case.fixture
    matrix = case.repo.get(DesignMatrix, f.model.matrix_id)
    rows = {r.sample_id: r for r in matrix.rows}
    groups: dict[str, list[float]] = {}
    for identity in f.training_observation_ids:
        o = case.repo.get(EventConditionedObservation, identity)
        e = case.repo.get(EventReference, o.event_id or "")
        groups.setdefault(e.event_class.value, []).append(rows[o.sample_id].response)
    for name, result, count in f.model.class_values:
        assert result == pytest.approx(statistics.mean(groups[name]), abs=1e-15)
        assert count == len(groups[name])
    ids = tuple(reversed(f.training_observation_ids)) if reverse else f.training_observation_ids
    assert case.engine.fit(f.spec, ids, 40, 40, 40) == f.model


@pytest.mark.parametrize(
    ("family", "key"),
    [
        (EventModelFamily.MATERIALITY_LINEAR, "materiality"),
        (EventModelFamily.SURPRISE_LINEAR, "surprise"),
        (EventModelFamily.EVENT_FEATURE_LINEAR, "novelty"),
    ],
)
def test_linear_coefficients_against_statistics(
    case: Case, family: EventModelFamily, key: str
) -> None:
    f = case.fixture
    originals = tuple(
        case.repo.get(EventConditionedObservation, i) for i in f.training_observation_ids
    )
    example = case.repo.get(EventReference, originals[0].event_id or "")
    attribute = getattr(example, key)
    rule = EventValueRule(key, attribute.semantic_key, use_as_feature=True)
    spec = replace(f.spec, family=family, value_rules=(rule,))
    observations = tuple(
        case.engine.observe(spec, o.sample_id, (o.event_id or "",))[0] for o in originals
    )
    model = case.engine.fit(spec, tuple(o.fingerprint for o in observations), 40, 40, 40)
    rows = {r.sample_id: r for r in case.repo.get(DesignMatrix, model.matrix_id).rows}
    oracle = statistics.linear_regression(
        [dict(o.values)[key] for o in observations],
        [rows[o.sample_id].response for o in observations],
    )
    assert model.coefficients == pytest.approx((oracle.intercept, oracle.slope), abs=1e-14)
    previous = first(case)
    o = case.repo.get(EventConditionedObservation, previous.observation_id)
    new = case.engine.observe(spec, o.sample_id, (o.event_id or "",))[0]
    forecast = case.engine.forecast(
        model.fingerprint, new.fingerprint, previous.base_forecast_id, 60
    )
    assert forecast.value == pytest.approx(
        oracle.intercept + oracle.slope * dict(new.values)[key], abs=1e-14
    )
    result = case.engine.evaluate((forecast.fingerprint,), 100, 100)
    assert any(g.key.startswith(key + ":") and g.count == 1 for g in result.groups)


@pytest.mark.parametrize(
    "kind", ["heldout", "duplicates", "too-few", "events", "class", "start", "spec"]
)
def test_fit_fail_closed(case: Case, kind: str) -> None:
    f = case.fixture
    spec, ids, start = f.spec, f.training_observation_ids, 40
    if kind == "heldout":
        ids = (first(case).observation_id,)
    elif kind == "duplicates":
        ids = (ids[0], ids[0])
    elif kind == "too-few":
        ids = ids[:1]
    elif kind == "events":
        spec = replace(spec, minimum_events=999)
        ids = tuple(
            case.engine.observe(
                spec,
                case.repo.get(EventConditionedObservation, i).sample_id,
                (case.repo.get(EventConditionedObservation, i).event_id or "",),
            )[0].fingerprint
            for i in ids
        )
    elif kind == "class":
        spec = replace(spec, minimum_class_samples=999)
        ids = tuple(
            case.engine.observe(
                spec,
                case.repo.get(EventConditionedObservation, i).sample_id,
                (case.repo.get(EventConditionedObservation, i).event_id or "",),
            )[0].fingerprint
            for i in ids
        )
    elif kind == "start":
        start = 39
    else:
        spec = replace(spec, seed=1)
    with pytest.raises(ContractError):
        case.engine.fit(spec, ids, start, 40, 40)


def test_target_free_application_and_base_bytes(
    case: Case, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = first(case)
    before = canonical_json(case.repo.get(PointForecast, p.base_forecast_id))
    original = case.repo.get

    def guarded(cls: type[Artifact], identity: str) -> Artifact:
        assert cls is not TargetVintage, "application read truth"
        return original(cls, identity)

    monkeypatch.setattr(case.repo, "get", guarded)
    assert (
        case.engine.forecast(
            p.model_id, p.observation_id, p.base_forecast_id, 60, p.base_probability_id
        )
        == p
    )
    assert canonical_json(case.repo.get(PointForecast, p.base_forecast_id)) == before


@pytest.mark.parametrize("kind", ["wrong-base", "early", "late", "TRAIN", "calibrated"])
def test_forecast_exact_boundary(case: Case, kind: str) -> None:
    p = first(case)
    base, observation, clock, probability = (
        p.base_forecast_id,
        p.observation_id,
        60,
        p.base_probability_id,
    )
    if kind == "wrong-base":
        base = next(
            case.repo.get(EventConditionedForecast, i).base_forecast_id
            for i in case.fixture.forecast_ids
            if case.repo.get(EventConditionedForecast, i).security != p.security
        )
    elif kind == "early":
        clock = 59
    elif kind == "late":
        clock = 61
    elif kind == "TRAIN":
        observation = case.fixture.training_observation_ids[0]
    else:
        probability = case.repo._connection.execute(
            "SELECT fingerprint FROM c_forecasts LIMIT 1"
        ).fetchone()[0]
    with pytest.raises((ContractError, KeyError)):
        case.engine.forecast(p.model_id, observation, base, clock, probability)


def test_unseen_class_and_unaffected_fallback(case: Case) -> None:
    p = first(case)
    o = case.repo.get(EventConditionedObservation, p.observation_id)
    sample = case.repo.get(ResearchSample, o.sample_id)
    e = replace(event(sample, "unseen"), event_class=EventClass.MERGER)
    identity = case.engine.publish_event(e)
    observed = case.engine.observe(case.fixture.spec, sample.fingerprint, (identity,))[0]
    forecast = case.engine.forecast(p.model_id, observed.fingerprint, p.base_forecast_id, 60)
    assert forecast.state == "insufficient-class-data" and forecast.shift == 0.0
    unaffected = case.engine.observe(case.fixture.spec, sample.fingerprint, ())[0]
    forecast = case.engine.forecast(p.model_id, unaffected.fingerprint, p.base_forecast_id, 60)
    assert forecast.state == "unaffected" and forecast.shift == 0.0


@pytest.mark.parametrize("family", list(DistributionFamily))
@pytest.mark.parametrize("shift", [-2.0, 0.0, 3.0])
def test_location_shift_exact(family: DistributionFamily, shift: float) -> None:
    if family is DistributionFamily.GAUSSIAN_LOCATION_SCALE:
        d = DistributionParameters(family, 1.0, 2.0)
    elif family is DistributionFamily.EMPIRICAL_RESIDUAL:
        d = DistributionParameters(family, 1.0, 1.0, samples=(-1.0, 0.0, 1.0))
    else:
        d = DistributionParameters(
            family,
            1.0,
            0.0,
            quantile_values=(
                QuantileValue(0.25, 0.0),
                QuantileValue(0.5, 1.0),
                QuantileValue(0.75, 2.0),
            ),
        )
    translated = shifted_distribution(d, shift)
    assert translated.location == d.location + shift
    assert translated.scale == d.scale
    assert translated.samples == d.samples
    assert tuple(q.value for q in translated.quantile_values) == tuple(
        q.value + shift for q in d.quantile_values
    )


def test_matched_deltas_groups_and_probability_scores(case: Case) -> None:
    result = case.engine.evaluate(case.fixture.forecast_ids, 100, 100)
    assert len(result.pairs) == 4 and result.affected_count == 3 and result.coverage == 0.75
    for field, predictions in (
        (result.base_metrics, [p.base for p in result.pairs]),
        (result.conditioned_metrics, [p.conditioned for p in result.pairs]),
    ):
        metrics = {m.name.value: m.value for m in field}
        errors = [a - p.truth for a, p in zip(predictions, result.pairs, strict=True)]
        assert metrics["mae"] == pytest.approx(statistics.mean(abs(e) for e in errors))
        assert metrics["mse"] == pytest.approx(statistics.mean(e * e for e in errors))
    for a, b, delta in zip(
        result.conditioned_metrics, result.base_metrics, result.deltas, strict=True
    ):
        if a.value is not None and b.value is not None:
            assert delta.value == pytest.approx(a.value - b.value)
    counts = Counter(
        case.repo.get(
            EventReference, case.repo.get(EventConditionedForecast, p.forecast_id).event_ids[0]
        ).event_class.value
        for p in result.pairs
        if case.repo.get(EventConditionedForecast, p.forecast_id).event_ids
    )
    assert {
        g.key.removeprefix("class:"): g.count
        for g in result.groups
        if g.key.startswith("class:")
    } == counts
    assert len(result.probability_scores) == 4
    assert all(not g.base_metrics for g in result.groups if g.state == "insufficient-data")
    by_sample = {p.sample_id: p for p in result.pairs}
    for group in result.groups:
        if group.state == "available":
            pairs = [by_sample[i] for i in group.sample_ids]
            assert next(
                m.value for m in group.base_metrics if m.name.value == "mae"
            ) == pytest.approx(statistics.mean(abs(p.base - p.truth) for p in pairs))
            assert next(
                m.value for m in group.conditioned_metrics if m.name.value == "mse"
            ) == pytest.approx(statistics.mean((p.conditioned - p.truth) ** 2 for p in pairs))
    from afre.probabilistic.artifacts import ProbabilisticForecast

    for identity in case.fixture.forecast_ids:
        forecast = case.repo.get(EventConditionedForecast, identity)
        raw = case.repo.get(ProbabilisticForecast, forecast.base_probability_id or "")
        assert forecast.distribution is not None
        assert forecast.distribution.location == raw.distribution.location + forecast.shift
        assert forecast.distribution.samples == raw.distribution.samples
        assert tuple(q.value for q in forecast.quantiles) == pytest.approx(
            tuple(q.value + forecast.shift for q in raw.quantiles), abs=1e-15
        )
        for probability in forecast.probabilities:
            atoms = [
                forecast.distribution.location + sample
                for sample in forecast.distribution.samples
            ]
            assert probability.probability == sum(
                v > probability.request.value for v in atoms
            ) / len(atoms)
    before_truth = case.engine.evaluate(case.fixture.forecast_ids, 60, 60)
    assert not before_truth.pairs and len(before_truth.exclusions) == 4


def test_conditioned_ic_independent_pearson(case: Case) -> None:
    rank = case.engine.rank(
        case.fixture.upstream.spec, case.fixture.forecast_ids, case.fixture.upstream.group_refs
    )
    assert len(rank.affected_ids) == 3 and len(rank.unaffected_ids) == 1
    result = case.engine.evaluate_rank(rank.fingerprint, 100, 100)
    cs = case.repo.get(CrossSectionEvaluation, result.cross_section_evaluation_id)
    from afre.cross_sectional.artifacts import CrossSectionRanking, CrossSectionTruth

    ranking = case.repo.get(CrossSectionRanking, rank.ranking_id)
    truth = case.repo.get(CrossSectionTruth, cs.truth_id)
    lookup = {r.security.fingerprint: r.value for r in truth.rows}
    x = [e.normalized for e in ranking.entries if e.rank is not None]
    y = [lookup[e.security.fingerprint] for e in ranking.entries if e.rank is not None]
    assert all(v is not None for v in (*x, *y))
    xx, yy = [float(v or 0) for v in x], [float(v or 0) for v in y]
    mx, my = statistics.mean(xx), statistics.mean(yy)
    oracle = fsum((a - mx) * (b - my) for a, b in zip(xx, yy, strict=True)) / sqrt(
        fsum((a - mx) ** 2 for a in xx) * fsum((b - my) ** 2 for b in yy)
    )
    assert cs.pearson.value == pytest.approx(oracle, abs=1e-14)


def test_calibration_refuses_unconditioned_and_TEST(case: Case) -> None:
    p = first(case)
    result = case.engine.assess_calibration(p.fingerprint, (), 100)
    assert result.status is EventCalibrationStatus.INSUFFICIENT_DATA
    result = case.engine.assess_calibration(p.fingerprint, case.fixture.forecast_ids, 100)
    assert result.status is EventCalibrationStatus.UNAVAILABLE
    with pytest.raises(ContractError):
        case.engine.assess_calibration(p.fingerprint, (p.fingerprint, p.fingerprint), 100)
    with pytest.raises(ContractError):
        case.engine.assess_calibration(p.fingerprint, (), 59)
    with pytest.raises(ContractError):
        replace(result, status=EventCalibrationStatus.SUPPORTED)


def test_separate_horizon_model_forecast_identity(case: Case) -> None:
    second = build_fixture(case.repo, upstream=case.fixture.upstream, horizon_index=1)
    assert second.model.fingerprint != case.fixture.model.fingerprint
    assert second.spec.window.target.horizon != case.fixture.spec.window.target.horizon
    assert set(second.forecast_ids).isdisjoint(case.fixture.forecast_ids)
    result = case.engine.evaluate(second.forecast_ids, 100, 100)
    assert all(
        case.repo.get(TargetVintage, p.target_id).definition == second.spec.window.target
        for p in result.pairs
    )
    with pytest.raises(ContractError, match="mixed"):
        case.engine.evaluate((second.forecast_ids[0], case.fixture.forecast_ids[0]), 100, 100)


def test_native_TEST_seal_reuse_and_calibration_isolation(case: Case) -> None:
    forecasts = []
    for raw in case.fixture.upstream.upstream.tests[0]:
        sample = case.repo.get(ResearchSample, raw.input.sample_id or "")
        identity = case.engine.publish_event(event(sample, "test:" + sample.fingerprint))
        o = case.engine.observe(case.fixture.spec, sample.fingerprint, (identity,))[0]
        forecasts.append(
            case.engine.forecast(
                case.fixture.model.fingerprint,
                o.fingerprint,
                raw.point_forecast_id,
                80,
                raw.fingerprint,
            ).fingerprint
        )
    ids = tuple(forecasts)
    with pytest.raises(ContractError, match="TEST"):
        case.engine.evaluate(ids, 100, 100)
    result = case.engine.evaluate(ids, 100, 100, "event-final-holdout")
    assert result.test_evaluation_id is not None
    assert case.engine.evaluate(ids, 100, 100, "event-final-holdout") == result
    with pytest.raises(ContractError, match="reuse"):
        case.engine.evaluate(ids, 110, 110, "event-final-holdout")
    with pytest.raises(ContractError, match="non-TRAIN/non-TEST"):
        case.engine.assess_calibration(ids[0], ids, 100)


def test_reaction_linear_fit_and_unmatched_exclusion(case: Case) -> None:
    from afre.cross_sectional import CrossSectionEngine
    from afre.event_conditioned import EventRelation
    from examples.cross_sectional_demo import external

    f = case.fixture
    spec = replace(
        f.spec,
        family=EventModelFamily.EVENT_FEATURE_LINEAR,
        window=replace(f.spec.window, relation=EventRelation.POST_EVENT, post_maximum_age_ns=2),
        reaction_specs=(f.upstream.spec.score,),
    )
    observations: list[EventConditionedObservation] = []
    xs, ys = [], []
    rows = {r.sample_id: r for r in case.repo.get(DesignMatrix, f.model.matrix_id).rows}
    for index, original_id in enumerate(f.training_observation_ids):
        original = case.repo.get(EventConditionedObservation, original_id)
        sample = case.repo.get(ResearchSample, original.sample_id)
        e = case.engine.publish_event(
            event(sample, "reaction-fit:" + sample.fingerprint, at=sample.timestamp_ns - 1)
        )
        if index == 0:
            observations.extend(case.engine.observe(spec, sample.fingerprint, (e,)))
            continue
        signal = external(sample.security, sample.timestamp_ns, float(index))
        CrossSectionEngine(case.repo).publish_external(signal)
        observations.extend(
            case.engine.observe(spec, sample.fingerprint, (e,), (signal.fingerprint,))
        )
        xs.append(float(index))
        ys.append(rows[sample.fingerprint].response)
    model = case.engine.fit(spec, tuple(o.fingerprint for o in observations), 40, 40, 40)
    oracle = statistics.linear_regression(xs, ys)
    assert model.coefficients == pytest.approx((oracle.intercept, oracle.slope), abs=1e-14)
    assert len(model.excluded_ids) == 1

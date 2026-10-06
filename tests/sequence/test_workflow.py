"""Independent normalization, probability, matched truth, ranking and diagnostics."""

import math
from dataclasses import replace
from statistics import mean, pstdev

import pytest

from afre.mixture import MixtureForecast
from afre.nonlinear import NonlinearForecast
from afre.probabilistic.artifacts import ProbabilisticForecast
from afre.probabilistic.distributions import conditional_variance, expected_value, quantile
from afre.research_datasets.samples import ResearchSample
from afre.schema import ContractError
from afre.sequence import (
    SequenceForecast,
    SequenceModelArtifact,
    SequenceSnapshot,
    SequenceTransformArtifact,
)
from afre.serialization import canonical_json
from afre.statistical_models.schema import MetricName
from tests.sequence.conftest import Case


@pytest.mark.parametrize("index", [0, 1])
def test_fitted_family_contributions(case: Case, index: int) -> None:
    model = case.fixture.models[index]
    forecast = case.repo.get(SequenceForecast, case.fixture.forecasts[index][0])
    assert model.iterations == 1 and model.convergence == "direct-QR-solved"
    assert forecast.value == pytest.approx(
        model.intercept + math.fsum(c.contribution for c in forecast.contributions)
    )
    assert all(
        c.contribution == c.transformed_value * c.temporal_weight * c.readout_coefficient
        for c in forecast.contributions
    )
    if index == 1:
        assert forecast.state_trajectory[-1] == pytest.approx(forecast.aggregates)
    else:
        assert not forecast.state_trajectory


def test_train_normalization_independent(case: Case) -> None:
    state = case.repo.get(SequenceTransformArtifact, case.fixture.models[0].transform_id)
    snapshots = [case.repo.get(SequenceSnapshot, i) for _, i in case.fixture.bindings]
    columns = [
        [v for s in snapshots for r in s.values for v in (r[j],) if v is not None]
        for j in range(len(state.centers))
    ]
    assert state.centers == pytest.approx(tuple(mean(c) for c in columns))
    assert state.scales == pytest.approx(tuple(pstdev(c) for c in columns))
    assert state.counts == tuple(len(c) for c in columns)


def test_probability_shape_translation(case: Case) -> None:
    forecast = case.forecast
    assert forecast.probability is not None
    view = forecast.probability
    base = case.repo.get(ProbabilisticForecast, view.base_forecast_id)
    assert expected_value(view.distribution) == pytest.approx(forecast.value)
    assert conditional_variance(view.distribution) == conditional_variance(base.distribution)
    assert view.distribution.samples == base.distribution.samples
    assert all(
        q.value == pytest.approx(quantile(base.distribution, q.level) + view.shift)
        for q in view.quantiles
    )


@pytest.mark.parametrize("family", ["sequence", "nonlinear", "mixture"])
def test_matched_comparison(case: Case, family: str) -> None:
    if family == "sequence":
        items = [case.repo.get(SequenceForecast, i) for i in case.fixture.forecasts[1]]
        bases = tuple((f.sample_id, f.fingerprint) for f in items)
    elif family == "nonlinear":
        bases = tuple(
            (case.repo.get(NonlinearForecast, i).sample_id, i)
            for i in case.fixture.upstream.forecast_ids[0]
        )
    else:
        bases = tuple(
            (case.repo.get(MixtureForecast, i).request.sample_id, i)
            for i in case.fixture.upstream.upstream.forecast_ids
        )
    result = case.engine.evaluate(case.fixture.forecasts[0], 100, 100, bases)
    mse = sum((p.prediction - p.truth) ** 2 for p in result.pairs) / len(result.pairs)
    bmse = sum(
        (p.baseline - p.truth) ** 2 for p in result.pairs if p.baseline is not None
    ) / len(result.pairs)
    assert next(m.value for m in result.metrics if m.name is MetricName.MSE) == pytest.approx(
        mse
    )
    assert next(m.value for m in result.deltas if m.name is MetricName.MSE) == pytest.approx(
        mse - bmse
    )
    assert all(
        case.repo.get(ResearchSample, p.sample_id).target_id == p.target_id
        for p in result.pairs
    )
    assert result.proper_scores
    assert any(n.startswith("event:") for n, _ in result.cohorts)
    assert any(n.startswith("regime-active:") for n, _ in result.cohorts)
    with pytest.raises(ContractError, match="grid"):
        case.engine.evaluate(case.fixture.forecasts[0], 100, 100, bases[:-1])


def test_rank_and_exact_ic(case: Case) -> None:
    cs = case.fixture.upstream.upstream.upstream.upstream
    rank = case.engine.rank(cs.spec, case.fixture.forecasts[0], cs.group_refs)
    result = case.engine.evaluate_rank(rank.fingerprint, 100, 100)
    assert result.ranking_id == rank.fingerprint
    assert case.engine.audit_lineage(result.fingerprint).node_ids


def test_stability_coefficient_range_and_no_refit(case: Case) -> None:
    first = case.fixture.models[0]
    before = canonical_json(first)
    spec = replace(case.fixture.specs[0], seed=7, ridge_penalty=0.1)
    state = case.engine.fit_transform(spec, case.fixture.bindings, 40, 40, 40)
    dataset = case.engine.dataset(spec, state.fingerprint, 40)
    second = case.engine.fit(spec, dataset.fingerprint, 40, 40, 40)
    result = case.engine.stability((first.fingerprint, second.fingerprint), 100)
    old_state = case.repo.get(SequenceTransformArtifact, first.transform_id)
    expected = tuple(
        abs(a / sa - b / sb)
        for a, b, sa, sb in zip(
            first.coefficients, second.coefficients, old_state.scales, state.scales, strict=True
        )
    )
    assert tuple(v for _, v in result.coefficient_ranges) == pytest.approx(expected)
    assert any(v > 0 for v in expected)
    assert canonical_json(case.repo.get(SequenceModelArtifact, first.fingerprint)) == before
    with pytest.raises(ContractError, match="compatible"):
        case.engine.stability(tuple(m.fingerprint for m in case.fixture.models), 100)
    assert case.engine.audit_lineage(result.fingerprint).node_ids


def test_coverage_and_calibration_states(case: Case) -> None:
    coverage = case.engine.coverage(tuple(i for _, i in case.fixture.validation), 100)
    assert dict(coverage.counts)["eligible_origins"] == len(case.fixture.validation)
    assert coverage.exclusions
    ids = case.fixture.forecasts[0]
    assert case.engine.assess_calibration(ids[0], ids, 100).status == "unavailable"
    assert case.engine.assess_calibration(ids[0], ids[:1], 100, 2).status == "insufficient"
    identity = case.repo._connection.execute(
        "SELECT fingerprint FROM c_artifacts WHERE type_name='CalibrationState' LIMIT 1"
    ).fetchone()[0]
    assert (
        case.engine.assess_calibration(ids[0], ids, 100, proposed_state_id=identity).status
        == "incompatible"
    )
    assert case.engine.audit_lineage(coverage.fingerprint).node_ids


def test_test_seal_and_train_rejection(case: Case) -> None:
    with pytest.raises(ContractError, match="TEST identity"):
        case.engine.evaluate(case.fixture.test_forecasts, 200, 200)
    result = case.engine.evaluate(
        case.fixture.test_forecasts, 200, 200, test_identity="sequence-final"
    )
    assert result.test_evaluation_id
    assert (
        case.engine.evaluate(
            case.fixture.test_forecasts, 200, 200, test_identity="sequence-final"
        )
        == result
    )
    with pytest.raises(ContractError):
        case.engine.fit_transform(case.fixture.specs[0], case.fixture.test, 40, 40, 40)
    with pytest.raises(ContractError):
        case.engine.predict(case.fixture.models[0].fingerprint, *case.fixture.bindings[0], 40)


def test_point_baseline_and_duplicate_requests(case: Case) -> None:
    from afre.statistical_models.artifacts import PointForecast

    ids = case.repo._connection.execute(
        "SELECT fingerprint FROM m_artifacts WHERE type_name='PointForecast'"
    ).fetchall()
    samples = {case.repo.get(SequenceForecast, i).sample_id for i in case.fixture.forecasts[0]}
    baselines = tuple(
        (p.input.sample_id, p.fingerprint)
        for row in ids
        if (p := case.repo.get(PointForecast, row[0])).input.sample_id in samples
    )
    assert case.engine.evaluate(case.fixture.forecasts[0], 100, 100, baselines).baseline_metrics
    with pytest.raises(ContractError, match="duplicates"):
        case.engine.evaluate((case.forecast.fingerprint,) * 2, 100, 100)
    with pytest.raises(ContractError):
        case.engine.assess_calibration(
            case.forecast.fingerprint, case.fixture.test_forecasts, 200
        )


def test_unpenalized_fit(case: Case) -> None:
    from afre.sequence import SequencePreprocessing

    spec = replace(
        case.fixture.specs[0],
        features=(case.micro,),
        ridge_penalty=0.0,
        preprocessing=SequencePreprocessing.NONE,
    )
    bindings = []
    for sample_id, snapshot_id in case.fixture.bindings:
        previous = case.repo.get(SequenceSnapshot, snapshot_id)
        snapshot = case.engine.snapshot(previous.origin, spec.features, spec.window, 40)
        bindings.append((sample_id, snapshot.fingerprint))
    state = case.engine.fit_transform(spec, tuple(bindings), 40, 40, 40)
    assert state.centers == (0.0,) and state.scales == (1.0,)
    dataset = case.engine.dataset(spec, state.fingerprint, 40, snapshot_hook=lambda: None)
    model = case.engine.fit(spec, dataset.fingerprint, 40, 40, 40)
    assert model.qr_rank == 2


def test_rank_cannot_link_different_evaluation_cutoff(case: Case) -> None:
    from afre.cross_sectional.engine import CrossSectionEngine
    from afre.sequence import SequenceEvaluation

    cs = case.fixture.upstream.upstream.upstream.upstream
    rank = case.engine.rank(cs.spec, case.fixture.forecasts[0], cs.group_refs)
    result = case.engine.evaluate_rank(rank.fingerprint, 100, 100)
    matched = case.repo.get(SequenceEvaluation, result.matched_id)
    grid = tuple(
        (case.repo.get(SequenceForecast, p.forecast_id).security.fingerprint, p.target_id)
        for p in matched.pairs
    )
    later = CrossSectionEngine(case.repo).evaluate(rank.ranking_id, grid, 101, 101)
    with pytest.raises(ContractError, match="exact truth/cutoff"), case.repo.transaction():
        case.repo.put(replace(result, cross_section_id=later.fingerprint))

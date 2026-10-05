"""Matched truth, proper scores, diagnostics, TEST sealing and exact rank integration."""

from dataclasses import replace
from math import fsum, sqrt

import pytest

from afre.mixture import MixtureForecast, MixtureRepository
from afre.mixture.schema import MixtureCalibrationStatus
from afre.probabilistic.definitions import ThresholdRequest
from afre.probabilistic.schema import ScoreState, ThresholdComparison
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.schema import ContractError
from afre.serialization import canonical_json
from afre.statistical_models.schema import MetricName
from examples.mixture_horizon_fixture import horizon_mixtures
from tests.mixture.conftest import Case


def test_matched_point_deltas_and_diagnostics_independent_oracle(case: Case) -> None:
    evaluation = case.engine.evaluate(case.fixture.forecast_ids, 100, 100)
    truths = {(p.sample_id, p.target_id) for p in evaluation.pairs}
    for comparison in evaluation.comparisons:
        assert set(comparison.sample_truth_ids) == truths
        identity = comparison.expert_id
        mixture_mae = fsum(abs(p.mixture - p.truth) for p in evaluation.pairs) / len(truths)
        expert_mae = fsum(
            abs((dict(p.experts)[identity] or 0.0) - p.truth) for p in evaluation.pairs
        ) / len(truths)
        assert next(
            m.value for m in comparison.deltas if m.name is MetricName.MAE
        ) == pytest.approx(mixture_mae - expert_mae)
    diagnostic = case.engine.diagnostics(evaluation.fingerprint)
    assert diagnostic.mean_effective_expert_count == pytest.approx(6.0)
    assert diagnostic.mean_weight_entropy == pytest.approx(1.0)
    assert diagnostic.fallback_frequency == diagnostic.missingness_frequency == 0.0
    for expert in diagnostic.experts:
        assert (
            expert.mean_weight
            == expert.median_weight
            == expert.minimum_weight
            == expert.maximum_weight
            == 1 / 6
        )
        assert expert.availability_rate == expert.contribution_frequency == 1.0
    for a, b, prediction, residual, disagreement in diagnostic.correlations:
        x = tuple(dict(p.experts)[a] for p in evaluation.pairs)
        y = tuple(dict(p.experts)[b] for p in evaluation.pairs)
        assert all(v is not None for v in (*x, *y))
        xx, yy = tuple(float(v or 0.0) for v in x), tuple(float(v or 0.0) for v in y)
        mx, my = fsum(xx) / len(xx), fsum(yy) / len(yy)
        vx, vy = fsum((v - mx) ** 2 for v in xx), fsum((v - my) ** 2 for v in yy)
        if vx and vy:
            oracle = fsum((u - mx) * (v - my) for u, v in zip(xx, yy, strict=True)) / sqrt(
                vx * vy
            )
            assert prediction.value == pytest.approx(oracle, abs=1e-12)
        assert disagreement == pytest.approx(
            fsum(abs(u - v) for u, v in zip(xx, yy, strict=True)) / len(xx)
        )
        assert residual.sample_count == len(xx)


def test_probability_evaluation_reuses_scores_and_exact_intersections(case: Case) -> None:
    ids = tuple(
        i
        for i in case.fixture.probability_ids
        if case.repo.get(MixtureForecast, i).partition is Partition.VALIDATION
    )
    evaluation = case.engine.evaluate(
        ids, 100, 100, thresholds=(ThresholdRequest(0.0, ThresholdComparison.GT),)
    )
    assert len(evaluation.pairs) == 4 and evaluation.probability_scores
    assert any(s.state is ScoreState.UNSUPPORTED for s in evaluation.probability_scores)
    for comparison in evaluation.comparisons:
        assert set(comparison.sample_truth_ids) == {
            (p.sample_id, p.target_id) for p in evaluation.pairs
        }
        assert comparison.expert_probability_scores and comparison.probability_deltas


def test_unknown_truth_excluded_and_duplicate_or_mixed_partitions_rejected(case: Case) -> None:
    early = case.engine.evaluate(case.fixture.forecast_ids, 60, 60)
    assert not early.pairs and len(early.exclusions) == 4
    for ids in (
        (case.fixture.forecast_ids[0],) * 2,
        (*case.fixture.forecast_ids, *case.fixture.test_ids),
    ):
        with pytest.raises(ContractError):
            case.engine.evaluate(ids, 100, 100)


def test_test_sealing_and_calibration_statuses(case: Case) -> None:
    with pytest.raises(ContractError, match="TEST identity"):
        case.engine.evaluate(case.fixture.test_ids, 100, 100)
    first = case.engine.evaluate(case.fixture.test_ids, 100, 100, "mixture-independent-test")
    repeat = case.engine.evaluate(case.fixture.test_ids, 100, 100, "mixture-independent-test")
    assert first == repeat and first.test_evaluation_id
    another = case.engine.evaluate(case.fixture.test_ids, 100, 100, "mixture-second-test")
    assert another.test_evaluation_id != first.test_evaluation_id
    empty = case.engine.assess_calibration(case.forecast.fingerprint, (), 100)
    assert empty.status is MixtureCalibrationStatus.INSUFFICIENT_DATA
    enough = case.engine.assess_calibration(
        case.forecast.fingerprint, case.fixture.forecast_ids, 100
    )
    assert enough.status is MixtureCalibrationStatus.UNAVAILABLE
    with pytest.raises(ContractError):
        case.engine.assess_calibration(case.forecast.fingerprint, case.fixture.test_ids, 100)
    with pytest.raises(ContractError):
        replace(enough, status=MixtureCalibrationStatus.SUPPORTED)


def test_rank_ic_and_test_bridge(case: Case) -> None:
    upstream = case.fixture.upstream.upstream
    ranking = case.engine.rank(upstream.spec, case.fixture.forecast_ids, upstream.group_refs)
    evaluation = case.engine.evaluate_rank(ranking.fingerprint, 100, 100)
    assert evaluation.matched_evaluation_id and evaluation.cross_section_evaluation_id
    with pytest.raises(ContractError):
        case.engine.rank(
            upstream.spec,
            (*case.fixture.forecast_ids, *case.fixture.test_ids),
            upstream.group_refs,
        )
    test_forecast = case.repo.get(MixtureForecast, case.fixture.test_ids[0])
    test_sample = case.repo.get(ResearchSample, test_forecast.request.sample_id)
    test_spec = replace(
        upstream.spec,
        identity=replace(
            upstream.spec.identity,
            anchor_origin=test_forecast.origin,
            snapshot_id=test_sample.snapshot_id,
        ),
    )
    test_rank = case.engine.rank(test_spec, case.fixture.test_ids, upstream.group_refs)
    with pytest.raises(ContractError):
        case.engine.evaluate_rank(test_rank.fingerprint, 100, 100)
    assert case.engine.evaluate_rank(test_rank.fingerprint, 100, 100, "mixture-ranked-TEST")


def test_drift_is_descriptive_and_requires_known_disjoint_windows(case: Case) -> None:
    before = canonical_json(case.fixture.learned)
    a = case.engine.diagnostics(
        case.engine.evaluate(case.fixture.forecast_ids, 100, 100).fingerprint
    )
    b = case.engine.diagnostics(
        case.engine.evaluate(case.fixture.test_ids, 100, 100, "mixture-drift-TEST").fingerprint
    )
    drift = case.engine.drift(a.fingerprint, b.fingerprint, 100)
    assert drift.state == "available" and all(v == 0 for _, v in drift.weight_deltas)
    assert case.engine.drift(a.fingerprint, b.fingerprint, 100, 5).state == "insufficient-data"
    for left, right, cutoff in ((a, a, 100), (b, a, 100), (a, b, 99)):
        with pytest.raises(ContractError):
            case.engine.drift(left.fingerprint, right.fingerprint, cutoff)
    assert canonical_json(case.repo.get_any(case.fixture.learned.fingerprint)) == before


def test_actual_hour_day_identity(case: Case) -> None:
    outputs = horizon_mixtures(case.repo)
    assert len(outputs) == 2 and all(len(rows) == 4 for rows in outputs)
    a, b = outputs[0][0], outputs[1][0]
    assert a.origin.timestamp_ns == b.origin.timestamp_ns
    assert (
        a.target_definition_id != b.target_definition_id
        and a.request.gate_id != b.request.gate_id
    )
    with pytest.raises(ContractError):
        case.engine.forecast(replace(a.request, gate_id=b.request.gate_id))


def test_restart_evaluation_bytes(case: Case) -> None:
    evaluation = case.engine.evaluate(case.fixture.forecast_ids, 100, 100)
    diagnostic = case.engine.diagnostics(evaluation.fingerprint)
    values = (case.forecast, case.fixture.learned, evaluation, diagnostic)
    with MixtureRepository(case.path) as reader:
        assert tuple(canonical_json(reader.get_any(v.fingerprint)) for v in values) == tuple(
            canonical_json(v) for v in values
        )


def test_known_availability_shift_changes_weights_without_refit(case: Case) -> None:
    from afre.mixture import ExpertMissingPolicy

    old = case.fixture.fixed
    gate = replace(
        old,
        expert_set=replace(
            old.expert_set, missing_policy=ExpertMissingPolicy.DROP_AND_RENORMALIZE
        ),
    )
    case.engine.publish_gate(gate)
    missing_id = gate.expert_set.expert_ids[0]
    windows = []
    for ids in (case.fixture.forecast_ids, case.fixture.test_ids):
        forecasts = []
        for identity in ids:
            forecast = case.repo.get(MixtureForecast, identity)
            grid = tuple(
                (i, None if forecast.partition is Partition.TEST and i == missing_id else b)
                for i, b in forecast.request.expert_inputs
            )
            request = replace(
                forecast.request,
                gate_id=gate.fingerprint,
                expert_set_id=gate.expert_set.fingerprint,
                expert_inputs=grid,
            )
            forecasts.append(case.engine.forecast(request).fingerprint)
        test_identity = "mixture-known-shift-TEST" if ids == case.fixture.test_ids else None
        evaluation = case.engine.evaluate(tuple(forecasts), 100, 100, test_identity)
        windows.append(case.engine.diagnostics(evaluation.fingerprint))
    before = canonical_json(gate)
    drift = case.engine.drift(windows[0].fingerprint, windows[1].fingerprint, 100)
    assert dict(drift.availability_deltas)[missing_id] == -1.0
    assert dict(drift.weight_deltas)[missing_id] == pytest.approx(-1 / 6)
    assert windows[1].mean_effective_expert_count == pytest.approx(5.0)
    assert windows[1].missingness_frequency == 1.0
    assert canonical_json(case.repo.get_any(gate.fingerprint)) == before

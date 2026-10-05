"""Independent arithmetic oracles, response-free application and exact research joins."""

from dataclasses import replace
from math import fsum
from pathlib import Path
from typing import TypeVar

import pytest

from afre.cross_sectional.artifacts import CrossSectionEvaluation, CrossSectionTruth
from afre.event_conditioned.artifacts import EventConditionedForecast
from afre.probabilistic.artifacts import ProbabilisticForecast
from afre.regime_conditioned import (
    RegimeCalibrationStatus,
    RegimeConditionedEvaluation,
    RegimeConditionedForecast,
    RegimeConditionedModel,
    RegimeConditionedSample,
    RegimeConditioningSpec,
    RegimeFallback,
    RegimeModelFamily,
    RegimeRepository,
    RegimeScope,
)
from afre.schema import Artifact, ContractError
from afre.serialization import canonical_json
from afre.statistical_models.artifacts import DesignMatrix, FittedModelArtifact, ModelFitInputs
from afre.target_engine.models import TargetVintage
from examples.event_conditioned_demo import build_fixture as event_fixture
from examples.regime_conditioned_demo import build_fixture
from examples.regime_horizon_fixture import DAY, HOUR, real_horizons
from tests.regime_conditioned.conftest import Case
from tests.regime_conditioned.test_temporal import context

A = TypeVar("A", bound=Artifact)


def changed(artifact: A, **fields: object) -> A:
    return replace(artifact, **fields)


@pytest.mark.parametrize("soft", [False, True])
def test_independent_state_mean_residual_weighting(case: Case, soft: bool) -> None:
    f = case.soft if soft else case.hard
    base = case.repo.get(FittedModelArtifact, f.spec.base_model_id)
    matrix = case.repo.get(
        DesignMatrix, case.repo.get(ModelFitInputs, base.fit_inputs_id).matrix_id
    )
    rows = {r.sample_id: r for r in matrix.rows}
    observations = sorted(
        (case.repo.get(RegimeConditionedSample, i) for i in f.training_ids),
        key=lambda o: o.sample_id,
    )
    for j, state in enumerate(f.model.state_fits):
        peers = [
            (o, rows[o.sample_id])
            for o in observations
            if o.membership and o.membership.weights[j] > 0
        ]
        weights = tuple(o.membership.weights[j] for o, _ in peers if o.membership)
        y = tuple(
            r.response
            - (
                base.intercept
                + sum(x * b for x, b in zip(r.values, base.coefficients, strict=True))
            )
            for _, r in peers
        )
        expected = fsum(w * v for w, v in zip(weights, y, strict=True)) / fsum(weights)
        assert state.value == pytest.approx(expected, abs=1e-14)
        assert state.count == len(peers) and state.weights == weights
        assert state.effective_support == pytest.approx(
            fsum(weights) ** 2 / fsum(w * w for w in weights)
        )
    for identity in f.forecast_ids:
        p = case.repo.get(RegimeConditionedForecast, identity)
        if p.membership:
            expected = fsum(
                w * (s.value or 0.0)
                for w, s in zip(p.membership.weights, f.model.state_fits, strict=True)
            )
            assert p.shift == pytest.approx(expected)


def test_target_mean_family(case: Case) -> None:
    from statistics import mean

    f = build_fixture(
        case.repo, upstream=case.hard.upstream, family=RegimeModelFamily.REGIME_TARGET_MEAN
    )
    p = case.repo.get(RegimeConditionedForecast, f.forecast_ids[0])
    matrix = case.repo.get(DesignMatrix, f.model.matrix_id)
    rows = {r.sample_id: r.response for r in matrix.rows}
    observations = tuple(case.repo.get(RegimeConditionedSample, i) for i in f.training_ids)
    for state in f.model.state_fits:
        expected = mean(
            rows[o.sample_id]
            for o in observations
            if o.membership and o.membership.hard_state == state.state_id
        )
        assert state.value == pytest.approx(expected, abs=1e-14)
    if p.membership:
        assert p.value == next(
            s.value for s in f.model.state_fits if s.state_id == p.membership.hard_state
        )
    assert f.model.fingerprint != case.hard.model.fingerprint


@pytest.mark.parametrize("policy", list(RegimeFallback))
def test_insufficient_state_and_missing_fallback(case: Case, policy: RegimeFallback) -> None:
    spec = replace(case.hard.spec, minimum_state_samples=100, fallback=policy)
    observations = tuple(
        case.engine.observe(spec, o.sample_id, (o.regime_snapshot_id or "",))
        for o in (case.repo.get(RegimeConditionedSample, i) for i in case.hard.training_ids)
    )
    model = case.engine.fit(spec, tuple(o.fingerprint for o in observations), 40, 40, 40)
    assert all(s.value is None and s.status == "insufficient-data" for s in model.state_fits)
    p, sample, _ = context(case)
    o = case.engine.observe(spec, sample.fingerprint, (p.regime_snapshot_id or "",))
    if policy is RegimeFallback.FAIL:
        with pytest.raises(ContractError, match="fallback FAIL"):
            case.engine.forecast(model.fingerprint, o.fingerprint, p.base_forecast_id, 60)
    else:
        result = case.engine.forecast(model.fingerprint, o.fingerprint, p.base_forecast_id, 60)
        assert result.value == pytest.approx(
            p.base_value
            + (model.global_offset if policy is RegimeFallback.GLOBAL_OFFSET else 0.0)
        )
        assert result.state == "fallback:" + policy.value


def test_train_only_and_fit_clocks(case: Case) -> None:
    f, sample, _ = context(case)
    heldout = case.repo.get(RegimeConditionedSample, f.observation_id)
    with pytest.raises(ContractError, match="TRAIN"):
        case.engine.fit(case.hard.spec, (heldout.fingerprint,), 40, 40, 40)
    with pytest.raises(ContractError, match="before"):
        case.engine.fit(case.hard.spec, case.hard.training_ids, 39, 40, 40)
    with pytest.raises(ContractError, match="duplicates"):
        case.engine.fit(case.hard.spec, case.hard.training_ids * 2, 40, 40, 40)
    with pytest.raises(ContractError, match="clocks"):
        case.engine.fit(case.hard.spec, case.hard.training_ids, 40, 39, 40)
    with pytest.raises(ContractError, match="insufficient"):
        case.engine.fit(case.hard.spec, case.hard.training_ids[:1], 40, 40, 40)


def test_application_truth_guard_and_base_bytes(
    case: Case, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, sample, _ = context(case)
    old = canonical_json(case.repo.get_any(first.base_forecast_id))
    original = case.repo.get

    def guarded(cls: type[A], identity: str) -> A:
        assert cls not in (TargetVintage, DesignMatrix), (
            "application read truth or TRAIN responses"
        )
        return original(cls, identity)

    monkeypatch.setattr(case.repo, "get", guarded)
    result = case.engine.forecast(
        case.hard.model.fingerprint,
        first.observation_id,
        first.base_forecast_id,
        60,
        first.base_probability_id,
    )
    assert result == first and canonical_json(case.repo.get_any(first.base_forecast_id)) == old
    other = next(
        case.repo.get(RegimeConditionedForecast, i)
        for i in case.hard.forecast_ids
        if i != first.fingerprint
    )
    with pytest.raises(ContractError, match="exact base"):
        case.engine.forecast(
            case.hard.model.fingerprint, first.observation_id, other.base_forecast_id, 60
        )
    with pytest.raises(ContractError, match="after origin"):
        case.engine.forecast(
            case.hard.model.fingerprint, first.observation_id, first.base_forecast_id, 61
        )


def test_probability_translation_and_incompatible_base(case: Case) -> None:
    p, _, _ = context(case)
    raw = case.repo.get(ProbabilisticForecast, p.base_probability_id or "")
    assert p.distribution is not None
    assert (
        p.distribution.scale == raw.distribution.scale
        and p.distribution.samples == raw.distribution.samples
    )
    assert p.distribution.location == pytest.approx(raw.distribution.location + p.shift)
    for a, b in zip(p.quantiles, raw.quantiles, strict=True):
        assert a.value == pytest.approx(b.value + p.shift)
    from afre.event_conditioned.forecasts import shifted_distribution
    from afre.probabilistic.artifacts import DistributionParameters, QuantileValue
    from afre.probabilistic.schema import DistributionFamily

    qs = DistributionParameters(
        DistributionFamily.QUANTILE_SET,
        0.0,
        0.0,
        (),
        (QuantileValue(0.1, 0.0), QuantileValue(0.5, 1.0), QuantileValue(0.9, 2.0)),
    )
    assert shifted_distribution(qs, 2.0).quantile_values[1].value == 3.0
    other = next(i for i in case.hard.forecast_ids if i != p.fingerprint)
    other_p = case.repo.get(RegimeConditionedForecast, other)
    with pytest.raises(ContractError, match="exact raw"):
        case.engine.forecast(
            case.hard.model.fingerprint,
            p.observation_id,
            p.base_forecast_id,
            60,
            other_p.base_probability_id,
        )


def test_matched_truth_groups_and_proper_scores(case: Case) -> None:
    result = case.engine.evaluate(case.hard.forecast_ids, 100, 100)
    assert len(result.pairs) == 4 and dict(result.coverage_counts) == {
        "eligible": 4,
        "matched": 3,
        "unmatched": 1,
        "stale": 0,
        "invalid": 0,
        "unsupported": 0,
    }
    assert result.probability_scores
    assert any(g.key == "state:A" for g in result.groups)
    assert all(g.base_metrics == () for g in result.groups if g.count < 2)
    for pair in result.pairs:
        p = case.repo.get(RegimeConditionedForecast, pair.forecast_id)
        assert pair.base == p.base_value and pair.conditioned == p.value
    early = case.engine.evaluate(case.hard.forecast_ids, 60, 60)
    assert not early.pairs and len(early.exclusions) == 4
    soft = case.engine.evaluate(case.soft.forecast_ids, 100, 100)
    assert soft.mean_entropy is not None and len(soft.soft_diagnostics) == 2
    assert not any(g.key.startswith("state:") for g in soft.groups)
    assert sum(d.mean_probability for d in soft.soft_diagnostics) == pytest.approx(1.0)
    with pytest.raises(ContractError, match="mixed"):
        case.engine.evaluate((case.hard.forecast_ids[0], case.soft.forecast_ids[0]), 100, 100)
    with pytest.raises(ContractError, match="duplicates"):
        case.engine.evaluate(case.hard.forecast_ids * 2, 100, 100)


def test_test_seal_and_reuse(case: Case) -> None:
    with pytest.raises(ContractError, match="explicit"):
        case.engine.evaluate(case.hard.test_ids, 100, 100)
    a = case.engine.evaluate(case.hard.test_ids, 100, 100, "regime-test-a")
    b = case.engine.evaluate(case.hard.test_ids, 100, 100, "regime-test-b")
    from afre.research_datasets.splits import TestEvaluation

    seal = case.repo.get(TestEvaluation, b.test_evaluation_id or "")
    assert a.test_evaluation_id in seal.previous_evaluation_ids
    with pytest.raises(ContractError, match="non-TRAIN/non-TEST"):
        case.engine.assess_calibration(case.hard.test_ids[0], case.hard.test_ids, 100)


def test_separate_calibration_statuses(case: Case) -> None:
    p, _, _ = context(case)
    a = case.engine.assess_calibration(p.fingerprint, (), 100)
    assert a.status is RegimeCalibrationStatus.INSUFFICIENT_DATA
    same = tuple(
        i
        for i in case.hard.forecast_ids
        if case.repo.get(RegimeConditionedForecast, i).membership == p.membership
    )
    if len(same) >= 2:
        assert (
            case.engine.assess_calibration(p.fingerprint, same, 100).status
            is RegimeCalibrationStatus.UNAVAILABLE
        )
    state = case.hard.upstream.upstream.spec.bindings[0].calibration_state_id
    assert state
    assert (
        case.engine.assess_calibration(p.fingerprint, (), 100, global_state_id=state).status
        is RegimeCalibrationStatus.INCOMPATIBLE
    )


@pytest.mark.parametrize("global_scope", [False, True])
def test_same_origin_ranking_matched_ic(case: Case, global_scope: bool) -> None:
    f = (
        build_fixture(case.repo, upstream=case.hard.upstream, scope=RegimeScope.GLOBAL)
        if global_scope
        else case.hard
    )
    ranking = case.engine.rank(f.upstream.spec, f.forecast_ids, f.upstream.group_refs)
    result = case.engine.evaluate_rank(ranking.fingerprint, 100, 100)
    cs = case.repo.get(CrossSectionEvaluation, result.cross_section_evaluation_id)
    truth = case.repo.get(CrossSectionTruth, cs.truth_id)
    matched = case.repo.get(RegimeConditionedEvaluation, result.matched_evaluation_id)
    assert {p.target_id for p in matched.pairs} == {
        t.target_id for t in truth.rows if t.value is not None
    }
    assert (cs.pearson.value is None) == global_scope
    assert len(ranking.matched_ids) == (4 if global_scope else 3)
    case.engine.audit_lineage(result.fingerprint)


def test_drift_descriptive_no_auto_refit(case: Case) -> None:
    a = case.engine.evaluate(case.hard.forecast_ids, 100, 100)
    b = case.engine.evaluate(case.hard.test_ids, 100, 100, "drift-test")
    before = canonical_json(case.hard.model)
    drift = case.engine.drift(a.fingerprint, b.fingerprint, 100)
    assert drift.status == "available" and drift.state_probability_deltas
    assert (
        canonical_json(case.repo.get(RegimeConditionedModel, case.hard.model.fingerprint))
        == before
    )
    with pytest.raises(ContractError, match="ordered disjoint"):
        case.engine.drift(a.fingerprint, a.fingerprint, 100)
    assert (
        case.engine.drift(a.fingerprint, b.fingerprint, 100, minimum_count=10).status
        == "insufficient-data"
    )
    with pytest.raises(ContractError, match="known windows"):
        case.engine.drift(a.fingerprint, b.fingerprint, 99)


def test_exact_declared_event_then_target_mean(case: Case) -> None:
    ec = event_fixture(case.repo, upstream=case.hard.upstream)
    spec = replace(
        case.hard.spec,
        family=RegimeModelFamily.REGIME_TARGET_MEAN,
        event_model_id=ec.model.fingerprint,
    )
    observations = tuple(
        case.engine.observe(spec, o.sample_id, (o.regime_snapshot_id or "",))
        for o in (case.repo.get(RegimeConditionedSample, i) for i in case.hard.training_ids)
    )
    model = case.engine.fit(spec, tuple(o.fingerprint for o in observations), 40, 40, 40)
    forecasts = []
    for identity in ec.forecast_ids:
        event = case.repo.get(EventConditionedForecast, identity)
        old = next(
            case.repo.get(RegimeConditionedForecast, i)
            for i in case.hard.forecast_ids
            if case.repo.get(RegimeConditionedForecast, i).security == event.security
        )
        sample = case.repo.get(RegimeConditionedSample, old.observation_id)
        o = case.engine.observe(
            spec, sample.sample_id, (old.regime_snapshot_id,) if old.regime_snapshot_id else ()
        )
        p = case.engine.forecast(
            model.fingerprint, o.fingerprint, event.fingerprint, 60, event.base_probability_id
        )
        assert (
            p.base_value == event.value
            and p.composition_order == "base-event-regime-location-v1"
        )
        assert p.distribution is not None and event.distribution is not None
        assert p.distribution.scale == event.distribution.scale
        forecasts.append(p.fingerprint)
    result = case.engine.evaluate(tuple(forecasts), 100, 100)
    assert any(g.key.startswith("event-base:") for g in result.groups)
    rank = case.engine.rank(
        case.hard.upstream.spec, tuple(forecasts), case.hard.upstream.group_refs
    )
    case.engine.evaluate_rank(rank.fingerprint, 100, 100)
    case.engine.audit_lineage(result.fingerprint)


def test_actual_hour_day_and_heldout_perturbation(tmp_path: Path) -> None:
    outputs = []
    for scale in (1.0, 10.0):
        with RegimeRepository(tmp_path / (str(scale) + ".sqlite")) as repo:
            results = real_horizons(repo, scale)
            assert tuple(
                repo.get(RegimeConditioningSpec, m.spec_id).target.horizon.duration_ns
                for m, _ in results
            ) == (HOUR, DAY)
            assert results[0][0].fingerprint != results[1][0].fingerprint
            outputs.append(tuple(tuple(s.value for s in m.state_fits) for m, _ in results))
            repo.audit()
    assert outputs[0] == outputs[1]


def test_event_composition_test_boundary(case: Case) -> None:
    from examples.regime_conditioned_demo import event_composition

    validation, tests = event_composition(case.repo, case.hard)
    with pytest.raises(ContractError, match="explicit"):
        case.engine.evaluate(tests, 100, 100)
    result = case.engine.evaluate(tests, 100, 100, "event-regime-TEST")
    assert result.test_evaluation_id and result.probability_scores
    audit = case.engine.audit_lineage(result.fingerprint)
    assert any(i.startswith("afre.ec_forecast:") for i in audit.evidence_ids)
    p = next(
        case.repo.get(RegimeConditionedForecast, i)
        for i in case.hard.forecast_ids
        if len(
            tuple(
                j
                for j in case.hard.forecast_ids
                if case.repo.get(RegimeConditionedForecast, j).membership
                == case.repo.get(RegimeConditionedForecast, i).membership
            )
        )
        >= 2
    )
    ids = tuple(
        i
        for i in case.hard.forecast_ids
        if case.repo.get(RegimeConditionedForecast, i).membership == p.membership
    )
    assert (
        case.engine.assess_calibration(p.fingerprint, ids, 100).status
        is RegimeCalibrationStatus.UNAVAILABLE
    )

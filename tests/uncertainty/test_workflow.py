"""All supported source families, explicit measures, calibration, evaluation and drift."""

from dataclasses import replace

import pytest

from afre.schema import ContractError
from afre.uncertainty import (
    ClosurePolicy,
    CovarianceAssumption,
    IdentifiabilityStatus,
    ParameterUncertaintySpec,
    UncertaintyEvaluationSpec,
    UncertaintyInterval,
    UncertaintyMeasure,
    UncertaintyRequest,
    UncertaintySpec,
    UncertaintyType,
)
from examples.uncertainty_demo import component
from examples.uncertainty_horizon_fixture import horizon_uncertainties
from tests.uncertainty.conftest import Case


@pytest.mark.parametrize(
    "name",
    [
        "gaussian",
        "empirical",
        "point",
        "mixture",
        "event",
        "hard-regime",
        "soft-regime",
        "nonlinear",
        "tree",
        "sequence",
        "calibrated",
    ],
)
def test_sources(case: Case, name: str) -> None:
    result = case.result(name)
    spec = case.repo.get(UncertaintySpec, result.spec_id)
    assert case.engine.decompose(spec, 60) == result
    assert result.available_ns == result.computed_ns == result.origin.timestamp_ns
    assert result.horizon_id == spec.target.horizon.fingerprint
    assert result.quality_states
    assert component(result, UncertaintyType.DATA_QUALITY).value is None
    assert component(result, UncertaintyType.DATA_QUALITY).additive is False
    evaluated = case.engine.evaluate(
        case.fixture.results(name), UncertaintyEvaluationSpec(bucket_count=2), 100, 100
    )
    assert len(evaluated.pairs) == 4
    assert all(p.target_id.startswith("afre.target_vintage:") for p in evaluated.pairs)
    assert evaluated.cohorts
    if name == "mixture":
        assert result.closure is ClosurePolicy.EXACT_ADDITIVE
        assert result.closure_error is not None and abs(result.closure_error) < 1e-10
        assert len(result.shares) == 2
        assert component(result, UncertaintyType.ALEATORIC).value is None
        assert evaluated.coverage.interval_count == 0
    if name == "event":
        assert any(n.startswith("event:") for n, _ in evaluated.cohorts)
        assert (
            component(result, UncertaintyType.EVENT_AMBIGUITY).status
            is IdentifiabilityStatus.PROXY_ONLY
        )
    if "regime" in name:
        assert any(n.startswith("regime-active:") for n, _ in evaluated.cohorts)
        assert component(result, UncertaintyType.REGIME_AMBIGUITY).units == "nats"


@pytest.mark.parametrize("measure", list(UncertaintyMeasure))
def test_total_measures(case: Case, measure: UncertaintyMeasure) -> None:
    spec = replace(
        case.repo.get(UncertaintySpec, case.result().spec_id),
        requests=(UncertaintyRequest(UncertaintyType.TOTAL_PREDICTIVE, measure),),
    )
    result = case.engine.decompose(spec, 60)
    value = component(result, UncertaintyType.TOTAL_PREDICTIVE)
    supported = measure in (
        UncertaintyMeasure.VARIANCE,
        UncertaintyMeasure.STANDARD_DEVIATION,
        UncertaintyMeasure.INTERVAL_WIDTH,
    )
    assert (value.value is not None) == supported
    assert value.status is (
        IdentifiabilityStatus.IDENTIFIED if supported else IdentifiabilityStatus.INCOMPATIBLE
    )
    assert not result.shares


@pytest.mark.parametrize(
    "kind,measure",
    [
        (UncertaintyType.PARAMETER, UncertaintyMeasure.STANDARD_DEVIATION),
        (UncertaintyType.ALEATORIC, UncertaintyMeasure.SCORE_VARIANCE),
        (UncertaintyType.MODEL_SPECIFICATION, UncertaintyMeasure.ENTROPY),
        (UncertaintyType.EVENT_AMBIGUITY, UncertaintyMeasure.VARIANCE),
        (UncertaintyType.DATA_QUALITY, UncertaintyMeasure.VARIANCE),
        (UncertaintyType.REGIME_AMBIGUITY, UncertaintyMeasure.DISAGREEMENT),
    ],
)
def test_incompatible_diagnostics(
    case: Case, kind: UncertaintyType, measure: UncertaintyMeasure
) -> None:
    name = (
        "event"
        if kind is UncertaintyType.EVENT_AMBIGUITY
        else "soft-regime"
        if kind is UncertaintyType.REGIME_AMBIGUITY
        else "gaussian"
    )
    spec = replace(
        case.repo.get(UncertaintySpec, case.result(name).spec_id),
        requests=(
            UncertaintyRequest(UncertaintyType.TOTAL_PREDICTIVE),
            UncertaintyRequest(kind, measure),
        ),
    )
    result = case.engine.decompose(spec, 60)
    assert component(result, kind).status is IdentifiabilityStatus.INCOMPATIBLE
    assert component(result, kind).value is None


def test_exact_partial_and_proxy_exclusion(case: Case) -> None:
    old = case.result("mixture")
    spec = replace(
        case.repo.get(UncertaintySpec, old.spec_id),
        requests=tuple(
            UncertaintyRequest(k)
            for k in (
                UncertaintyType.TOTAL_PREDICTIVE,
                UncertaintyType.EXPERT_DISAGREEMENT,
                UncertaintyType.RESIDUAL_UNATTRIBUTED,
                UncertaintyType.PARAMETER,
            )
        ),
    )
    result = case.engine.decompose(spec, 60)
    assert component(result, UncertaintyType.RESIDUAL_UNATTRIBUTED).value == pytest.approx(
        component(old, UncertaintyType.WITHIN_EXPERT_PREDICTIVE).value
    )
    assert UncertaintyType.PARAMETER not in dict(result.shares)
    assert sum(s for _, s in result.shares if s is not None) == pytest.approx(1)
    with pytest.raises(ContractError):
        replace(spec, closure=ClosurePolicy.APPROXIMATE_ADDITIVE)
    with pytest.raises(ContractError):
        case.engine.decompose(replace(spec, forecast_id=case.result().forecast_id), 60)
    with pytest.raises(ContractError, match="closure"):
        case.engine.decompose(
            replace(
                spec,
                requests=tuple(
                    UncertaintyRequest(k)
                    for k in (
                        UncertaintyType.TOTAL_PREDICTIVE,
                        UncertaintyType.EXPERT_DISAGREEMENT,
                    )
                ),
            ),
            60,
        )


def test_regime_spread_is_separate_from_entropy(case: Case) -> None:
    from afre.regime_conditioned.artifacts import (
        RegimeConditionedForecast,
        RegimeConditionedModel,
    )

    old = case.result("soft-regime")
    raw = case.repo.get(RegimeConditionedForecast, old.forecast_id)
    model = case.repo.get(RegimeConditionedModel, raw.model_id)
    assert raw.membership is not None
    values = tuple(f.value or 0 for f in model.state_fits)
    mean = sum(w * v for w, v in zip(raw.membership.weights, values, strict=True))
    expected = sum(
        w * (v - mean) ** 2 for w, v in zip(raw.membership.weights, values, strict=True)
    )
    spec = replace(
        case.repo.get(UncertaintySpec, old.spec_id),
        requests=(
            UncertaintyRequest(UncertaintyType.TOTAL_PREDICTIVE),
            UncertaintyRequest(UncertaintyType.REGIME_AMBIGUITY),
        ),
    )
    value = component(case.engine.decompose(spec, 60), UncertaintyType.REGIME_AMBIGUITY)
    assert value.value == pytest.approx(expected)
    assert value.status is IdentifiabilityStatus.PROXY_ONLY
    assert not value.additive
    assert all(
        component(case.repo.get(type(old), i), UncertaintyType.REGIME_AMBIGUITY).value
        in (None, 0.0)
        for i in case.fixture.results("hard-regime")
    )


def test_covariance_limits(case: Case) -> None:
    from afre.nonlinear.artifacts import NonlinearForecast

    for identity in (
        case.repo.get(NonlinearForecast, case.result("tree").forecast_id).model_id,
        case.fixture.upstream.models[0].fingerprint,
    ):
        result = case.engine.fit_covariance(
            ParameterUncertaintySpec(
                identity, CovarianceAssumption.IID_HOMOSKEDASTIC_CORRECT_LINEAR
            ),
            40,
        )
        assert result.status is IdentifiabilityStatus.INCOMPATIBLE
        assert result.covariance == ()
        assert result.residual_variance is None
    for cov in case.fixture.covariances:
        assert cov.status is IdentifiabilityStatus.PARTIALLY_IDENTIFIED
        assert cov.intercept_included
        limited = case.engine.fit_covariance(
            replace(case.repo.get(ParameterUncertaintySpec, cov.spec_id), minimum_samples=2000),
            40,
        )
        assert limited.status is IdentifiabilityStatus.INSUFFICIENT_DATA
        unstable = case.engine.fit_covariance(
            replace(case.repo.get(ParameterUncertaintySpec, cov.spec_id), condition_limit=1.0),
            40,
        )
        assert unstable.status is IdentifiabilityStatus.INCOMPATIBLE


def test_comparison_drift_test_seal(case: Case) -> None:
    policy = UncertaintyEvaluationSpec(bucket_count=2)
    a = case.engine.evaluate(case.fixture.results("gaussian"), policy, 100, 100)
    b = case.engine.evaluate(
        tuple(reversed(case.fixture.results("empirical"))), policy, 100, 100
    )
    c = case.engine.compare(a.fingerprint, b.fingerprint, 100)
    assert len(c.sample_truth_ids) == 4
    with pytest.raises(ContractError):
        case.engine.evaluate(case.fixture.test_ids, policy, 100, 100)
    test = case.engine.evaluate(case.fixture.test_ids, policy, 100, 100, "uncertainty-test")
    assert test.test_evaluation_id
    assert (
        case.engine.evaluate(case.fixture.test_ids, policy, 100, 100, "uncertainty-test")
        == test
    )
    with pytest.raises(ContractError):
        case.engine.evaluate(case.fixture.test_ids, policy, 101, 101, "uncertainty-test")
    before = tuple(c.fingerprint for c in case.fixture.covariances)
    drift = case.engine.drift((a.fingerprint, test.fingerprint), 100)
    assert test.coverage.mean_variance is not None and a.coverage.mean_variance is not None
    assert drift.variance_shifts[0] == pytest.approx(
        test.coverage.mean_variance - a.coverage.mean_variance
    )
    assert drift.behavior == "descriptive-no-refit-no-selection-v1"
    assert tuple(c.fingerprint for c in case.fixture.covariances) == before
    with pytest.raises(ContractError):
        case.engine.drift((test.fingerprint, a.fingerprint), 100)
    with pytest.raises(ContractError):
        case.engine.drift((a.fingerprint, b.fingerprint), 100)
    with pytest.raises(ContractError):
        case.engine.compare(a.fingerprint, test.fingerprint, 100)
    with pytest.raises(ContractError):
        case.engine.evaluate((case.fixture.results("gaussian")[0],) * 2, policy, 100, 100)
    with pytest.raises(ContractError):
        case.engine.evaluate(case.fixture.results("gaussian"), policy, 59, 100)


def test_horizons_independent(case: Case) -> None:
    values = horizon_uncertainties(case.repo)
    assert len(values) == 2
    assert values[0][0].horizon_id != values[1][0].horizon_id
    assert values[0][0].total_variance == 0.01**2
    assert values[1][0].total_variance == 0.025**2
    assert values[1][0].total_variance / values[0][0].total_variance != 24
    for group in values:
        for d in group:
            assert component(d, UncertaintyType.HORIZON).value == d.total_variance
            assert case.repo.get(UncertaintyInterval, d.interval_id).width is not None

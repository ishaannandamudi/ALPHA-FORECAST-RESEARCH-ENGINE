"""Matched model proxies, point expert diagnostics, sparse intervals and zero-total behavior."""

from dataclasses import replace

import pytest

from afre.calibration.artifacts import IntervalValue
from afre.mixture import MixtureForecast
from afre.probabilistic.artifacts import DistributionParameters, QuantileValue
from afre.probabilistic.schema import DistributionFamily, DistributionState
from afre.schema import ContractError
from afre.statistical_models import ModelEngine, PredictionScope
from afre.statistical_models.artifacts import FittedModelArtifact
from afre.statistical_models.definitions import BaselineModelSpec
from afre.statistical_models.schema import InterceptPolicy
from afre.uncertainty import (
    ClosurePolicy,
    CovarianceAssumption,
    IdentifiabilityStatus,
    ParameterUncertaintySpec,
    UncertaintyEvaluationSpec,
    UncertaintyMeasure,
    UncertaintyRequest,
    UncertaintySpec,
    UncertaintyType,
)
from afre.uncertainty.decomposition import decomposition_for
from afre.uncertainty.intervals import interval_for
from afre.uncertainty.sources import source_for
from examples.uncertainty_demo import component
from tests.uncertainty.conftest import Case


def test_matched_distinct_model_spread(case: Case) -> None:
    raw = source_for(case.repo, case.result().forecast_id)
    candidates = tuple(
        source_for(case.repo, i) for name in ("point", "tree") for i in case.fixture.ids(name)
    )
    ids = tuple(s.artifact.fingerprint for s in candidates if s.sample_id == raw.sample_id)
    assert len(ids) == 2
    spec = replace(
        case.repo.get(UncertaintySpec, case.result().spec_id), alternative_forecast_ids=ids
    )
    result = case.engine.decompose(spec, 60)
    value = component(result, UncertaintyType.MODEL_SPECIFICATION)
    numbers = tuple(source_for(case.repo, i).prediction for i in ids)
    assert value.value == pytest.approx((numbers[0] - numbers[1]) ** 2 / 4)
    assert value.status is IdentifiabilityStatus.PROXY_ONLY and not value.additive
    with pytest.raises(ContractError):
        case.engine.decompose(
            replace(
                spec,
                alternative_forecast_ids=(
                    case.result().forecast_id,
                    case.result("empirical").forecast_id,
                ),
            ),
            60,
        )
    unmatched = next(
        i
        for i in case.fixture.ids("tree")
        if source_for(case.repo, i).sample_id != raw.sample_id
    )
    with pytest.raises(ContractError):
        case.engine.decompose(replace(spec, alternative_forecast_ids=(ids[0], unmatched)), 60)


@pytest.mark.parametrize(
    "measure",
    [UncertaintyMeasure.VARIANCE, UncertaintyMeasure.DISAGREEMENT, UncertaintyMeasure.ENTROPY],
)
def test_point_expert_disagreement(case: Case, measure: UncertaintyMeasure) -> None:
    identity = case.fixture.upstream.upstream.upstream.forecast_ids[0]
    raw = case.repo.get(MixtureForecast, identity)
    target = case.repo.get(UncertaintySpec, case.result().spec_id).target
    spec = UncertaintySpec(
        target,
        identity,
        (
            UncertaintyRequest(UncertaintyType.TOTAL_PREDICTIVE),
            UncertaintyRequest(UncertaintyType.EXPERT_DISAGREEMENT, measure),
        ),
    )
    result = case.engine.decompose(spec, raw.origin.timestamp_ns)
    value = component(result, UncertaintyType.EXPERT_DISAGREEMENT)
    if measure is UncertaintyMeasure.ENTROPY:
        assert value.value is None and value.status is IdentifiabilityStatus.INCOMPATIBLE
    else:
        rows = tuple(c for c in raw.contributions if c.effective_weight > 0)
        mean = sum(c.effective_weight * (c.value or 0) for c in rows)
        expected = (
            sum(c.effective_weight * ((c.value or 0) - mean) ** 2 for c in rows)
            if measure is UncertaintyMeasure.VARIANCE
            else sum(
                a.effective_weight * b.effective_weight * abs((a.value or 0) - (b.value or 0))
                for a in rows
                for b in rows
            )
        )
        assert value.value == pytest.approx(expected)
        assert value.status is IdentifiabilityStatus.PROXY_ONLY
        assert not result.shares


def test_interval_sparse_calibrated_semantics(case: Case) -> None:
    spec = case.repo.get(UncertaintySpec, case.result().spec_id)
    source = source_for(case.repo, spec.forecast_id)
    law = DistributionParameters(
        DistributionFamily.QUANTILE_SET,
        0.0,
        1.0,
        quantile_values=(
            QuantileValue(0.1, -2.0),
            QuantileValue(0.5, 0.0),
            QuantileValue(0.9, 3.0),
        ),
    )
    sparse = replace(source, law=law)
    assert interval_for(spec, sparse, 60).width == 5
    assert (
        interval_for(replace(spec, interval_levels=(0.2, 0.8)), sparse, 60).status
        is IdentifiabilityStatus.INCOMPATIBLE
    )
    stored = IntervalValue(0.1, 0.9, -1.0, 2.0)
    calibrated = replace(source, interval=stored, law=None)
    assert (
        interval_for(spec, calibrated, 60).semantics == "AFRE-7-pinned-calibrated-interval-v1"
    )
    assert interval_for(spec, calibrated, 60).width == 3.0
    assert (
        interval_for(replace(spec, interval_levels=(0.2, 0.8)), calibrated, 60).status
        is IdentifiabilityStatus.INCOMPATIBLE
    )


def test_zero_mixture_total_no_shares(case: Case, monkeypatch: pytest.MonkeyPatch) -> None:
    old = case.result("mixture")
    raw = source_for(case.repo, old.forecast_id)
    assert isinstance(
        raw.law, type(case.repo.get(MixtureForecast, old.forecast_id).distribution)
    )
    from afre.mixture.artifacts import MixtureDistribution

    assert isinstance(raw.law, MixtureDistribution)
    degenerate = DistributionParameters(
        DistributionFamily.EMPIRICAL_RESIDUAL,
        0.0,
        0.0,
        samples=(2.0,),
        state=DistributionState.DEGENERATE,
    )
    law = replace(
        raw.law,
        components=tuple(replace(c, distribution=degenerate) for c in raw.law.components),
    )
    # Independent mathematical source fixture, never persisted as a native forecast forgery.
    monkeypatch.setattr(
        "afre.uncertainty.decomposition.source_for",
        lambda repo, identity: replace(raw, law=law),
    )
    spec = replace(
        case.repo.get(UncertaintySpec, old.spec_id),
        requests=tuple(
            UncertaintyRequest(k)
            for k in (
                UncertaintyType.TOTAL_PREDICTIVE,
                UncertaintyType.WITHIN_EXPERT_PREDICTIVE,
                UncertaintyType.EXPERT_DISAGREEMENT,
            )
        ),
    )
    result, _ = decomposition_for(case.repo, spec, 60)
    assert result.total_variance == 0
    assert all(s is None for _, s in result.shares)
    assert result.closure_error == 0
    assert result.closure is ClosurePolicy.EXACT_ADDITIVE


def test_no_intercept_and_unsupported_constant(case: Case) -> None:
    cov = case.fixture.covariances[0]
    model = case.repo.get(FittedModelArtifact, cov.model_id)
    old = case.repo.get(BaselineModelSpec, model.spec_id)
    engine = ModelEngine(case.repo)
    spec = replace(old, intercept=InterceptPolicy.NONE)
    fitted = engine.model_artifact(engine.fit_model(spec, 40, 40, 40).artifact_id)
    covariance = case.engine.fit_covariance(
        ParameterUncertaintySpec(
            fitted.fingerprint, CovarianceAssumption.IID_HOMOSKEDASTIC_CORRECT_LINEAR
        ),
        40,
    )
    constant = case.fixture.upstream.upstream.upstream.upstream.spec.base_model_id
    unsupported = case.engine.fit_covariance(
        ParameterUncertaintySpec(
            constant, CovarianceAssumption.IID_HOMOSKEDASTIC_CORRECT_LINEAR
        ),
        40,
    )
    assert unsupported.status is IdentifiabilityStatus.INCOMPATIBLE
    assert not covariance.intercept_included
    assert covariance.design_rank == len(fitted.coefficients)
    from afre.research_datasets.schema import Partition

    point = engine.predict_samples(
        fitted.fingerprint,
        tuple(
            s.fingerprint
            for s in case.repo.partition_samples(old.fold_id, Partition.VALIDATION)
        ),
        PredictionScope.VALIDATION,
    )[-1]
    unc = UncertaintySpec(
        old.target,
        point.fingerprint,
        (
            UncertaintyRequest(UncertaintyType.TOTAL_PREDICTIVE),
            UncertaintyRequest(UncertaintyType.PARAMETER),
        ),
        covariance_id=covariance.fingerprint,
    )
    assert (
        component(
            case.engine.decompose(unc, point.input.origin.timestamp_ns),
            UncertaintyType.PARAMETER,
        ).value
        is not None
    )


def test_full_repository_audit(case: Case) -> None:
    assert case.repo.audit() > 100
    d = case.result("mixture")
    a = case.engine.evaluate(
        case.fixture.results("mixture"), UncertaintyEvaluationSpec(bucket_count=2), 100, 100
    )
    # Exact share drift traverses real distinct origin windows, not two methods at one origin.
    assert case.engine.audit_lineage(a.fingerprint).root_id == a.fingerprint
    assert d.fingerprint in case.engine.audit_lineage(a.fingerprint).node_ids

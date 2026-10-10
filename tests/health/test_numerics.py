"""Independent moment, KS, error, reliability and parameter fixtures."""

from dataclasses import replace
from math import erf, exp, log, pi, sqrt
from statistics import fmean, pstdev

import pytest

from afre.health import HealthDiagnostic as D
from afre.health import (
    HealthDiagnosticRequest,
    HealthDirection,
    HealthMetric,
    HealthRule,
    HealthStatistic,
    HealthStatus,
)
from afre.health.drift import distribution_pair
from afre.health.rules import classify
from afre.research_datasets.samples import ResearchSample
from afre.schema import ContractError
from afre.target_engine.models import TargetVintage
from examples.health_fixture import health_spec
from tests.health.conftest import HealthCase


@pytest.mark.parametrize(
    "kind,expected",
    [
        (D.PREDICTION_MEAN, 3.0),
        (D.PREDICTION_STD, 0.0),
        (D.PREDICTION_QUANTILE, 3.0),
        (D.PREDICTION_KS, 1.0),
        (D.SIGN_FRACTION, 0.0),
        (D.MEAN_ABSOLUTE_SHIFT, 3.0),
    ],
)
def test_known_prediction_vectors(health_case: HealthCase, kind: D, expected: float) -> None:
    c = health_case
    s, r = health_spec(c.repo, c.fixture, (kind,))
    c.engine.declare(s, r)
    out = c.engine.evaluate(s.fingerprint, 120)
    m = c.repo.resolve(HealthMetric, out.metric_ids[0])
    assert m.delta == pytest.approx(expected, abs=1e-14)
    assert m.reference_count == m.current_count == 3


def test_standardized_shift_exact() -> None:
    request = HealthDiagnosticRequest(D.STANDARDIZED_MEAN, "prediction", 2)
    a, b = distribution_pair(request, (1.0, 2.0, 3.0), (4.0, 5.0, 6.0))
    assert a == 0.0
    assert b == pytest.approx(3 / sqrt(2 / 3))
    assert distribution_pair(request, (1.0, 1.0), (3.0, 3.0)) == (0.0, None)


@pytest.mark.parametrize(
    "kind",
    [
        D.BIAS,
        D.MAE,
        D.MSE,
        D.RMSE,
        D.ERROR_VARIANCE,
        D.ERROR_QUANTILE,
        D.R_SQUARED,
        D.IC,
        D.RANK_IC,
    ],
)
def test_error_oracles(health_case: HealthCase, kind: D) -> None:
    c = health_case
    s, r = health_spec(c.repo, c.fixture, (kind,))
    c.engine.declare(s, r)
    out = c.engine.evaluate(s.fingerprint, 120)
    m = c.repo.resolve(HealthMetric, out.metric_ids[0])

    def oracle(at: int) -> float:
        records = []
        for i in (*c.fixture.upstream.train, *c.fixture.upstream.validation):
            sample = c.repo.get(ResearchSample, i)
            if sample.timestamp_ns != at:
                continue
            assert sample.target_id is not None
            y = c.repo.get(TargetVintage, sample.target_id).value
            assert y is not None
            p = float(int(sample.security.value) + (3 if at >= 40 else 0))
            records.append((p, y))
        predictions, truths = tuple(a for a, _ in records), tuple(b for _, b in records)
        e = tuple(a - b for a, b in records)
        if kind in (D.BIAS, D.MAE):
            return fmean(e)
        if kind is D.MSE:
            return fmean(x * x for x in e)
        if kind is D.RMSE:
            return sqrt(fmean(x * x for x in e))
        if kind is D.ERROR_VARIANCE:
            return pstdev(e) ** 2
        if kind is D.ERROR_QUANTILE:
            return sorted(e)[1]
        if kind is D.R_SQUARED:
            return 1 - sum(v * v for v in e) / sum((v - fmean(truths)) ** 2 for v in truths)
        if kind is D.RANK_IC:
            return -1.0
        a, b = fmean(predictions), fmean(truths)
        return sum((x - a) * (v - b) for x, v in records) / sqrt(
            sum((x - a) ** 2 for x in predictions) * sum((v - b) ** 2 for v in truths)
        )

    assert m.reference_value == pytest.approx(oracle(10), rel=1e-12)
    assert m.current_value == pytest.approx(oracle(40), rel=1e-12)
    assert m.delta == pytest.approx(oracle(40) - oracle(10), rel=1e-12)
    assert len(m.truth_ids) == 6


@pytest.mark.parametrize(
    "kind", [D.PREDICTIVE_VARIANCE, D.THRESHOLD_PROBABILITY, D.NLL, D.CRPS, D.ECE, D.MCE]
)
def test_gaussian_probability_oracles(health_case: HealthCase, kind: D) -> None:
    c = health_case
    s, r = health_spec(c.repo, c.fixture, (kind,), probability=True)
    c.engine.declare(s, r)
    out = c.engine.evaluate(s.fingerprint, 120)
    m = c.repo.resolve(HealthMetric, out.metric_ids[0])

    def oracle(at: int) -> float:
        scores = []
        for i in (*c.fixture.upstream.train, *c.fixture.upstream.validation):
            sample = c.repo.get(ResearchSample, i)
            if sample.timestamp_ns != at:
                continue
            assert sample.target_id is not None
            y = c.repo.get(TargetVintage, sample.target_id).value
            assert y is not None
            mu = float(int(sample.security.value) + (3 if at >= 40 else 0))
            sigma = 2.0 if at >= 40 else 1.0
            probability = (1 + erf(mu / (sigma * sqrt(2)))) / 2
            if kind is D.PREDICTIVE_VARIANCE:
                value = sigma * sigma
            elif kind is D.THRESHOLD_PROBABILITY:
                value = probability
            elif kind in (D.ECE, D.MCE):
                value = 1 - probability
            elif kind is D.NLL:
                value = 0.5 * log(2 * pi) + log(sigma) + (y - mu) ** 2 / (2 * sigma * sigma)
            else:
                z = (y - mu) / sigma
                phi = exp(-z * z / 2) / sqrt(2 * pi)
                Phi = (1 + erf(z / sqrt(2))) / 2
                value = sigma * (z * (2 * Phi - 1) + 2 * phi - 1 / sqrt(pi))
            scores.append(value)
        return fmean(scores)

    assert m.reference_value == pytest.approx(oracle(10), abs=1e-12)
    assert m.current_value == pytest.approx(oracle(40), abs=1e-12)


@pytest.mark.parametrize(
    "value,status",
    [
        (-1.0, HealthStatus.HEALTHY),
        (0.49, HealthStatus.HEALTHY),
        (0.5, HealthStatus.WARNING),
        (1.99, HealthStatus.WARNING),
        (2.0, HealthStatus.DEGRADED),
    ],
)
@pytest.mark.parametrize(
    "direction",
    [
        HealthDirection.HIGHER_WORSE,
        HealthDirection.LOWER_WORSE,
        HealthDirection.ABSOLUTE_CHANGE_WORSE,
    ],
)
def test_exact_rule_boundaries(
    value: float, status: HealthStatus, direction: HealthDirection
) -> None:
    if direction is HealthDirection.ABSOLUTE_CHANGE_WORSE and value < 0:
        status = HealthStatus.WARNING
    rule = HealthRule(
        "explicit",
        D.PREDICTION_MEAN,
        direction,
        HealthStatistic.DELTA,
        2,
        -0.5 if direction is HealthDirection.LOWER_WORSE else 0.5,
        -2.0 if direction is HealthDirection.LOWER_WORSE else 2.0,
        0,
    )
    assert (
        classify(rule, -value if direction is HealthDirection.LOWER_WORSE else value) is status
    )


def test_two_sided_inclusive_ranges() -> None:
    rule = HealthRule(
        "range",
        D.PREDICTION_MEAN,
        HealthDirection.TWO_SIDED_RANGE,
        HealthStatistic.CURRENT,
        2,
        -1.0,
        -2.0,
        0,
        1.0,
        2.0,
    )
    for v, s in [
        (1.0, HealthStatus.HEALTHY),
        (2.0, HealthStatus.WARNING),
        (2.001, HealthStatus.DEGRADED),
        (-1.5, HealthStatus.WARNING),
    ]:
        assert classify(rule, v) is s
    with pytest.raises(ContractError):
        replace(rule, degraded_upper=0.0)

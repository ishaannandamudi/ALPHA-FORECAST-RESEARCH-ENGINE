"""Exact point metrics, constant states, ties and per-origin evaluation checks."""

import math

import pytest

from afre.schema import ContractError
from afre.statistical_models import MetricName, MetricState
from afre.statistical_models.metrics import correlation, point_metrics, ranks


def test_known_point_metrics() -> None:
    values = {m.name: m.value for m in point_metrics((2.0, 2.0, 4.0), (1.0, 2.0, 3.0))}
    assert values[MetricName.COUNT] == 3.0
    assert values[MetricName.MEAN_ERROR] == pytest.approx(2 / 3)
    assert values[MetricName.MAE] == pytest.approx(2 / 3)
    assert values[MetricName.MSE] == pytest.approx(2 / 3)
    assert values[MetricName.RMSE] == pytest.approx(math.sqrt(2 / 3))
    assert values[MetricName.R_SQUARED] == 0.0
    assert values[MetricName.PEARSON_CORRELATION] == pytest.approx(math.sqrt(3) / 2)


@pytest.mark.parametrize(
    "p,y,state",
    (
        ((), (), MetricState.INSUFFICIENT_OBSERVATIONS),
        ((1.0,), (2.0,), MetricState.INSUFFICIENT_OBSERVATIONS),
        ((1.0, 2.0), (3.0, 3.0), MetricState.CONSTANT_TARGET),
        ((1.0, 1.0), (2.0, 3.0), MetricState.CONSTANT_PREDICTION),
    ),
)
def test_correlation_states(
    p: tuple[float, ...], y: tuple[float, ...], state: MetricState
) -> None:
    result = correlation(p, y)
    assert result.value is None and result.state is state


def test_tied_rank_ic_and_sign_zeros() -> None:
    assert ranks((2.0, 1.0, 2.0, 4.0)) == (2.5, 1.0, 2.5, 4.0)
    assert correlation(
        (2.0, 1.0, 2.0), (4.0, 3.0, 4.0), MetricName.SPEARMAN_CORRELATION
    ).value == pytest.approx(1.0)
    metrics = {m.name: m for m in point_metrics((0.0, 1.0, -1.0), (0.0, -1.0, -2.0))}
    assert metrics[MetricName.DIRECTIONAL_ACCURACY].value == pytest.approx(2 / 3)
    assert all(m.sample_count == 0 for m in point_metrics((), ()))
    assert (
        next(
            m for m in point_metrics((1.0, 2.0), (1.0, 1.0)) if m.name is MetricName.R_SQUARED
        ).state
        is MetricState.CONSTANT_TARGET
    )


def test_metric_shape_and_overflow() -> None:
    with pytest.raises(ContractError):
        point_metrics((1.0,), ())
    with pytest.raises(ContractError):
        correlation((1.0,), ())
    with pytest.raises(ContractError):
        point_metrics((math.inf,), (0.0,))
    with pytest.raises(ContractError, match="overflow"):
        point_metrics((1e308,), (-1e308,))


def test_nonbinary_constant_float_is_unavailable() -> None:
    assert correlation((0.1,) * 3, (1.0, 2.0, 3.0)).state is MetricState.CONSTANT_PREDICTION
    assert correlation((1.0, 2.0, 3.0), (0.1,) * 3).state is MetricState.CONSTANT_TARGET
    assert (
        next(
            m
            for m in point_metrics((1.0, 2.0, 3.0), (0.1,) * 3)
            if m.name is MetricName.R_SQUARED
        ).state
        is MetricState.CONSTANT_TARGET
    )

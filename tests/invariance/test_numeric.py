"""Independent numerical oracles, tied/degenerate inputs and explicit boundaries."""

import math
from statistics import mean

import pytest

from afre.hashing import bytes_digest
from afre.invariance import StabilityMetricName, StabilityTimeWindow
from afre.invariance.coefficients import parameter_summary
from afre.invariance.distributions import empirical_ks, summary_for
from afre.invariance.scoring import point_score
from afre.invariance.temporal import rolling_windows
from afre.lineage import ProvenanceRef
from afre.schema import ContractError


@pytest.mark.parametrize(
    "a,b",
    [
        ((0.0, 0.0, 1.0), (0.0, 1.0, 1.0)),
        ((0.0, 1.0), (2.0, 3.0)),
        ((2.0,), (2.0,)),
        ((-3.0, 0.0, 4.0), (-2.0, 0.0, 2.0, 8.0)),
    ],
)
def test_ks_empirical_cdf_oracle(a: tuple[float, ...], b: tuple[float, ...]) -> None:
    expected = max(
        abs(sum(v <= x for v in a) / len(a) - sum(v <= x for v in b) / len(b))
        for x in set(a + b)
    )
    assert empirical_ks(a, b) == expected
    assert empirical_ks(b, a) == expected


@pytest.mark.parametrize(
    "name",
    [
        StabilityMetricName.MAE,
        StabilityMetricName.MSE,
        StabilityMetricName.RMSE,
        StabilityMetricName.R_SQUARED,
        StabilityMetricName.SIGN_ACCURACY,
    ],
)
def test_explicit_weighted_scores(name: StabilityMetricName) -> None:
    p, y, w = (-2.0, 3.0, 1.0), (-1.0, 1.0, 2.0), (0.2, 0.5, 0.3)
    errors = tuple(a - b for a, b in zip(p, y, strict=True))
    mse = sum(a * e * e for a, e in zip(w, errors, strict=True))
    center = sum(a * b for a, b in zip(w, y, strict=True))
    variance = sum(a * (b - center) ** 2 for a, b in zip(w, y, strict=True))
    expected = {
        StabilityMetricName.MAE: sum(a * abs(e) for a, e in zip(w, errors, strict=True)),
        StabilityMetricName.MSE: mse,
        StabilityMetricName.RMSE: math.sqrt(mse),
        StabilityMetricName.R_SQUARED: 1 - mse / variance,
        StabilityMetricName.SIGN_ACCURACY: 1.0,
    }[name]
    assert point_score(name, p, y, w)[0] == pytest.approx(expected, abs=1e-14)


def test_sign_range_zero_and_type7() -> None:
    s = parameter_summary("known coefficient", (-2.0, 0.0, 3.0, 3.0))
    assert (s.minimum, s.maximum, s.mean, s.median) == (-2.0, 3.0, 1.0, 1.5)
    assert (s.negative_fraction, s.zero_fraction, s.positive_fraction, s.sign_consistency) == (
        0.25,
        0.25,
        0.5,
        0.5,
    )
    ids = tuple(
        ProvenanceRef("fixture", str(i), "1", bytes_digest(str(i).encode())).fingerprint
        for i in range(5)
    )
    d = summary_for(
        tuple(zip(ids, (0.0, 2.0, 4.0, 6.0, None), strict=True)), (0.0, 0.25, 0.5, 0.75, 1.0)
    )
    assert d.mean == mean((0.0, 2.0, 4.0, 6.0)) and d.std == pytest.approx(math.sqrt(5))
    assert (
        tuple(v for _, v in d.quantiles) == (0.0, 1.5, 3.0, 4.5, 6.0)
        and d.missing_fraction == 0.2
    )


@pytest.mark.parametrize(
    "left,right", [(False, False), (False, True), (True, False), (True, True)]
)
def test_window_exact_inclusivity(left: bool, right: bool) -> None:
    w = StabilityTimeWindow(10, 20, left, right)
    assert w.contains(10) is left and w.contains(20) is right
    assert w.contains(15) and not w.contains(9) and not w.contains(21)


def test_rolling_predeclared_bounds() -> None:
    assert tuple((w.start_ns, w.end_ns) for w in rolling_windows(0, 10, 4, 2)) == (
        (0, 4),
        (2, 6),
        (4, 8),
        (6, 10),
    )
    for args in ((0, 10, 1, 1, 2, 2), (0, 10, 0, 1), (0, 2, 4, 1)):
        with pytest.raises(ContractError):
            rolling_windows(*args)
    with pytest.raises(ContractError):
        empirical_ks((), (1.0,))


@pytest.mark.parametrize("name", [StabilityMetricName.PEARSON, StabilityMetricName.SPEARMAN])
def test_weighted_rank_semantics_not_silently_invented(name: StabilityMetricName) -> None:
    assert point_score(name, (1.0, 2.0), (2.0, 3.0), (0.2, 0.8)) == (
        None,
        "weighted-correlation-not-supported",
    )

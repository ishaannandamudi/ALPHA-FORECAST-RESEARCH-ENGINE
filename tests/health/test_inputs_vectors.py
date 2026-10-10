"""Independent scalar/vector oracles and admission exclusions retain missing evidence."""

from dataclasses import replace
from math import sqrt
from statistics import fmean, pstdev

import pytest

from afre.health import HealthDiagnostic as D
from afre.health import HealthDiagnosticRequest, HealthMetric, HealthObservation, HealthStatus
from afre.health.vectors import vector_pair
from examples.health_fixture import health_spec
from tests.health.conftest import HealthCase


@pytest.mark.parametrize(
    "kind",
    (
        D.INPUT_MEAN,
        D.INPUT_STD,
        D.INPUT_QUANTILE,
        D.INPUT_KS,
        D.STANDARDIZED_MEAN,
        D.MISSINGNESS,
    ),
)
def test_actual_input_drift_oracle(
    health_case: HealthCase, kind: D, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = health_case
    from typing import TypeVar

    from afre.schema import Artifact
    from afre.target_engine.models import TargetVintage

    A = TypeVar("A", bound=Artifact)
    get = c.repo.get

    def target_free(cls: type[A], identity: str) -> A:
        assert cls is not TargetVintage
        return get(cls, identity)

    monkeypatch.setattr(c.repo, "get", target_free)
    column = c.repo.get(HealthObservation, c.fixture.input_ids[0]).values[0][0]
    s, rules = health_spec(c.repo, c.fixture, (kind,), input_column=column)
    c.engine.declare(s, rules)
    out = c.engine.evaluate(s.fingerprint, 120)
    m = c.repo.resolve(HealthMetric, out.metric_ids[0])
    pools = tuple(
        tuple(dict(c.repo.get(HealthObservation, i).values)[column] for i in ids)
        for ids in (s.reference_observation_ids, s.current_observation_ids)
    )
    a, b = tuple(tuple(float(v) for v in values if v is not None) for values in pools)
    if kind is D.INPUT_MEAN:
        expected = fmean(b) - fmean(a)
    elif kind is D.INPUT_STD:
        expected = pstdev(b) - pstdev(a)
    elif kind is D.INPUT_QUANTILE:
        expected = (sorted(b)[(len(b) - 1) // 2] + sorted(b)[len(b) // 2]) / 2 - (
            sorted(a)[(len(a) - 1) // 2] + sorted(a)[len(a) // 2]
        ) / 2
    elif kind is D.INPUT_KS:
        expected = max(
            abs(sum(x <= v for x in a) / len(a) - sum(x <= v for x in b) / len(b))
            for v in set(a + b)
        )
    elif kind is D.STANDARDIZED_MEAN:
        expected = (fmean(b) - fmean(a)) / sqrt((pstdev(a) ** 2 + pstdev(b) ** 2) / 2)
    else:
        expected = sum(v is None for v in pools[1]) / len(pools[1]) - sum(
            v is None for v in pools[0]
        ) / len(pools[0])
    assert m.delta == pytest.approx(expected, abs=1e-12)
    assert not m.truth_ids


def test_missing_column_is_not_zero_imputed(health_case: HealthCase) -> None:
    c = health_case
    s, rules = health_spec(
        c.repo, c.fixture, (D.MISSINGNESS,), input_column="explicit-absent-feature"
    )
    c.engine.declare(s, rules)
    m = c.repo.resolve(HealthMetric, c.engine.evaluate(s.fingerprint, 120).metric_ids[0])
    assert m.reference_value == m.current_value == 1.0
    assert m.reference_count == m.current_count == 3
    s, rules = health_spec(
        c.repo, c.fixture, (D.INPUT_MEAN,), input_column="explicit-absent-feature"
    )
    c.engine.declare(s, rules)
    m = c.repo.resolve(HealthMetric, c.engine.evaluate(s.fingerprint, 120).metric_ids[0])
    assert m.status is HealthStatus.INSUFFICIENT_DATA
    assert m.reference_value is None and len(m.exclusions) == 6


@pytest.mark.parametrize(
    "kind",
    (
        D.PARAMETER_L1,
        D.PARAMETER_L2,
        D.RELATIVE_PARAMETER,
        D.PARAMETER_SIGN_CHANGES,
        D.PARAMETER_CORRELATION,
        D.RANK_DISPLACEMENT,
        D.TOP_K_OVERLAP,
        D.SIGN_PERSISTENCE,
        D.TREE_SPLIT_RECURRENCE,
        D.TREE_PATH_RECURRENCE,
        D.TREE_THRESHOLD,
        D.TREE_LEAF_SUPPORT,
    ),
)
def test_vector_oracles(health_case: HealthCase, kind: D) -> None:
    c = health_case
    base = c.repo.get(HealthObservation, c.fixture.observation_ids[0])
    prefix = (
        "rank"
        if kind in (D.RANK_DISPLACEMENT, D.TOP_K_OVERLAP)
        else "score"
        if kind is D.SIGN_PERSISTENCE
        else "split"
        if kind is D.TREE_SPLIT_RECURRENCE
        else "path"
        if kind is D.TREE_PATH_RECURRENCE
        else "threshold"
        if kind is D.TREE_THRESHOLD
        else "leaf_support"
        if kind is D.TREE_LEAF_SUPPORT
        else "parameter"
    )
    a = (1.0, 2.0, -3.0) if prefix in ("parameter", "score") else (1.0, 2.0, 3.0)
    b = (-1.0, 4.0, -3.0) if prefix in ("parameter", "score") else (3.0, 2.0, 1.0)
    left = replace(base, values=tuple((prefix + ":" + str(i), v) for i, v in enumerate(a)))
    right = replace(base, values=tuple((prefix + ":" + str(i), v) for i, v in enumerate(b)))
    request = HealthDiagnosticRequest(kind, "parameter", 1)
    reference, current, _ = vector_pair(request, (left,), (right,))
    expected = {
        D.PARAMETER_L1: 4 / 6,
        D.PARAMETER_L2: sqrt(8 / 14),
        D.RELATIVE_PARAMETER: 2.0,
        D.PARAMETER_SIGN_CHANGES: 1.0,
        D.RANK_DISPLACEMENT: 4 / 3,
        D.TOP_K_OVERLAP: 0.0,
        D.SIGN_PERSISTENCE: 2 / 3,
        D.TREE_SPLIT_RECURRENCE: 1.0,
        D.TREE_PATH_RECURRENCE: 1.0,
        D.TREE_THRESHOLD: 2.0,
        D.TREE_LEAF_SUPPORT: 2.0,
    }
    if kind is D.PARAMETER_CORRELATION:
        ma, mb = fmean(a), fmean(b)
        value = sum((x - ma) * (y - mb) for x, y in zip(a, b, strict=True)) / sqrt(
            sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)
        )
    else:
        value = expected[kind]
    assert reference is not None and current == pytest.approx(value, abs=1e-14)


def test_different_unit_incomparable(health_case: HealthCase) -> None:
    c = health_case
    s, r = health_spec(c.repo, c.fixture, (D.PREDICTION_MEAN,))
    # A point versus a probabilistic frozen producer has different exact semantics.
    wrong = replace(
        s,
        comparison_reference_ids=(c.fixture.probability_reference.fingerprint,),
        current_observation_ids=c.fixture.probability_ids,
    )
    c.engine.declare(wrong, r)
    assert c.engine.evaluate(wrong.fingerprint, 120).status is HealthStatus.INCOMPARABLE


def test_input_grid_cannot_be_forecast_truth(health_case: HealthCase) -> None:
    from afre.schema import ContractError

    c = health_case
    column = c.repo.get(HealthObservation, c.fixture.input_ids[0]).values[0][0]
    s, r = health_spec(c.repo, c.fixture, (D.MAE,), input_column=column)
    c.engine.declare(s, r)
    with pytest.raises(ContractError, match="input grids|exact native prediction"):
        c.engine.evaluate(s.fingerprint, 120)

"""Independent correlation, OLS, residual, variance, VIF and incremental metric oracles."""

import math
from dataclasses import replace

import pytest

from afre.orthogonalization import ProjectionIntercept, ProjectionPreprocessing
from afre.orthogonalization.projection import numeric, population_variance, solve, vif_for
from afre.research_datasets.schema import Partition
from afre.schema import ContractError
from afre.statistical_models.metrics import correlation
from afre.statistical_models.schema import MetricName
from afre.target_engine.models import TargetVintage
from examples.orthogonalization_oracles import (
    metrics,
    ols,
    pearson,
    predict,
    spearman,
    variance,
)
from tests.orthogonalization.conftest import Case


@pytest.mark.parametrize(
    "x,y",
    [
        ((1.0, 2.0, 3.0, 4.0), (4.0, 1.0, 5.0, 2.0)),
        ((1.0, 1.0, 3.0, 4.0), (2.0, 3.0, 2.0, 4.0)),
        ((-2.0, 0.0, 7.0, 9.0), (1.0, -3.0, 2.0, 5.0)),
    ],
)
def test_correlations(x: tuple[float, ...], y: tuple[float, ...]) -> None:
    assert correlation(x, y).value == pytest.approx(pearson(x, y), abs=1e-14)
    assert correlation(x, y, MetricName.SPEARMAN_CORRELATION).value == pytest.approx(
        spearman(x, y), abs=1e-14
    )


@pytest.mark.parametrize(
    "x,y", [((), ()), ((1.0,), (2.0,)), ((1.0, 1.0), (1.0, 2.0)), ((1.0, 2.0), (3.0, 3.0))]
)
def test_undefined_correlation(x: tuple[float, ...], y: tuple[float, ...]) -> None:
    assert correlation(x, y).value is None


@pytest.mark.parametrize("intercept", [True, False])
@pytest.mark.parametrize("dimension", [1, 2, 3])
def test_independent_qr(case: Case, intercept: bool, dimension: int) -> None:
    x = tuple(tuple((i + 1.0) ** (j + 1) / 20 for j in range(dimension)) for i in range(12))
    y = tuple(2.0 + 1.5 * r[0] + math.sin(i) for i, r in enumerate(x))
    spec = replace(
        case.fixture.spec,
        intercept=ProjectionIntercept.WITH_INTERCEPT
        if intercept
        else ProjectionIntercept.NO_INTERCEPT,
    )
    a, b, rank, condition = solve(spec, x, y)
    oracle = ols(x, y, intercept)
    assert ((a, *b) if intercept else b) == pytest.approx(oracle, abs=1e-8)
    assert rank == dimension + int(intercept) and condition >= 1


def test_projection_and_vif(case: Case) -> None:
    model = case.fixture.projection
    rows = case.fixture.partition(Partition.TRAIN)
    x = tuple(tuple(numeric(v) for v in r.references) for r in rows)
    y = tuple(numeric(r.candidate) for r in rows)
    oracle = ols(x, y)
    assert (model.intercept, *model.coefficients) == pytest.approx(oracle, abs=1e-12)
    p = predict(x, oracle)
    residual = tuple(a - b for a, b in zip(y, p, strict=True))
    assert model.train_residual_variance == pytest.approx(variance(residual), abs=1e-14)
    assert next(
        m.value for m in model.train_metrics if m.name is MetricName.R_SQUARED
    ) == pytest.approx(metrics(p, y)[3])
    expected = 1 / (1 - pearson(tuple(r[0] for r in x), tuple(r[1] for r in x)) ** 2)
    assert model.vif == pytest.approx((expected, expected))
    assert vif_for(tuple((float(i),) for i in range(8)), case.fixture.spec) == (1.0,)
    assert vif_for(((1.0,), (1.0,), (1.0,)), case.fixture.spec) == (None,)


@pytest.mark.parametrize("preprocess", list(ProjectionPreprocessing))
@pytest.mark.parametrize("intercept", list(ProjectionIntercept))
def test_persisted_policies(
    case: Case, preprocess: ProjectionPreprocessing, intercept: ProjectionIntercept
) -> None:
    spec = replace(case.fixture.spec, preprocessing=preprocess, intercept=intercept)
    rows = tuple(case.engine.align(spec, r.observation_ids) for r in case.fixture.rows)
    train = tuple(r.fingerprint for r in rows if r.partition is Partition.TRAIN)
    model = case.engine.fit(spec, train, 40)
    x = tuple(
        tuple(
            (numeric(v) - c) / s
            for v, c, s in zip(r.references, model.centers, model.scales, strict=True)
        )
        for r in rows
        if r.partition is Partition.TRAIN
    )
    y = tuple(numeric(r.candidate) for r in rows if r.partition is Partition.TRAIN)
    oracle = ols(x, y, intercept is ProjectionIntercept.WITH_INTERCEPT)
    assert (
        (model.intercept, *model.coefficients)
        if intercept is ProjectionIntercept.WITH_INTERCEPT
        else model.coefficients
    ) == pytest.approx(oracle, abs=1e-12)
    assert (model.centers == (0.0,) * len(spec.references)) == (
        preprocess is ProjectionPreprocessing.NONE
    )
    sample = next(r for r in rows if r.partition is Partition.VALIDATION)
    v = case.engine.residual(model.fingerprint, sample.fingerprint, sample.origin.timestamp_ns)
    assert v.unit == spec.candidate.unit and v.residual == numeric(v.raw_candidate) - numeric(
        v.projected
    )


def test_perfect_and_no_intercept(case: Case) -> None:
    from examples.orthogonalization_fixture import build_rows

    spec, rows = build_rows(
        case.repo,
        case.fixture.spec.fold_id,
        case.fixture.spec.target,
        40,
        tag="perfect",
        perfect=True,
    )
    train = tuple(r.fingerprint for r in rows if r.partition is Partition.TRAIN)
    p = case.engine.fit(spec, train, 40)
    assert (p.intercept, *p.coefficients) == pytest.approx((1.0, 2.0), abs=1e-12)
    vals = tuple(
        case.engine.residual(p.fingerprint, r.fingerprint, r.origin.timestamp_ns)
        for r in rows
        if r.partition is Partition.VALIDATION
    )
    assert max(abs(numeric(v.residual)) for v in vals) < 1e-12
    no = replace(spec, intercept=ProjectionIntercept.NO_INTERCEPT)
    trainrows = tuple(
        case.engine.align(no, r.observation_ids) for r in rows if r.partition is Partition.TRAIN
    )
    p2 = case.engine.fit(no, tuple(r.fingerprint for r in trainrows), 40)
    x = tuple(numeric(r.references[0]) for r in trainrows)
    y = tuple(numeric(r.candidate) for r in trainrows)
    assert p2.intercept == 0 and p2.coefficients[0] == pytest.approx(
        sum(a * b for a, b in zip(x, y, strict=True)) / sum(a * a for a in x)
    )


def test_heldout_and_incremental_oracles(case: Case) -> None:
    e = case.engine
    pair = e.fit_target_models(case.fixture.projection.fingerprint, 40)
    v = e.evaluate(
        case.fixture.residual_ids(Partition.VALIDATION), 100, 100, pair.fingerprint, True
    )
    rows = {r.sample_id: r for r in case.fixture.rows}
    rr = {r.sample_id: r for r in case.fixture.residuals}
    raw = tuple(numeric(rr[k].raw_candidate) for k in v.sample_ids)
    residual = tuple(numeric(rr[k].residual) for k in v.sample_ids)
    predicted = tuple(numeric(rr[k].projected) for k in v.sample_ids)
    assert v.candidate_variance == pytest.approx(variance(raw))
    assert v.residual_variance_ratio == pytest.approx(variance(residual) / variance(raw))
    assert next(
        m.value for m in v.projection_metrics if m.name is MetricName.R_SQUARED
    ) == pytest.approx(metrics(predicted, raw)[3])
    assert v.raw_target_correlations[0].value == pytest.approx(pearson(raw, v.truths))
    assert v.residual_target_correlations[1].value == pytest.approx(
        spearman(residual, v.truths)
    )
    train = case.fixture.partition(Partition.TRAIN)
    xtrain = tuple(tuple(numeric(a) for a in r.references) for r in train)
    trainres = tuple(
        numeric(r.candidate)
        - case.fixture.projection.intercept
        - sum(a * b for a, b in zip(x, case.fixture.projection.coefficients, strict=True))
        for r, x in zip(train, xtrain, strict=True)
    )
    base = ols(xtrain, pair.truths)
    aug = ols(tuple((*x, u) for x, u in zip(xtrain, trainres, strict=True)), pair.truths)
    xval = tuple(tuple(numeric(a) for a in rows[k].references) for k in v.sample_ids)
    bp = predict(xval, base)
    ap = predict(tuple((*x, u) for x, u in zip(xval, residual, strict=True)), aug)
    expected = tuple(
        a - b for a, b in zip(metrics(ap, v.truths), metrics(bp, v.truths), strict=True)
    )
    assert tuple(m.value for m in v.incremental_metrics[:4]) == pytest.approx(
        expected, abs=1e-12
    )
    assert v.partial_target_correlations[0].value == pytest.approx(
        pearson(residual, tuple(a - b for a, b in zip(v.truths, bp, strict=True)))
    )
    assert pair.truths == tuple(case.repo.get(TargetVintage, t).value for t in pair.target_ids)


@pytest.mark.parametrize("limit", [1.0, 2.0, 5.0])
def test_condition_policy(case: Case, limit: float) -> None:
    x = tuple((float(i), float(i) + 1e-7 * math.sin(i)) for i in range(12))
    with pytest.raises(ContractError, match="condition|rank"):
        solve(
            replace(case.fixture.spec, condition_limit=limit),
            x,
            tuple(float(i) for i in range(12)),
        )


@pytest.mark.parametrize(
    "x",
    [((0.0,), (0.0,), (0.0,)), ((1.0, 1.0), (2.0, 2.0), (3.0, 3.0)), ((1.0,), (1.0,), (1.0,))],
)
def test_rank_failure(case: Case, x: tuple[tuple[float, ...], ...]) -> None:
    with pytest.raises(ContractError, match="rank"):
        solve(case.fixture.spec, x, (1.0, 2.0, 3.0))


def test_missing_and_variance_helpers() -> None:
    assert population_variance(()) is None
    assert population_variance((2.0, 2.0)) == 0
    with pytest.raises(ContractError):
        numeric(None)


@pytest.mark.parametrize(
    "x",
    [
        ((1.0, 2.0, 2.0), (2.0, 4.0, 4.0), (3.0, 6.0, 6.0), (4.0, 8.0, 8.0)),
        ((1.0, 1.0), (1.0, 2.0), (1.0, 3.0), (1.0, 4.0)),
    ],
)
def test_vif_unsupported_auxiliary(case: Case, x: tuple[tuple[float, ...], ...]) -> None:
    values = vif_for(x, case.fixture.spec)
    assert any(v is None for v in values)

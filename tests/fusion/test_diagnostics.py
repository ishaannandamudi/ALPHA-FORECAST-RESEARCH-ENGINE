"""Independent common-intersection diagnostics and AFRE19 accounting."""

from dataclasses import replace
from math import fsum, log, sqrt

import pytest

from afre.fusion import (
    FusedForecast,
    FusionEngine,
    FusionObservation,
    FusionRepository,
    FusionWeights,
)
from afre.fusion.contributions import stability_for, weight_diagnostics
from afre.multiple_testing.engine import MultipleTestingEngine
from afre.multiple_testing.schema import TrialState
from afre.multiple_testing.trials import TrialSpecification
from afre.schema import ContractError
from afre.statistical_models.schema import MetricName
from examples.fusion_fixture import FusionFixture, apply_partition

Case = tuple[FusionRepository, FusionFixture]


def pearson(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    am, bm = fsum(a) / len(a), fsum(b) / len(b)
    return fsum((x - am) * (y - bm) for x, y in zip(a, b, strict=True)) / sqrt(
        fsum((x - am) ** 2 for x in a) * fsum((y - bm) ** 2 for y in b)
    )


def test_diversity_oracle_and_common_intersection(fusion_case: Case) -> None:
    repo, f = fusion_case
    e = FusionEngine(repo)
    ids = tuple(i for s in f.validation for i in f.observations(s))
    matrix = e.diversity(f.spec.source_ids, ids, 100)
    columns = {
        i: tuple(
            repo.get(FusionObservation, j).value
            for s in matrix.sample_ids
            for j in f.observations(s)
            if repo.get(FusionObservation, j).source_id == i
        )
        for i in f.spec.source_ids
    }
    a = tuple(v for v in columns[f.spec.source_ids[0]] if v is not None)
    b = tuple(v for v in columns[f.spec.source_ids[1]] if v is not None)
    pair = next(p for p in matrix.pairs if p.left_id != p.right_id)
    assert pair.pearson.value is not None and abs(pair.pearson.value - pearson(a, b)) < 1e-14
    assert (
        pair.mean_absolute_disagreement
        == fsum(abs(x - y) for x, y in zip(a, b, strict=True)) / 3
    )

    def ranks(v: tuple[float, ...]) -> tuple[float, ...]:
        return tuple(float(sorted(v).index(x) + 1) for x in v)

    assert (
        pair.spearman.value is not None
        and abs(pair.spearman.value - pearson(ranks(a), ranks(b))) < 1e-14
    )
    assert (
        pair.sign_agreement
        == sum((x > 0) - (x < 0) == (y > 0) - (y < 0) for x, y in zip(a, b, strict=True)) / 3
    )
    assert pair.error_correlation is None
    partial = e.diversity(f.spec.source_ids, ids[1:], 100)
    missing = repo.get(FusionObservation, ids[0]).sample_id
    assert partial.sample_ids == tuple(s for s in matrix.sample_ids if s != missing)
    errors = e.diversity(f.spec.source_ids, ids, 100, 100)
    assert all(p.error_correlation is not None for p in errors.pairs)
    with pytest.raises(ContractError, match="exact source/sample grid"):
        e.diversity(f.spec.source_ids, ids + (ids[0],), 100)


def test_comparison_and_all_trials(fusion_case: Case) -> None:
    repo, f = fusion_case
    e = FusionEngine(repo)
    a = e.fit(f.spec, 0, 0, 0)
    spec2 = replace(
        f.spec,
        name="second-rule",
        weights=tuple((i, 0.75 if j == 0 else 0.25) for j, (i, _) in enumerate(f.spec.weights)),
    )
    b = e.fit(spec2, 0, 0, 0)
    ids = apply_partition(repo, f, a.fingerprint, f.validation)
    other = apply_partition(repo, f, b.fingerprint, f.validation)
    pool = e.trial_pool(((f.spec.fingerprint, ids), (spec2.fingerprint, other)))
    assert len(pool.plan_ids) == 2 and len(pool.spec_ids) == 2
    trials = tuple(
        MultipleTestingEngine(repo).complete(i, pool.family_id, 100, 100) for i in pool.plan_ids
    )
    assert all(t.state is TrialState.COMPLETED for t in trials)
    assert all(repo.get(TrialSpecification, i).native_phase == 21 for i in pool.plan_ids)
    result = e.evaluate(ids, pool.fingerprint, 100, 100)
    mse = fsum((p.fused - p.truth) ** 2 for p in result.pairs) / len(result.pairs)
    assert next(m.value for m in result.fused_metrics if m.name is MetricName.MSE) == mse
    for source, metrics in result.component_metrics:
        expected = fsum(
            (dict(p.component_values)[source] - p.truth) ** 2 for p in result.pairs
        ) / len(result.pairs)
        assert next(m.value for m in metrics if m.name is MetricName.MSE) == expected
        assert (
            next(v for i, n, v in result.deltas if i == source and n == "mse") == mse - expected
        )
    assert result.sign_convention.startswith("fused-minus-component")
    assert len(result.origin_ic) == 3
    with pytest.raises(ContractError, match="one frozen artifact"):
        e.evaluate((ids[0], other[0]), pool.fingerprint, 100, 100)
    with pytest.raises(ContractError, match="finite fusion trial pool"):
        e.trial_pool(((f.spec.fingerprint, ids), (f.spec.fingerprint, ids)))


def test_missing_intersection_and_test_boundary(fusion_case: Case) -> None:
    repo, f = fusion_case
    e = FusionEngine(repo)
    a = e.fit(f.spec, 0, 0, 0)
    ids = apply_partition(repo, f, a.fingerprint, f.validation)
    pool = e.trial_pool(((f.spec.fingerprint, ids),))
    missing = e.apply(a.fingerprint, f.validation[0], f.observations(f.validation[0])[:1], 40)
    result = e.evaluate(
        tuple(i for i in ids if repo.get(FusedForecast, i).sample_id != missing.sample_id)
        + (missing.fingerprint,),
        pool.fingerprint,
        100,
        100,
    )
    assert len(result.pairs) == 2 and len(result.exclusions) == 1
    tests = apply_partition(repo, f, a.fingerprint, f.test)
    with pytest.raises(ContractError, match="TEST frozen choice"):
        e.evaluate(tests, pool.fingerprint, 100, 100)
    choice = e.choose_test(a.fingerprint, 0, "single predeclared final artifact")
    result = e.evaluate(
        tests, pool.fingerprint, 100, 100, choice.fingerprint, "fusion-test-final"
    )
    assert len(result.pairs) == 6 and result.test_evaluation_id is not None
    with pytest.raises(ContractError, match="before held-out"):
        e.choose_test(a.fingerprint, 70, "late selection")


def test_weight_descriptions_and_stability(fusion_case: Case) -> None:
    repo, f = fusion_case
    e = FusionEngine(repo)
    a = e.fit(f.spec, 0, 0, 0)
    b = e.fit(
        replace(
            f.spec,
            name="window-two",
            weights=tuple(
                (i, 0.2 if j == 0 else 0.8) for j, (i, _) in enumerate(f.spec.weights)
            ),
        ),
        0,
        0,
        0,
    )
    dominant, count, entropy = weight_diagnostics(a.weights)
    assert dominant == 0.5 and count == 2.0 and entropy == log(2)
    signed = weight_diagnostics((("a", -1.0), ("b", 2.0)))
    assert signed[1:] == (None, None)
    with pytest.raises(ContractError, match="all-zero"):
        weight_diagnostics((("a", 0.0),))
    stability = stability_for(repo, (b.fingerprint, a.fingerprint))
    assert all(same for _, _, _, same in stability.ranges)
    e._publish((stability,))
    assert repo.get_any(stability.fingerprint) == stability
    c = e.fit(
        replace(
            f.spec,
            name="signed",
            weight_policy=FusionWeights.SIGNED_LINEAR,
            weights=tuple((i, -w) for i, w in f.spec.weights),
        ),
        0,
        0,
        0,
    )
    assert weight_diagnostics(c.weights)[1] is None

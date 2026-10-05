"""Each horizon retains its own availability, scoring and TEST reuse evidence."""

from dataclasses import replace

import pytest

from afre.calibration import CalibrationEngine
from afre.multihorizon import ComponentState, HorizonForecastEntry
from afre.research_datasets.splits import TestEvaluation as AccessRecord
from afre.schema import ContractError
from afre.statistical_models.schema import MetricName
from tests.multihorizon.conftest import Case


def test_per_horizon_evaluation_and_declared_aggregate(case: Case) -> None:
    ids = tuple(b.fingerprint for b in case.fixture.bundles)
    evaluated = case.engine.evaluate(ids, 75, 75)
    mses = tuple(
        next(m.value for m in h.point_metrics if m.name is MetricName.MSE)
        for h in evaluated.horizons
    )
    assert evaluated.weighted_mse == pytest.approx(
        ((mses[0] or 0.0) + 2 * (mses[1] or 0.0)) / 3
    )
    assert len(evaluated.matched_origins) == len(ids)
    assert all(h.raw_scores and h.calibrated_scores for h in evaluated.horizons)
    assert case.engine.evaluate(tuple(reversed(ids)), 75, 75) == evaluated
    late = case.engine.evaluate(ids, 65, 65)
    assert late.horizons[0].missing_count == 0
    assert late.horizons[1].missing_count == len(ids)
    assert late.matched_origins == () and late.weighted_mse is None
    missing = case.engine.build_bundle(
        case.fixture.run.fingerprint,
        case.fixture.bundles[0].origin,
        (
            case.fixture.bundles[0].entries[0],
            HorizonForecastEntry(
                case.fixture.spec.bindings[1].target_definition_id,
                ComponentState.MISSING,
                reason="declared absence",
            ),
        ),
        60,
    )
    partial = case.engine.evaluate((missing.fingerprint, ids[1]), 75, 75)
    assert len(partial.matched_origins) == 1
    assert partial.horizons[1].missing_count == 1
    assert (
        next(
            m.sample_count for m in partial.matched_point_metrics[0] if m.name is MetricName.MSE
        )
        == 1
    )
    with pytest.raises(ContractError, match="duplicates"):
        case.engine.evaluate((ids[0], ids[0]), 75, 75)
    with pytest.raises(ContractError, match="unavailable"):
        case.engine.evaluate(ids, 59, 59)
    with pytest.raises(ContractError):
        case.engine.evaluate(ids, 75, 74)


def test_horizon_test_access_and_reuse(case: Case) -> None:
    maps = [{p.input.origin.fingerprint: p for p in ps} for ps in case.fixture.tests]
    adjusted = [
        CalibrationEngine(case.repo).apply_batch(
            b.calibration_state_id or "", tuple(p.fingerprint for p in ps)
        )
        for b, ps in zip(case.fixture.spec.bindings, case.fixture.tests, strict=True)
    ]
    cmaps = [{p.input.origin.fingerprint: p for p in ps} for ps in adjusted]
    bundles = []
    for key in sorted(set(maps[0]) & set(maps[1])):
        raws = tuple(m[key] for m in maps)
        entries = tuple(
            HorizonForecastEntry(
                p.target_definition_id,
                ComponentState.AVAILABLE,
                p.point_forecast_id,
                p.fingerprint,
                m[key].fingerprint,
            )
            for p, m in zip(raws, cmaps, strict=True)
        )
        bundles.append(
            case.engine.build_bundle(
                case.fixture.run.fingerprint, raws[0].input.origin, entries, 80
            )
        )
    ids = tuple(b.fingerprint for b in bundles)
    with pytest.raises(ContractError, match="TEST requires"):
        case.engine.evaluate(ids, 95, 95)
    first = case.engine.evaluate(ids, 95, 95, ("short-final", "long-final"))
    assert all(h.test_evaluation_id is not None for h in first.horizons)
    assert first.horizons[0].test_evaluation_id != first.horizons[1].test_evaluation_id
    assert case.engine.evaluate(ids, 95, 95, ("short-final", "long-final")) == first
    second = case.engine.evaluate(ids, 95, 95, ("short-again", "long-again"))
    for old, new in zip(first.horizons, second.horizons, strict=True):
        seal = case.repo.get(AccessRecord, new.test_evaluation_id or "")
        assert old.test_evaluation_id in seal.previous_evaluation_ids
    with pytest.raises(ContractError, match="conflicting test"):
        case.engine.evaluate(ids, 100, 100, ("short-final", "long-final"))
    case.engine.lineage_audit(first.fingerprint)
    with case.repo.transaction(), pytest.raises(ContractError, match="mismatch"):
        case.repo.put(replace(first, weighted_mse=1.0))

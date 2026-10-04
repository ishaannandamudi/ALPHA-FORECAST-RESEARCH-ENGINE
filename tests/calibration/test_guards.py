"""Exact event identities, full identity scores and bounded failure paths."""

from dataclasses import replace

import pytest

from afre.calibration import (
    CalibrationBounds,
    CalibrationDriftSpec,
    CalibrationMethod,
    CalibrationRequest,
    CalibrationState,
    DriftMetric,
    ProbabilityMapping,
)
from afre.probabilistic import (
    DistributionFamily,
    ProbabilisticEngine,
    ProbabilisticForecast,
    ProbabilisticModelSpec,
    ScoreName,
    ScoreState,
    ThresholdComparison,
    ThresholdDefinition,
    ThresholdRequest,
)
from afre.research_datasets.samples import ResearchSample
from afre.schema import ContractError
from tests.calibration.conftest import CalibrationCase


def test_multiple_exact_events_gaussian_identity_proper_scores(
    calibration_case: CalibrationCase,
) -> None:
    c = calibration_case
    raw_spec = c.repo.get(ProbabilisticModelSpec, c.fixture.spec.raw_spec_id)
    events = ThresholdDefinition(
        tuple(ThresholdRequest(0.0, comparison) for comparison in ThresholdComparison)
        + (ThresholdRequest(0.01, ThresholdComparison.GT),)
    )
    raw_spec = replace(
        raw_spec, family=DistributionFamily.GAUSSIAN_LOCATION_SCALE, thresholds=events
    )
    raw_engine = ProbabilisticEngine(c.repo)
    run = raw_engine.fit_model(raw_spec, 40, 40, 40)
    cal = raw_engine.predict_batch(
        run.artifact_id, tuple(p.input for p in c.fixture.calibration_raw)
    )
    deployed = raw_engine.predict_batch(
        run.artifact_id, tuple(p.input for p in c.fixture.deployment_raw)
    )
    requests = tuple(
        CalibrationRequest(
            p.fingerprint, c.repo.get(ResearchSample, p.input.sample_id or "").target_id or ""
        )
        for p in cal
    )
    spec = replace(
        c.fixture.spec,
        raw_model_id=run.artifact_id,
        raw_spec_id=raw_spec.fingerprint,
        events=events,
    )
    identity = c.engine.fit(spec, requests, 55, 55, 55)
    fs = c.engine.apply_batch(identity.state_id, tuple(p.fingerprint for p in deployed))
    evaluation = c.engine.evaluate(tuple(f.fingerprint for f in fs), 75, 75)
    comparison = c.engine.compare(evaluation.raw_evaluation_id, evaluation.fingerprint)
    for name in (ScoreName.NLL, ScoreName.CRPS):
        delta = next(d for d in comparison.deltas if d.raw.name is name)
        assert (
            delta.raw.state is ScoreState.AVAILABLE
            and delta.calibrated.state is ScoreState.AVAILABLE
        )
        assert delta.delta == 0.0
    isotonic = c.engine.fit(
        replace(spec, method=CalibrationMethod.ISOTONIC_PROBABILITY), requests, 55, 55, 55
    )
    state = c.repo.get(CalibrationState, isotonic.state_id)
    maps = tuple(c.repo.get(ProbabilityMapping, m) for m in state.mapping_ids)
    assert len(maps) == 5 and {m.event for m in maps} == set(events.requests)
    fs = c.engine.apply_batch(isotonic.state_id, tuple(p.fingerprint for p in deployed))
    assert all(len(f.probabilities) == 5 for f in fs)
    with pytest.raises(ContractError, match="raw model"):
        c.engine.apply(identity.state_id, c.fixture.deployment_raw[0].fingerprint, 60)


def test_eligibility_wrong_raw_target_and_unknown_spec(
    calibration_case: CalibrationCase,
) -> None:
    c = calibration_case
    other = replace(
        c.fixture.spec.target, horizon=replace(c.fixture.spec.target.horizon, duration_ns=15)
    )
    with pytest.raises(ContractError, match="model/spec/target"):
        c.engine.fit(replace(c.fixture.spec, target=other), c.fixture.requests, 55, 55, 55)
    with pytest.raises(ContractError, match="count/duplicates"):
        c.engine.fit(c.fixture.spec, (), 55, 55, 55)
    with pytest.raises(ContractError, match="count/duplicates"):
        c.engine.fit(c.fixture.spec, c.fixture.requests * 2, 55, 55, 55)
    with pytest.raises(ContractError, match="clock"):
        c.engine.fit(c.fixture.spec, c.fixture.requests, 54, 55, 55)
    with pytest.raises(ContractError, match="clock"):
        c.engine.fit(c.fixture.spec, c.fixture.requests, 55, 56, 55)
    with pytest.raises(ContractError, match="raw model availability"):
        c.engine.fit(replace(c.fixture.spec, cutoff_ns=39), c.fixture.requests, 55, 55, 55)
    wrong_request = replace(c.fixture.requests[0], target_id=c.fixture.requests[1].target_id)
    with pytest.raises(ContractError, match="target/origin"):
        c.engine.fit(c.fixture.spec, (wrong_request, *c.fixture.requests[1:]), 55, 55, 55)


def test_application_evaluation_drift_batches_and_protocols(
    calibration_case: CalibrationCase,
) -> None:
    c = calibration_case
    run = c.fit()
    raw_ids = tuple(p.fingerprint for p in c.fixture.deployment_raw)
    for invalid in ((), raw_ids * 2):
        with pytest.raises(ContractError, match="count/duplicates"):
            c.engine.apply_batch(run.state_id, invalid)
    fs = c.engine.apply_batch(run.state_id, raw_ids, computed_ns=61)
    ids = tuple(f.fingerprint for f in fs)
    with pytest.raises(ContractError, match="non-TEST"):
        c.engine.evaluate(ids, 75, 75, "incorrect-test-id")
    with pytest.raises(ContractError, match="count bound"):
        c.engine.evaluate((), 75, 75)
    evaluation = c.engine.evaluate(ids, 75, 75)
    second = c.engine.evaluate(ids, 76, 76)
    with pytest.raises(ContractError, match="repeats truth"):
        c.engine.diagnose_drift(
            CalibrationDriftSpec(2, 1, DriftMetric.ECE, 0.5),
            (evaluation.fingerprint, second.fingerprint),
        )
    for invalid in ((), (evaluation.fingerprint, evaluation.fingerprint)):
        with pytest.raises(ContractError, match="history count/duplicates"):
            c.engine.diagnose_drift(CalibrationDriftSpec(1, 1, DriftMetric.ECE, 0.5), invalid)
    c.repo.calibration_bounds = replace(CalibrationBounds(), work_cells=1)
    with pytest.raises(ContractError, match="total window work"):
        c.engine.diagnose_drift(
            CalibrationDriftSpec(1, 1, DriftMetric.ECE, 0.5), (evaluation.fingerprint,)
        )


def test_exact_binned_fallback_no_full_density(calibration_case: CalibrationCase) -> None:
    c = calibration_case
    from afre.calibration import CalibrationBinDefinition

    spec = replace(
        c.fixture.spec,
        method=CalibrationMethod.BINNED_PROBABILITY,
        bins=CalibrationBinDefinition(minimum_count=100),
    )
    run = c.engine.fit(spec, c.fixture.requests, 55, 55, 55)
    fs = c.engine.apply_batch(
        run.state_id, tuple(p.fingerprint for p in c.fixture.deployment_raw)
    )
    for f in fs:
        raw = c.repo.get(ProbabilisticForecast, f.raw_forecast_id)
        assert f.probabilities == raw.threshold_probabilities
        assert not f.full_distribution_preserved
    evaluation = c.engine.evaluate(tuple(f.fingerprint for f in fs), 75, 75)
    assert (
        next(s for s in evaluation.calibrated_scores if s.name is ScoreName.CRPS).state
        is ScoreState.UNSUPPORTED
    )

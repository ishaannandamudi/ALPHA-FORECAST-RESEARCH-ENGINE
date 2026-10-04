"""Causal fit, target-free application, independent scoring and no automatic refit."""

from dataclasses import replace

import pytest

from afre.calibration import (
    CalibrationDriftSpec,
    CalibrationMethod,
    CalibrationObservationSet,
    CalibrationOverlapStatus,
    CalibrationPartitionPolicy,
    CalibrationRequest,
    CalibrationState,
    ConformalScoreSet,
    DriftMetric,
    DriftState,
    ProbabilityMapping,
    QuantileOffset,
)
from afre.calibration.application import outputs_for
from afre.calibration.partitions import overlap_status
from afre.probabilistic import (
    ProbabilisticEngine,
    ProbabilisticEvaluationProtocol,
    ProbabilisticForecast,
    ScoreName,
    ScoreState,
    ThresholdComparison,
    ThresholdRequest,
)
from afre.research_datasets.samples import ResearchSample
from afre.schema import ContractError
from afre.serialization import canonical_json
from afre.time import TimeRange
from examples.calibration_demo import corrected_calibration_truth as corrected_truth
from examples.calibration_demo import method_spec
from tests.calibration.conftest import CalibrationCase


@pytest.mark.parametrize("method", list(CalibrationMethod))
def test_fit_apply_evaluate_compare_and_audit(
    calibration_case: CalibrationCase, method: CalibrationMethod
) -> None:
    c = calibration_case
    before = tuple(canonical_json(p) for p in c.fixture.deployment_raw)
    run = c.fit(method)
    state = c.repo.get(CalibrationState, run.state_id)
    observations = c.repo.get(CalibrationObservationSet, run.inputs.observations_id)
    assert run.inputs.overlap is CalibrationOverlapStatus.DISJOINT_FROM_MODEL_TRAIN
    assert all(r.truth_available_ns == 55 and r.cutoff_ns == 55 for r in observations.rows)
    c.repo.deny_truth = True
    forecasts = c.engine.apply_batch(
        run.state_id, tuple(p.fingerprint for p in reversed(c.fixture.deployment_raw))
    )
    c.repo.deny_truth = False
    assert (
        tuple(
            canonical_json(c.repo.get(ProbabilisticForecast, p.fingerprint))
            for p in c.fixture.deployment_raw
        )
        == before
    )
    if method is CalibrationMethod.IDENTITY:
        for f in forecasts:
            raw = c.repo.get(ProbabilisticForecast, f.raw_forecast_id)
            assert (f.quantiles, f.probabilities, f.raw_interval) == (
                raw.quantiles,
                raw.threshold_probabilities,
                f.calibrated_interval,
            )
    evaluation = c.engine.evaluate(tuple(f.fingerprint for f in forecasts), 75, 75)
    assert evaluation.pairs
    assert all(p.sample_id not in run.inputs.sample_ids for p in evaluation.pairs)
    comparison = c.engine.compare(evaluation.raw_evaluation_id, evaluation.fingerprint)
    nll = next(d for d in comparison.deltas if d.raw.name is ScoreName.NLL)
    assert nll.delta is None  # Empirical raw NLL is already unsupported.
    crps = next(s for s in evaluation.calibrated_scores if s.name is ScoreName.CRPS)
    assert crps.state is (
        ScoreState.AVAILABLE if method is CalibrationMethod.IDENTITY else ScoreState.UNSUPPORTED
    )
    audit = c.engine.calibration_audit(forecasts[0].fingerprint)
    assert (
        state.inputs.observations_id in audit.evidence_ids
        and forecasts[0].raw_forecast_id in audit.evidence_ids
    )
    assert all(r.target_id in audit.evidence_ids for r in observations.rows)
    assert all(p.target_id not in audit.evidence_ids for p in evaluation.pairs)
    assert all(
        p.target_id in c.engine.calibration_audit(evaluation.fingerprint).evidence_ids
        for p in evaluation.pairs
    )
    assert c.engine.history(c.fixture.spec.raw_model_id) == (run,)
    assert c.repo.audit() > 100


def test_cutoff_exclusion_exact_time_and_rolling_no_future(
    calibration_case: CalibrationCase,
) -> None:
    c = calibration_case
    first = c.fixture.requests[0]
    late_id = corrected_truth(c.repo, first.target_id)
    requests = tuple(
        replace(r, target_id=late_id) if r == first else r for r in c.fixture.requests
    )
    spec = method_spec(c.fixture, CalibrationMethod.ROLLING_CONFORMAL)
    spec = replace(spec, partition=replace(spec.partition, rolling_count=5))
    run = c.engine.fit(spec, requests, 55, 55, 55)
    obs = c.repo.get(CalibrationObservationSet, run.inputs.observations_id)
    assert len(obs.rows) == 5 and len(obs.exclusions) == 2
    assert late_id not in {r.target_id for r in obs.rows}
    assert any(e.reason.startswith("truth-unavailable") for e in obs.exclusions)
    assert any(e.reason.startswith("outside-explicit") for e in obs.exclusions)
    assert all(r.truth_available_ns <= 55 for r in obs.rows)
    with pytest.raises(ContractError, match="insufficient eligible"):
        c.engine.fit(replace(c.fixture.spec, cutoff_ns=54), c.fixture.requests, 54, 54, 54)


def test_corrected_truth_new_identity_old_bytes_and_TEST_isolation(
    calibration_case: CalibrationCase,
) -> None:
    c = calibration_case
    run = c.fit()
    state_bytes = canonical_json(c.repo.get(CalibrationState, run.state_id))
    requests = c.fixture.requests
    corrected = corrected_truth(c.repo, requests[0].target_id)
    new_requests = (replace(requests[0], target_id=corrected), *requests[1:])
    new = c.engine.fit(replace(c.fixture.spec, cutoff_ns=100), new_requests, 100, 100, 100)
    assert new.state_id != run.state_id
    assert canonical_json(c.repo.get(CalibrationState, run.state_id)) == state_bytes
    test = c.fixture.test_raw[0]
    sample = c.repo.get(ResearchSample, test.input.sample_id or "")
    corrected_truth(c.repo, sample.target_id or "", 110, 10.0)
    assert c.fit() == run
    assert canonical_json(c.repo.get(CalibrationState, run.state_id)) == state_bytes


def test_TEST_fit_denied_before_any_TEST_truth_read(
    calibration_case: CalibrationCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = calibration_case
    test = c.fixture.test_raw[0]
    sample = c.repo.get(ResearchSample, test.input.sample_id or "")
    spec = replace(
        c.fixture.spec,
        cutoff_ns=100,
        minimum_samples=1,
        partition=replace(
            c.fixture.spec.partition,
            reserved_sample_ids=(sample.fingerprint,),
            origin_range=TimeRange(80, 90),
        ),
    )
    original = c.repo.get

    def guarded(cls: type[ResearchSample], identity: str) -> ResearchSample:
        assert identity != sample.target_id, "TEST truth accessed during fit"
        return original(cls, identity)

    monkeypatch.setattr(c.repo, "get", guarded)
    with pytest.raises(ContractError, match="TEST"):
        c.engine.fit(
            spec, (CalibrationRequest(test.fingerprint, sample.target_id or ""),), 100, 100, 100
        )


def test_reservation_overlap_and_availability_guards(calibration_case: CalibrationCase) -> None:
    c = calibration_case
    first = c.fixture.requests[0]
    unreserved = replace(
        c.fixture.spec,
        partition=replace(
            c.fixture.spec.partition,
            reserved_sample_ids=c.fixture.spec.partition.reserved_sample_ids[:1],
        ),
    )
    with pytest.raises(ContractError, match="unreserved"):
        c.engine.fit(unreserved, c.fixture.requests, 55, 55, 55)
    bad = replace(
        c.fixture.spec,
        partition=replace(c.fixture.spec.partition, origin_range=TimeRange(41, 50)),
    )
    with pytest.raises(ContractError, match="origin/target"):
        c.engine.fit(bad, (first,), 55, 55, 55)
    late_raw = ProbabilisticEngine(c.repo).predict(
        c.fixture.raw_run.artifact_id, c.fixture.calibration_raw[0].input, 41
    )
    with pytest.raises(ContractError, match="did not exist historically"):
        c.engine.fit(
            c.fixture.spec, (replace(first, raw_forecast_id=late_raw.fingerprint),), 55, 55, 55
        )
    run = c.fit()
    with pytest.raises(ContractError, match="unavailable at historical origin"):
        c.engine.apply(run.state_id, c.fixture.calibration_raw[0].fingerprint, 55)
    future = c.engine.fit(c.fixture.spec, c.fixture.requests, 55, 61, 61)
    with pytest.raises(ContractError, match="unavailable at historical origin"):
        c.engine.apply_batch(
            future.state_id, tuple(p.fingerprint for p in c.fixture.deployment_raw)
        )
    with pytest.raises(ContractError, match="clock"):
        c.engine.apply(run.state_id, c.fixture.deployment_raw[0].fingerprint, 59)
    assert overlap_status(("a",), ("a",)) is CalibrationOverlapStatus.OVERLAPS_MODEL_TRAIN
    assert overlap_status(("a",), None) is CalibrationOverlapStatus.UNKNOWN


def test_TRAIN_tail_strict_holdout(calibration_case: CalibrationCase) -> None:
    from afre.research_datasets import DatasetEngine, SplitDefinition
    from afre.research_datasets.splits import FoldDefinition

    c = calibration_case
    fold = c.repo.get(FoldDefinition, c.fixture.spec.partition.fold_id)
    definition = c.repo.get(SplitDefinition, fold.split_definition_id)
    parent = DatasetEngine(c.repo).build_split(
        fold.dataset_id,
        replace(
            definition,
            name="split.calibration-parent",
            train=TimeRange(10, 50),
            validation=TimeRange(60, 70),
            training_cutoff_ns=55,
        ),
    )
    spec = replace(
        c.fixture.spec,
        partition=replace(
            c.fixture.spec.partition,
            policy=CalibrationPartitionPolicy.TRAIN_TAIL,
            fold_id=parent.fold_ids[0],
        ),
    )
    run = c.engine.fit(spec, c.fixture.requests, 55, 55, 55)
    assert run.inputs.overlap is CalibrationOverlapStatus.DISJOINT_FROM_MODEL_TRAIN
    with c.repo.read_snapshot():
        from afre.probabilistic import ProbabilisticFitInputs

        inputs = c.repo.get(ProbabilisticFitInputs, c.fixture.raw_run.inputs.fingerprint)
        sample = c.repo.get(ResearchSample, inputs.train_sample_ids[0])
    bad = replace(
        c.fixture.spec,
        partition=replace(
            c.fixture.spec.partition,
            reserved_sample_ids=(sample.fingerprint,),
            origin_range=TimeRange(10, 40),
        ),
    )
    with pytest.raises(ContractError, match="overlaps model TRAIN"):
        c.engine.fit(bad, c.fixture.requests, 55, 55, 55)


def test_event_and_quantile_application_identity(calibration_case: CalibrationCase) -> None:
    c = calibration_case
    run = c.fit(CalibrationMethod.ISOTONIC_PROBABILITY)
    state = c.repo.get(CalibrationState, run.state_id)
    spec = method_spec(c.fixture, CalibrationMethod.ISOTONIC_PROBABILITY)
    maps = tuple(c.repo.get(ProbabilityMapping, i) for i in state.mapping_ids)
    raw = c.fixture.deployment_raw[0]
    from afre.calibration.probability import mapped_probability

    with pytest.raises(ContractError, match="threshold/comparison"):
        mapped_probability(maps[0], ThresholdRequest(0.0, ThresholdComparison.GE), 0.5)
    with pytest.raises(ContractError, match="mapping event/spec"):
        outputs_for(
            spec, raw.quantiles, raw.threshold_probabilities, raw.median_value, (), (), None
        )
    with pytest.raises(ContractError, match="event/quantile"):
        outputs_for(spec, raw.quantiles, (), raw.median_value, maps, (), None)
    qrun = c.fit(CalibrationMethod.QUANTILE_OFFSET)
    qs = c.repo.get(CalibrationState, qrun.state_id)
    offsets = tuple(c.repo.get(QuantileOffset, i) for i in qs.offset_ids)
    with pytest.raises(ContractError, match="offset quantile"):
        outputs_for(
            method_spec(c.fixture, CalibrationMethod.QUANTILE_OFFSET),
            raw.quantiles,
            raw.threshold_probabilities,
            raw.median_value,
            (),
            offsets[:-1],
            None,
        )
    crun = c.fit(CalibrationMethod.CONFORMAL_ABSOLUTE_RESIDUAL)
    cs = c.repo.get(CalibrationState, crun.state_id)
    scores = c.repo.get(ConformalScoreSet, cs.conformal_id or "")
    assert scores.rank == len(scores.scores) and scores.q_hat == max(
        s.value for s in scores.scores
    )
    deployed = c.engine.apply(crun.state_id, raw.fingerprint, 60)
    assert deployed.calibrated_interval is not None
    assert deployed.calibrated_interval.lower == raw.median_value - scores.q_hat
    assert deployed.calibrated_interval.upper == raw.median_value + scores.q_hat


def test_TEST_evaluation_reuse_and_exact_comparison(calibration_case: CalibrationCase) -> None:
    c = calibration_case
    run = c.fit()
    fs = c.engine.apply_batch(run.state_id, tuple(p.fingerprint for p in c.fixture.test_raw))
    ids = tuple(f.fingerprint for f in fs)
    with pytest.raises(ContractError, match="TEST calibration evaluation requires"):
        c.engine.evaluate(ids, 100, 100)
    evaluation = c.engine.evaluate(ids, 100, 100, "calibration-test-1")
    again = c.engine.evaluate(ids, 100, 100, "calibration-test-2")
    from afre.probabilistic import ProbabilisticEvaluation
    from afre.research_datasets.splits import TestEvaluation

    raw = c.repo.get(ProbabilisticEvaluation, again.raw_evaluation_id)
    seal = c.repo.get(TestEvaluation, raw.test_evaluation_id or "")
    assert seal.previous_evaluation_ids
    with pytest.raises(ContractError, match="identity"):
        c.engine.evaluate(ids, 101, 101, "calibration-test-1")
    c.engine.compare(evaluation.raw_evaluation_id, evaluation.fingerprint)
    assert c.fixture.spec.interval is not None
    subset = ProbabilisticEngine(c.repo).evaluate(
        tuple(p.fingerprint for p in c.fixture.test_raw[:1]),
        100,
        100,
        ProbabilisticEvaluationProtocol((c.fixture.spec.interval,)),
        "calibration-test-subset",
    )
    with pytest.raises(ContractError, match="identical sample"):
        c.engine.compare(subset.fingerprint, evaluation.fingerprint)


@pytest.mark.parametrize("metric", list(DriftMetric))
def test_drift_states_no_refit(calibration_case: CalibrationCase, metric: DriftMetric) -> None:
    c = calibration_case
    run = c.fit()
    forecasts = c.engine.apply_batch(
        run.state_id, tuple(p.fingerprint for p in c.fixture.deployment_raw)
    )
    evaluation = c.engine.evaluate(tuple(p.fingerprint for p in forecasts), 75, 75)
    frozen = canonical_json(c.repo.get(CalibrationState, run.state_id))
    insufficient = c.engine.diagnose_drift(
        CalibrationDriftSpec(1, 100, metric, 0.5), (evaluation.fingerprint,)
    )
    assert insufficient.windows[0].state is DriftState.INSUFFICIENT_DATA
    stable = c.engine.diagnose_drift(
        CalibrationDriftSpec(1, 1, metric, 1.0), (evaluation.fingerprint,)
    )
    assert stable.windows[0].state is DriftState.STABLE
    value = stable.windows[0].value
    assert value is not None
    if value > 0:
        degraded = c.engine.diagnose_drift(
            CalibrationDriftSpec(1, 1, metric, 0.0), (evaluation.fingerprint,)
        )
        assert degraded.windows[0].state is DriftState.DEGRADED
    assert canonical_json(c.repo.get(CalibrationState, run.state_id)) == frozen
    assert c.engine.history(c.fixture.spec.raw_model_id) == (run,)


def test_empty_evaluation_and_unknown_drift(calibration_case: CalibrationCase) -> None:
    c = calibration_case
    run = c.fit()
    fs = c.engine.apply_batch(
        run.state_id, tuple(p.fingerprint for p in c.fixture.deployment_raw)
    )
    evaluation = c.engine.evaluate(tuple(f.fingerprint for f in fs), 60, 60)
    assert not evaluation.pairs
    assert (
        next(s for s in evaluation.calibrated_scores if s.name is ScoreName.COUNT).value == 0.0
    )
    drift = c.engine.diagnose_drift(
        CalibrationDriftSpec(1, 1, DriftMetric.ECE, 0.5), (evaluation.fingerprint,)
    )
    assert drift.windows[0].state is DriftState.INSUFFICIENT_DATA
    spec = replace(
        c.fixture.spec, events=replace(c.fixture.spec.events, requests=()), interval=None
    )
    noevent = c.engine.fit(spec, c.fixture.requests, 55, 55, 55)
    forecasts = c.engine.apply_batch(
        noevent.state_id, tuple(p.fingerprint for p in c.fixture.deployment_raw)
    )
    # Raw unselected events are preserved, so absent interval is the unsupported drift metric.
    ev = c.engine.evaluate(tuple(f.fingerprint for f in forecasts), 75, 75)
    unknown = c.engine.diagnose_drift(
        CalibrationDriftSpec(1, 1, DriftMetric.ABS_INTERVAL_GAP, 0.5), (ev.fingerprint,)
    )
    assert unknown.windows[0].state is DriftState.UNKNOWN

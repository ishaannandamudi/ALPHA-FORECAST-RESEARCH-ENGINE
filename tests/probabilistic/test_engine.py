"""Exact fitted evidence, causal availability, response-free publication and later scores."""

from dataclasses import replace
from typing import TypeVar

import pytest

from afre.probabilistic import (
    DistributionFamily as F,
)
from afre.probabilistic import (
    ObservationPolicy,
    ProbabilisticEvaluationProtocol,
    ProbabilisticForecast,
    QuantileInterval,
    ResidualCentering,
    ScalePolicy,
    ScaleSpec,
    ScoreName,
    ScoreState,
    ThresholdDefinition,
    TrainingDistribution,
    TrainingObservations,
    cdf,
    conditional_variance,
    expected_value,
    quantile,
)
from afre.probabilistic.scoring import score_forecast
from afre.research_datasets import DatasetEngine, Partition, SplitStrategy
from afre.schema import Artifact, ContractError
from afre.serialization import canonical_json
from afre.statistical_models import (
    DesignMatrix,
    ModelEngine,
    ModelFitInputs,
    PredictionInput,
    PredictionScope,
)
from afre.statistical_models.prediction import input_for_sample
from afre.target_engine.models import TargetVintage
from afre.time import TimeRange
from examples.research_dataset_demo import split_definition
from tests.probabilistic.conftest import ProbabilityCase

A = TypeVar("A", bound=Artifact)


@pytest.mark.parametrize("family", list(F))
@pytest.mark.parametrize("centering", list(ResidualCentering))
def test_exact_residuals_and_supported_queries(
    probability_case: ProbabilityCase, family: F, centering: ResidualCentering
) -> None:
    c = probability_case
    spec = replace(
        c.residual_spec,
        family=family,
        residual_centering=centering,
        thresholds=ThresholdDefinition(())
        if family is F.QUANTILE_SET
        else c.residual_spec.thresholds,
    )
    run = c.fit(spec)
    model = c.engine.model_artifact(run.artifact_id)
    obs = c.repo.get(TrainingObservations, run.inputs.observations_id)
    state = c.repo.get(TrainingDistribution, run.distribution_id)
    base = c.repo.get(DesignMatrix, run.inputs.matrix_id)
    assert tuple(r.sample_id for r in obs.rows) == tuple(r.sample_id for r in base.rows)
    assert all(
        r.point_value is not None and r.value == r.response - r.point_value for r in obs.rows
    )
    shift = state.diagnostics.raw_mean if centering is ResidualCentering.CENTER_MEAN else 0
    assert state.values == tuple(sorted(r.value - shift for r in obs.rows))
    assert state.diagnostics.centering_shift == shift
    predictions = c.engine.predict_samples(
        run.artifact_id, c.validation_ids, PredictionScope.VALIDATION
    )
    assert (
        c.engine.predict_samples(
            run.artifact_id, tuple(reversed(c.validation_ids)), PredictionScope.VALIDATION
        )
        == predictions
    )
    protocol = ProbabilisticEvaluationProtocol((QuantileInterval(0.1, 0.9),))
    evaluation = c.engine.evaluate(
        tuple(p.fingerprint for p in predictions), 100, 100, protocol
    )
    assert sum(evaluation.pit_histogram) == (
        0 if family is F.QUANTILE_SET else len(predictions)
    )
    assert len(evaluation.origin_scores) == 1
    p = predictions[0]
    assert quantile(p, 0.5) == p.median_value
    assert (
        expected_value(p) == p.expected_value
        and conditional_variance(p) == p.conditional_variance
    )
    assert p.model_available_ns == model.available_ns == state.available_ns == 40
    assert all(a.value <= b.value for a, b in zip(p.quantiles, p.quantiles[1:], strict=False))
    if family is F.QUANTILE_SET:
        assert p.expected_value is None and p.conditional_variance is None
        assert all(
            s.state is ScoreState.UNSUPPORTED
            for s in evaluation.scores
            if s.name in (ScoreName.CRPS, ScoreName.NLL, ScoreName.BRIER, ScoreName.PIT_MEAN)
        )
        with pytest.raises(ContractError, match="unsupported"):
            cdf(p, 0.0)
        with pytest.raises(ContractError, match="stored level"):
            quantile(p, 0.2)
    else:
        assert cdf(p, p.median_value) >= 0
    with pytest.raises(ContractError, match="requested quantiles"):
        score_forecast(p, 0.0, ProbabilisticEvaluationProtocol((QuantileInterval(0.2, 0.8),)))
    assert c.engine.model_history(spec.fold_id) == (run,)
    audit = c.engine.forecast_audit(p.fingerprint)
    assert obs.fingerprint in audit.evidence_ids and run.fingerprint in audit.evidence_ids
    assert c.engine.model_audit(evaluation.fingerprint).root_id == evaluation.fingerprint
    assert c.repo.audit() > 100


@pytest.mark.parametrize("family", [F.EMPIRICAL_RESIDUAL, F.GAUSSIAN_LOCATION_SCALE])
def test_unconditional_train_targets(probability_case: ProbabilityCase, family: F) -> None:
    c = probability_case
    run = c.fit(replace(c.unconditional_spec, family=family))
    obs = c.repo.get(TrainingObservations, run.inputs.observations_id)
    state = c.repo.get(TrainingDistribution, run.distribution_id)
    assert state.values == tuple(sorted(r.response for r in obs.rows))
    assert all(r.point_value is None and r.value == r.response for r in obs.rows)
    predictions = c.engine.predict_samples(
        run.artifact_id, c.validation_ids, PredictionScope.VALIDATION
    )
    assert len({canonical_json(p.distribution) for p in predictions}) == 1
    assert predictions[0].expected_value == state.diagnostics.distribution_mean


@pytest.mark.parametrize(
    "scale",
    [
        ScaleSpec(ScalePolicy.TRAIN_RESIDUAL_MAD_SCALED, mad_consistency_factor=2.0),
        ScaleSpec(ScalePolicy.FIXED_SCALE, 0.2),
    ],
)
def test_gaussian_declared_scale(probability_case: ProbabilityCase, scale: ScaleSpec) -> None:
    c = probability_case
    run = c.fit(replace(c.residual_spec, family=F.GAUSSIAN_LOCATION_SCALE, scale=scale))
    state = c.repo.get(TrainingDistribution, run.distribution_id)
    reference = (
        0.2
        if scale.policy is ScalePolicy.FIXED_SCALE
        else 2 * state.diagnostics.median_absolute_deviation
    )
    assert c.engine.model_artifact(run.artifact_id).scale == reference


@pytest.mark.parametrize(
    "partition",
    [
        Partition.VALIDATION,
        Partition.TEST,
        Partition.PURGED,
        Partition.EMBARGOED,
        Partition.INELIGIBLE,
    ],
)
def test_excluded_truth_cannot_enter_uncertainty(
    probability_case: ProbabilityCase, monkeypatch: pytest.MonkeyPatch, partition: Partition
) -> None:
    c = probability_case
    first = c.fit()
    with c.repo.read_snapshot(), c.repo.validation_cache():
        blocked = {
            s.target_id for s in c.repo.partition_samples(c.residual_spec.fold_id, partition)
        }
    original = c.repo.get

    def guarded(cls: type[A], identity: str) -> A:
        assert cls is not TargetVintage or identity not in blocked, (
            "excluded truth entered uncertainty"
        )
        return original(cls, identity)

    monkeypatch.setattr(c.repo, "get", guarded)
    assert c.fit() == first


@pytest.mark.parametrize(("cutoff", "admitted"), [(34, False), (35, True)])
def test_future_and_exact_cutoff_train_targets(
    probability_case: ProbabilityCase, cutoff: int, admitted: bool
) -> None:
    c = probability_case
    research = DatasetEngine(c.repo)
    definition = replace(
        split_definition(c.fixture),
        name=f"split.probability_{cutoff}",
        strategy=SplitStrategy.FIXED_HOLDOUT,
        step_ns=0,
        fold_count=1,
        training_cutoff_ns=cutoff,
        train=TimeRange(10, 30),
        preprocessing_spec_ids=(),
    )
    base_model = ModelEngine(c.repo).model_artifact(c.unconditional_spec.point_model_id)
    base_inputs = c.repo.get(ModelFitInputs, base_model.fit_inputs_id)
    split = research.build_split(base_inputs.dataset_id, definition)
    from afre.statistical_models import BaselineModelSpec

    base_spec = replace(
        c.repo.get(BaselineModelSpec, base_model.spec_id),
        fold_id=split.fold_ids[0],
        preprocessing_state_ids=(),
    )
    base = ModelEngine(c.repo).fit_model(base_spec, cutoff, cutoff, cutoff)
    spec = replace(
        c.unconditional_spec,
        point_model_id=base.artifact_id,
        fold_id=base_spec.fold_id,
        training_cutoff_ns=cutoff,
    )
    run = c.engine.fit_model(spec, cutoff, cutoff, cutoff)
    obs = c.repo.get(TrainingObservations, run.inputs.observations_id)
    assert (
        any(
            c.repo.get(TargetVintage, r.target_id).clocks.final_available_ns == 35
            for r in obs.rows
        )
        is admitted
    )
    assert all(
        c.repo.get(TargetVintage, r.target_id).clocks.final_available_ns <= cutoff
        for r in obs.rows
    )


def test_target_free_forecast_and_causal_availability(
    probability_case: ProbabilityCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = probability_case
    run = c.fit()
    original = c.repo.get

    def guarded(cls: type[A], identity: str) -> A:
        assert cls not in (TargetVintage, TrainingObservations, DesignMatrix), (
            "response read during forecast"
        )
        return original(cls, identity)

    with monkeypatch.context() as patch:
        patch.setattr(c.repo, "get", guarded)
        predictions = c.engine.predict_samples(
            run.artifact_id, c.validation_ids, PredictionScope.VALIDATION
        )
        assert predictions
    late = c.engine.fit_model(c.residual_spec, 40, 41, 41)
    with pytest.raises(ContractError, match="unavailable"):
        c.engine.predict_samples(late.artifact_id, c.validation_ids, PredictionScope.VALIDATION)
    assert (
        c.engine.predict_samples(run.artifact_id, c.validation_ids, PredictionScope.VALIDATION)
        == predictions
    )
    with pytest.raises(ContractError, match="backdated"):
        c.engine.predict_samples(
            run.artifact_id, c.validation_ids, PredictionScope.VALIDATION, 39
        )
    with pytest.raises(ContractError, match="before point"):
        c.engine.fit_model(c.residual_spec, 39, 40, 40)
    with pytest.raises(ContractError, match="clocks"):
        c.engine.fit_model(c.residual_spec, 41, 40, 40)


def test_in_sample_diagnostics_and_test_reuse(probability_case: ProbabilityCase) -> None:
    c = probability_case
    run = c.fit()
    train = c.engine.predict_samples(
        run.artifact_id, run.inputs.train_sample_ids, PredictionScope.IN_SAMPLE, 40
    )
    assert all(not p.historical_admissible for p in train)
    assert (
        c.engine.evaluate(tuple(p.fingerprint for p in train), 40, 40).scope
        is PredictionScope.IN_SAMPLE
    )
    with pytest.raises(ContractError, match="retrospective"):
        c.engine.predict_samples(
            run.artifact_id, run.inputs.train_sample_ids, PredictionScope.IN_SAMPLE
        )
    test = c.engine.predict_samples(run.artifact_id, c.test_ids, PredictionScope.TEST)
    ids = tuple(p.fingerprint for p in test)
    with pytest.raises(ContractError, match="explicit identity"):
        c.engine.evaluate(ids, 100, 100)
    evaluation = c.engine.evaluate(ids, 100, 100, test_evaluation_identity="afre6-test-v1")
    assert evaluation.test_evaluation_id
    assert (
        c.engine.evaluate(ids, 100, 100, test_evaluation_identity="afre6-test-v1") == evaluation
    )
    with pytest.raises(ContractError, match="identity reuse"):
        c.engine.evaluate(ids, 99, 100, test_evaluation_identity="afre6-test-v1")
    validation = c.forecast_ids(run)
    with pytest.raises(ContractError, match="non-TEST"):
        c.engine.evaluate(validation, 100, 100, test_evaluation_identity="invalid")
    with pytest.raises(ContractError, match="scope/partition"):
        c.engine.predict_samples(run.artifact_id, c.test_ids, PredictionScope.VALIDATION)
    assert c.engine.model_audit(evaluation.fingerprint).root_id == evaluation.fingerprint


def test_truth_cutoff_exclusion_and_exact_sample_comparison(
    probability_case: ProbabilityCase,
) -> None:
    c = probability_case
    run = c.fit()
    reference = c.fit(c.unconditional_spec)
    ids = c.forecast_ids(run)
    references = c.forecast_ids(reference)
    early = c.engine.evaluate(ids, 40, 40)
    assert not early.pairs and len(early.exclusions) == len(ids)
    assert next(s.value for s in early.scores if s.name is ScoreName.COUNT) == 0
    assert all(
        s.state is ScoreState.INSUFFICIENT_OBSERVATIONS
        for s in early.scores
        if s.name is not ScoreName.COUNT
    )
    evaluation = c.engine.evaluate(ids, 100, 100)
    ref = c.engine.evaluate(references, 100, 100)
    frozen = canonical_json(evaluation)
    comparison = c.engine.compare_models(evaluation.fingerprint, ref.fingerprint)
    assert comparison.sample_ids == tuple(sorted(c.validation_ids))
    assert canonical_json(c.repo.get(type(evaluation), evaluation.fingerprint)) == frozen
    for delta, left, right in zip(
        comparison.deltas, evaluation.scores, ref.scores, strict=True
    ):
        if left.value is not None and right.value is not None:
            assert delta.value == left.value - right.value
    assert c.engine.model_audit(comparison.fingerprint).root_id == comparison.fingerprint
    smaller = c.engine.evaluate(ids[:1], 100, 100)
    with pytest.raises(ContractError, match="identical samples"):
        c.engine.compare_models(smaller.fingerprint, ref.fingerprint)
    with pytest.raises(ContractError, match="protocol differs"):
        c.engine.compare_models(early.fingerprint, ref.fingerprint)
    with pytest.raises(ContractError, match="cannot mix"):
        c.engine.evaluate((ids[0], references[1]), 100, 100)
    with pytest.raises(ContractError, match="unavailable"):
        c.engine.evaluate(ids, 39, 40)
    with pytest.raises(ContractError, match="duplicates"):
        c.engine.evaluate((ids[0], ids[0]), 100, 100)
    with c.repo.read_snapshot(), c.repo.validation_cache():
        other = next(
            s.fingerprint
            for s in c.repo.partition_samples(c.residual_spec.fold_id, Partition.VALIDATION)
            if s.target_definition_id != c.residual_spec.target.fingerprint
        )
    with pytest.raises(ContractError, match="target/horizon"):
        c.engine.predict_samples(run.artifact_id, (other,), PredictionScope.VALIDATION)


def test_external_forecast_cannot_invent_truth(probability_case: ProbabilityCase) -> None:
    c = probability_case
    run = c.fit()
    base = ModelEngine(c.repo).model_artifact(c.residual_spec.point_model_id)
    with c.repo.read_snapshot(), c.repo.validation_cache():
        request = input_for_sample(
            c.repo, base, c.validation_ids[0], PredictionScope.VALIDATION
        )
    external = replace(request, sample_id=None, scope=PredictionScope.OUT_OF_SAMPLE_OTHER)
    prediction = c.engine.predict(run.artifact_id, external, 40)
    with pytest.raises(ContractError, match="pinned truth"):
        c.engine.evaluate((prediction.fingerprint,), 100, 100)
    constructor = PredictionInput
    assert "target_value" not in constructor.__dataclass_fields__
    assert c.repo.get(ProbabilisticForecast, prediction.fingerprint) == prediction


def test_unconditional_scaffold_and_unknown_versions(probability_case: ProbabilityCase) -> None:
    c = probability_case
    with pytest.raises(ContractError, match="TRAIN mean"):
        c.fit(replace(c.residual_spec, observation_policy=ObservationPolicy.TRAIN_TARGETS))
    with pytest.raises(ContractError, match="target/fold/cutoff"):
        c.fit(replace(c.residual_spec, training_cutoff_ns=39))
    with pytest.raises(ContractError, match="unknown"):
        c.fit(replace(c.residual_spec, implementation_version="future"))
    with pytest.raises(ContractError, match="unknown"):
        c.fit(replace(c.residual_spec, approximation_version="future"))

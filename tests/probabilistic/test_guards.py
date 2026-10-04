"""Degenerate real fits, incomplete publication and numerical/lineage truth boundaries."""

from dataclasses import replace
from pathlib import Path

import pytest

from afre.probabilistic import (
    DistributionFamily as F,
)
from afre.probabilistic import (
    DistributionState,
    ObservationPolicy,
    ProbabilisticEngine,
    ProbabilisticRepository,
    QuantileDefinition,
    ScalePolicy,
    ScaleSpec,
    ScoreName,
    ScoreState,
    ThresholdDefinition,
    TrainingDistribution,
    TrainingObservations,
)
from afre.research_datasets import DatasetEngine, ResearchSample
from afre.schema import Artifact, ContractError
from afre.statistical_models import ModelEngine, ModelFamily, PredictionScope
from afre.target_engine.market_data import TargetBar
from benchmarks.probabilistic import numerical_validation
from examples.probabilistic_demo import probability_spec
from examples.research_dataset_demo import populate, split_definition
from examples.statistical_baselines_demo import baseline_spec
from tests.probabilistic.conftest import ProbabilityCase


class ConstantTruthRepository(ProbabilisticRepository):
    def put(self, value: Artifact) -> str:
        if isinstance(value, TargetBar):
            value = replace(value, close=100.0)
        return super().put(value)


def test_real_constant_train_state_and_gaussian_failure(tmp_path: Path) -> None:
    with ConstantTruthRepository(tmp_path / "constant.sqlite") as repo:
        fixture = populate(repo)
        research = DatasetEngine(repo)
        dataset = research.build_dataset(fixture.definition, fixture.requests, 100, 100)
        split = research.build_split(dataset.fingerprint, split_definition(fixture))
        state = research.fit_preprocessing(split.fold_ids[0], fixture.preprocessing)
        point = ModelEngine(repo).fit_model(
            baseline_spec(fixture, split, state, ModelFamily.UNCONDITIONAL_MEAN), 40, 40, 40
        )
        spec = probability_spec(
            point.artifact_id,
            split.fold_ids[0],
            fixture,
            F.EMPIRICAL_RESIDUAL,
            ObservationPolicy.TRAIN_TARGETS,
        )
        engine = ProbabilisticEngine(repo)
        run = engine.fit_model(spec, 40, 40, 40)
        pool = repo.get(TrainingDistribution, run.distribution_id)
        assert (
            pool.values == (0.0,) * len(pool.values)
            and pool.diagnostics.degenerate_observations
        )
        qspec = replace(spec, family=F.QUANTILE_SET, thresholds=ThresholdDefinition(()))
        qrun = engine.fit_model(qspec, 40, 40, 40)
        from afre.research_datasets import Partition

        with repo.read_snapshot(), repo.validation_cache():
            ids = tuple(
                s.fingerprint
                for s in repo.partition_samples(spec.fold_id, Partition.VALIDATION)
                if s.target_definition_id == spec.target.fingerprint
            )
        forecasts = engine.predict_samples(run.artifact_id, ids, PredictionScope.VALIDATION)
        assert all(
            p.distribution.state is DistributionState.DEGENERATE and p.conditional_variance == 0
            for p in forecasts
        )
        assert all(
            p.distribution.state is DistributionState.DEGENERATE
            for p in engine.predict_samples(qrun.artifact_id, ids, PredictionScope.VALIDATION)
        )
        before = repo._connection.execute("SELECT count(*) FROM p_artifacts").fetchone()[0]
        with pytest.raises(ContractError, match="zero continuous"):
            engine.fit_model(replace(spec, family=F.GAUSSIAN_LOCATION_SCALE), 40, 40, 40)
        assert (
            repo._connection.execute("SELECT count(*) FROM p_artifacts").fetchone()[0] == before
        )
        fixed = engine.fit_model(
            replace(
                spec,
                family=F.GAUSSIAN_LOCATION_SCALE,
                scale=ScaleSpec(ScalePolicy.FIXED_SCALE, 0.01),
            ),
            40,
            40,
            40,
        )
        assert repo.get(
            TrainingDistribution, fixed.distribution_id
        ).diagnostics.degenerate_observations


def test_incomplete_fit_and_sparse_protocol_comparison(
    probability_case: ProbabilityCase,
) -> None:
    c = probability_case
    empirical = c.fit()
    gaussian = c.fit(replace(c.residual_spec, family=F.GAUSSIAN_LOCATION_SCALE))
    left = c.engine.evaluate(c.forecast_ids(gaussian), 100, 100)
    right = c.engine.evaluate(c.forecast_ids(empirical), 100, 100)
    comparison = c.engine.compare_models(left.fingerprint, right.fingerprint)
    nll = next(s for s in comparison.deltas if s.name is ScoreName.NLL)
    assert nll.state is ScoreState.UNSUPPORTED and nll.value is None
    different = c.fit(replace(c.residual_spec, quantiles=QuantileDefinition((0.2, 0.5, 0.8))))
    other = c.engine.evaluate(c.forecast_ids(different), 100, 100)
    with pytest.raises(ContractError, match="quantile/threshold"):
        c.engine.compare_models(other.fingerprint, right.fingerprint)
    conn = c.repo._connection
    trigger = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='immutable_p_fits_delete'"
    ).fetchone()[0]
    conn.execute("DROP TRIGGER immutable_p_fits_delete")
    conn.execute("DELETE FROM p_fits WHERE fingerprint=?", (empirical.fingerprint,))
    conn.execute(trigger)
    with pytest.raises(ContractError, match="completed fit"):
        c.forecast_ids(empirical)
    with pytest.raises(KeyError):
        c.repo.get(TrainingObservations, "afre.p_observations:1.0:" + "a" * 64)


def test_forecast_audit_omits_heldout_truth_evaluation_adds_it(
    probability_case: ProbabilityCase,
) -> None:
    c = probability_case
    run = c.fit()
    forecasts = c.forecast_ids(run)
    heldout = {c.repo.get(ResearchSample, p).target_id for p in c.validation_ids}
    audit = c.engine.forecast_audit(forecasts[0])
    assert not heldout.intersection(audit.evidence_ids)
    evaluation = c.engine.evaluate(forecasts, 100, 100)
    evaluated = c.engine.model_audit(evaluation.fingerprint)
    assert heldout <= set(evaluated.evidence_ids)


def test_reported_numerical_errors() -> None:
    errors = numerical_validation()
    assert errors["normal_cdf_max_abs_error"] < 1e-15
    assert errors["inverse_normal_max_abs_error"] < 3e-15
    assert errors["gaussian_crps_quadrature_abs_error"] < 5e-12
    assert errors["gaussian_crps_fixture_abs_error"] < 1e-15
    assert errors["empirical_crps_pairwise_abs_error"] < 1e-14
    assert errors["type7_quantile_max_abs_error"] < 1e-14
    assert errors["threshold_probability_max_abs_error"] == 0
    assert errors["gaussian_threshold_abs_error"] < 1e-15

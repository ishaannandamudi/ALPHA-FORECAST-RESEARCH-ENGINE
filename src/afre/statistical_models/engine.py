"""Bounded offline fit/predict/evaluate APIs; no tuning or executable model loading."""

from collections.abc import Callable
from time import perf_counter

from afre.schema import require
from afre.statistical_models.artifacts import (
    BaselineComparison,
    FittedModelArtifact,
    ModelFitInputs,
    ModelFitRun,
    ModelLineageAudit,
    PointEvaluation,
    PointForecast,
    PredictionInput,
)
from afre.statistical_models.definitions import BaselineModelSpec
from afre.statistical_models.design_matrix import build_matrix
from afre.statistical_models.evaluation import comparison_for, evaluate_forecasts, test_record
from afre.statistical_models.prediction import forecast_for, input_for_sample
from afre.statistical_models.repository import ModelRepository
from afre.statistical_models.schema import (
    IMPLEMENTATION_VERSION,
    SOLVER_VERSION,
    PredictionScope,
)
from afre.statistical_models.validation import fitted_artifact, lineage_audit
from afre.time import validate_timestamp


class ModelEngine:
    def __init__(self, repository: ModelRepository) -> None:
        self.repository = repository
        self.last_fit_timings: dict[str, float] = {}

    def fit_model(
        self,
        spec: BaselineModelSpec,
        fit_started_ns: int,
        fit_completed_ns: int,
        available_ns: int,
        snapshot_hook: Callable[[], None] | None = None,
    ) -> ModelFitRun:
        for at in (fit_started_ns, fit_completed_ns, available_ns):
            validate_timestamp(at)
        require(
            spec.implementation_version == IMPLEMENTATION_VERSION
            and spec.solver_version == SOLVER_VERSION,
            "unsupported model/solver implementation",
        )
        repo = self.repository
        repo.check_model_bounds(spec)
        started = perf_counter()
        with repo.read_snapshot(), repo.validation_cache():
            repo._connection.execute("SELECT count(*) FROM r_folds").fetchone()
            if snapshot_hook is not None:
                snapshot_hook()
            matrix = build_matrix(repo, spec, fit_started_ns)
            matrix_seconds = perf_counter() - started
            inputs = ModelFitInputs(
                spec.fingerprint,
                matrix.dataset_id,
                matrix.split_id,
                matrix.fold_id,
                matrix.fingerprint,
                tuple(r.sample_id for r in matrix.rows),
                spec.preprocessing_state_ids,
                matrix.training_cutoff_ns,
                fit_started_ns,
                fit_completed_ns,
                available_ns,
            )
            solve_started = perf_counter()
            artifact = fitted_artifact(repo, spec, matrix, inputs)
            solve_seconds = perf_counter() - solve_started
            run = ModelFitRun(inputs, artifact.fingerprint, artifact.diagnostics.fingerprint)
        publish_started = perf_counter()
        with repo.transaction(), repo.validation_cache():
            for value in (
                spec.foundation_spec,
                spec,
                matrix,
                inputs,
                artifact.diagnostics,
                artifact,
                run,
            ):
                repo.put(value)
        self.last_fit_timings = {
            "design_matrix": matrix_seconds,
            "solver": solve_seconds,
            "persistence_and_validation": perf_counter() - publish_started,
        }
        return run

    def model_artifact(self, identity: str) -> FittedModelArtifact:
        with self.repository.read_snapshot(), self.repository.validation_cache():
            return self.repository.resolve(FittedModelArtifact, identity)

    def predict(
        self, artifact_id: str, request: PredictionInput, computed_ns: int
    ) -> PointForecast:
        return self.predict_batch(artifact_id, (request,), computed_ns)[0]

    def predict_batch(
        self,
        artifact_id: str,
        requests: tuple[PredictionInput, ...],
        computed_ns: int | None = None,
    ) -> tuple[PointForecast, ...]:
        if computed_ns is not None:
            validate_timestamp(computed_ns)
        repo = self.repository
        require(
            0 < len(requests) <= repo.model_bounds.predictions
            and len({r.fingerprint for r in requests}) == len(requests),
            "prediction batch count/duplicate bound",
        )
        with repo.read_snapshot(), repo.validation_cache():
            model = repo.resolve(FittedModelArtifact, artifact_id)
            ordered = tuple(
                sorted(
                    requests,
                    key=lambda r: (
                        r.origin.timestamp_ns,
                        r.origin.instrument.fingerprint,
                        r.fingerprint,
                    ),
                )
            )
            forecasts = tuple(
                forecast_for(
                    repo,
                    model,
                    request,
                    request.origin.timestamp_ns if computed_ns is None else computed_ns,
                )
                for request in ordered
            )
        with repo.transaction(), repo.validation_cache():
            for forecast in forecasts:
                repo.put(forecast.input)
                repo.put(forecast)
        return forecasts

    def predict_samples(
        self,
        artifact_id: str,
        sample_ids: tuple[str, ...],
        scope: PredictionScope,
        computed_ns: int | None = None,
    ) -> tuple[PointForecast, ...]:
        repo = self.repository
        require(0 < len(sample_ids) <= repo.model_bounds.predictions, "prediction sample bound")
        with repo.read_snapshot(), repo.validation_cache():
            model = repo.resolve(FittedModelArtifact, artifact_id)
            requests = tuple(
                input_for_sample(repo, model, identity, scope) for identity in sample_ids
            )
        return self.predict_batch(artifact_id, requests, computed_ns)

    def evaluate(
        self,
        prediction_ids: tuple[str, ...],
        evaluation_cutoff_ns: int,
        available_ns: int,
        test_evaluation_identity: str | None = None,
        purpose: str = "fixed-baseline-evaluation",
    ) -> PointEvaluation:
        validate_timestamp(evaluation_cutoff_ns)
        validate_timestamp(available_ns)
        repo = self.repository
        with repo.transaction(), repo.validation_cache():
            require(bool(prediction_ids), "empty evaluation predictions")
            first = repo.resolve(PointForecast, prediction_ids[0])
            seal = None
            if first.input.scope is PredictionScope.TEST:
                require(
                    test_evaluation_identity is not None,
                    "TEST evaluation requires explicit identity",
                )
                assert test_evaluation_identity is not None
                model = repo.resolve(FittedModelArtifact, first.model_artifact_id)
                spec = repo.resolve(BaselineModelSpec, model.spec_id)
                seal = test_record(
                    repo, spec.fold_id, test_evaluation_identity, purpose, evaluation_cutoff_ns
                )
                repo.put(seal)
            else:
                require(
                    test_evaluation_identity is None,
                    "non-TEST evaluation cannot use TEST identity",
                )
            evaluation = evaluate_forecasts(
                repo, prediction_ids, evaluation_cutoff_ns, available_ns, seal
            )
            repo.put(evaluation)
            return evaluation

    def compare_models(
        self, candidate_evaluation_id: str, reference_evaluation_id: str
    ) -> BaselineComparison:
        with self.repository.transaction(), self.repository.validation_cache():
            comparison = comparison_for(
                self.repository, candidate_evaluation_id, reference_evaluation_id
            )
            self.repository.put(comparison)
            return comparison

    def model_audit(self, root_id: str) -> ModelLineageAudit:
        with self.repository.transaction(), self.repository.validation_cache():
            audit = lineage_audit(self.repository, root_id)
            self.repository.put(audit)
            return audit

    def prediction_audit(self, prediction_id: str) -> ModelLineageAudit:
        return self.model_audit(prediction_id)

    def model_history(self, fold_id: str) -> tuple[ModelFitRun, ...]:
        with self.repository.read_snapshot(), self.repository.validation_cache():
            return self.repository.model_history(fold_id)

"""Atomic frozen uncertainty fitting, target-free forecasts and proper evaluation."""

from collections.abc import Callable
from time import perf_counter

from afre.probabilistic.artifacts import (
    ProbabilisticComparison,
    ProbabilisticEvaluation,
    ProbabilisticFitInputs,
    ProbabilisticFitRun,
    ProbabilisticForecast,
    ProbabilisticLineageAudit,
    ProbabilisticModelArtifact,
    TrainingDistribution,
)
from afre.probabilistic.definitions import (
    ProbabilisticEvaluationProtocol,
    ProbabilisticModelSpec,
)
from afre.probabilistic.evaluation import comparison_for, evaluate_forecasts
from afre.probabilistic.fitting import (
    artifact_for,
    distribution_for,
    observations_for,
    point_context,
)
from afre.probabilistic.forecast import forecast_for
from afre.probabilistic.lineage import lineage_audit
from afre.probabilistic.repository import ProbabilisticRepository
from afre.schema import require
from afre.statistical_models.artifacts import FittedModelArtifact, PredictionInput
from afre.statistical_models.evaluation import test_record
from afre.statistical_models.prediction import input_for_sample
from afre.statistical_models.schema import PredictionScope
from afre.time import validate_timestamp


class ProbabilisticEngine:
    def __init__(self, repository: ProbabilisticRepository) -> None:
        self.repository = repository
        self.last_fit_timings: dict[str, float] = {}

    def fit_model(
        self,
        spec: ProbabilisticModelSpec,
        fit_started_ns: int,
        fit_completed_ns: int,
        available_ns: int,
        snapshot_hook: Callable[[], None] | None = None,
    ) -> ProbabilisticFitRun:
        for at in (fit_started_ns, fit_completed_ns, available_ns):
            validate_timestamp(at)
        repo = self.repository
        repo.check_probability_bounds(spec)
        started = perf_counter()
        with repo.read_snapshot(), repo.validation_cache():
            repo._connection.execute("SELECT count(*) FROM m_fits").fetchone()
            if snapshot_hook is not None:
                snapshot_hook()
            model, base_inputs = point_context(repo, spec, True)
            require(
                fit_started_ns >= model.available_ns,
                "probability fit before point availability",
            )
            observations = observations_for(repo, spec)
            evidence_seconds = perf_counter() - started
            inputs = ProbabilisticFitInputs(
                spec.fingerprint,
                model.fingerprint,
                base_inputs.fingerprint,
                observations.fingerprint,
                base_inputs.matrix_id,
                base_inputs.dataset_id,
                base_inputs.split_id,
                base_inputs.fold_id,
                spec.target.fingerprint,
                tuple(r.sample_id for r in observations.rows),
                base_inputs.preprocessing_state_ids,
                base_inputs.training_cutoff_ns,
                fit_started_ns,
                fit_completed_ns,
                available_ns,
            )
            require(
                available_ns >= max(r.data_available_ns for r in observations.rows),
                "probability availability before TRAIN observations",
            )
            fit_started = perf_counter()
            state = distribution_for(spec, observations, available_ns)
            artifact = artifact_for(spec, inputs, state)
            run = ProbabilisticFitRun(
                inputs, artifact.fingerprint, state.fingerprint, state.diagnostics.fingerprint
            )
            fitting_seconds = perf_counter() - fit_started
        publish = perf_counter()
        with repo.transaction(), repo.validation_cache():
            for value in (
                spec.quantiles,
                spec.scale,
                *spec.thresholds.requests,
                spec.thresholds,
                spec,
                observations,
                inputs,
                state.diagnostics,
                state,
                artifact,
                run,
            ):
                repo.put(value)
        self.last_fit_timings = {
            "TRAIN_evidence": evidence_seconds,
            "uncertainty_fit": fitting_seconds,
            "persistence_and_validation": perf_counter() - publish,
        }
        return run

    def model_artifact(self, identity: str) -> ProbabilisticModelArtifact:
        with self.repository.read_snapshot(), self.repository.validation_cache():
            return self.repository.resolve(ProbabilisticModelArtifact, identity)

    def predict(
        self, artifact_id: str, request: PredictionInput, computed_ns: int
    ) -> ProbabilisticForecast:
        return self.predict_batch(artifact_id, (request,), computed_ns)[0]

    def predict_batch(
        self,
        artifact_id: str,
        requests: tuple[PredictionInput, ...],
        computed_ns: int | None = None,
    ) -> tuple[ProbabilisticForecast, ...]:
        if computed_ns is not None:
            validate_timestamp(computed_ns)
        repo = self.repository
        require(
            0 < len(requests) <= repo.probabilistic_bounds.forecasts
            and len({r.fingerprint for r in requests}) == len(requests),
            "probability forecast count/duplicate bound",
        )
        with repo.read_snapshot(), repo.validation_cache():
            artifact = repo.resolve(ProbabilisticModelArtifact, artifact_id)
            state = repo.resolve(TrainingDistribution, artifact.distribution_id)
            spec = repo.resolve(ProbabilisticModelSpec, artifact.spec_id)
            require(
                len(requests)
                * (
                    len(state.values)
                    + len(spec.quantiles.levels)
                    + len(spec.thresholds.requests)
                )
                <= repo.probabilistic_bounds.work_cells,
                "probability forecast work bound",
            )
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
            results = tuple(
                forecast_for(
                    repo,
                    artifact,
                    request,
                    request.origin.timestamp_ns if computed_ns is None else computed_ns,
                )
                for request in ordered
            )
        with repo.transaction(), repo.validation_cache():
            for point, forecast in results:
                repo.put(point.input)
                repo.put(point)
                repo.put(forecast)
        return tuple(forecast for _, forecast in results)

    def predict_samples(
        self,
        artifact_id: str,
        sample_ids: tuple[str, ...],
        scope: PredictionScope,
        computed_ns: int | None = None,
    ) -> tuple[ProbabilisticForecast, ...]:
        repo = self.repository
        require(
            0 < len(sample_ids) <= repo.probabilistic_bounds.forecasts,
            "probability sample batch bound",
        )
        with repo.read_snapshot(), repo.validation_cache():
            artifact = repo.resolve(ProbabilisticModelArtifact, artifact_id)
            spec = repo.resolve(ProbabilisticModelSpec, artifact.spec_id)
            model = repo.resolve(FittedModelArtifact, spec.point_model_id)
            requests = tuple(input_for_sample(repo, model, p, scope) for p in sample_ids)
        return self.predict_batch(artifact_id, requests, computed_ns)

    def evaluate(
        self,
        forecast_ids: tuple[str, ...],
        evaluation_cutoff_ns: int,
        available_ns: int,
        protocol: ProbabilisticEvaluationProtocol | None = None,
        test_evaluation_identity: str | None = None,
        purpose: str = "fixed-probabilistic-evaluation",
    ) -> ProbabilisticEvaluation:
        for at in (evaluation_cutoff_ns, available_ns):
            validate_timestamp(at)
        repo = self.repository
        policy = protocol or ProbabilisticEvaluationProtocol()
        with repo.transaction(), repo.validation_cache():
            require(
                0 < len(forecast_ids) <= repo.probabilistic_bounds.forecasts,
                "probability evaluation batch bound",
            )
            first = repo.resolve(ProbabilisticForecast, forecast_ids[0])
            seal = None
            if first.input.scope is PredictionScope.TEST:
                require(
                    test_evaluation_identity is not None,
                    "TEST probability evaluation requires explicit identity",
                )
                assert test_evaluation_identity is not None
                model = repo.resolve(ProbabilisticModelArtifact, first.model_artifact_id)
                spec = repo.resolve(ProbabilisticModelSpec, model.spec_id)
                seal = test_record(
                    repo, spec.fold_id, test_evaluation_identity, purpose, evaluation_cutoff_ns
                )
                repo.put(seal)
            else:
                require(
                    test_evaluation_identity is None,
                    "non-TEST probability evaluation cannot use TEST identity",
                )
            for interval in policy.intervals:
                repo.put(interval)
            repo.put(policy)
            result = evaluate_forecasts(
                repo, forecast_ids, policy, evaluation_cutoff_ns, available_ns, seal
            )
            repo.put(result)
            return result

    def compare_models(
        self, candidate_evaluation_id: str, reference_evaluation_id: str
    ) -> ProbabilisticComparison:
        with self.repository.transaction(), self.repository.validation_cache():
            result = comparison_for(
                self.repository, candidate_evaluation_id, reference_evaluation_id
            )
            self.repository.put(result)
            return result

    def model_audit(self, root_id: str) -> ProbabilisticLineageAudit:
        with self.repository.transaction(), self.repository.validation_cache():
            result = lineage_audit(self.repository, root_id)
            self.repository.put(result)
            return result

    def forecast_audit(self, forecast_id: str) -> ProbabilisticLineageAudit:
        return self.model_audit(forecast_id)

    def model_history(self, fold_id: str) -> tuple[ProbabilisticFitRun, ...]:
        with self.repository.read_snapshot(), self.repository.validation_cache():
            return self.repository.probability_history(fold_id)

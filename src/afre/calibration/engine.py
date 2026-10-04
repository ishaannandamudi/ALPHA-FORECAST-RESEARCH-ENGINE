"""Atomic calibration fit/application, independent evaluation and bounded audits."""

from collections.abc import Callable
from time import perf_counter

from afre.calibration.application import forecast_for
from afre.calibration.artifacts import (
    CalibratedForecast,
    CalibrationComparison,
    CalibrationDriftDiagnostics,
    CalibrationEvaluation,
    CalibrationFitRun,
    CalibrationLineageAudit,
    CalibrationState,
    ProbabilityMapping,
)
from afre.calibration.definitions import (
    CalibrationDriftSpec,
    CalibrationRequest,
    CalibrationSpec,
)
from afre.calibration.drift import drift_for
from afre.calibration.evaluation import comparison_for, evaluation_for
from afre.calibration.fitting import fit_for
from afre.calibration.lineage import lineage_audit
from afre.calibration.repository import CalibrationRepository
from afre.probabilistic.artifacts import ProbabilisticForecast, ProbabilisticModelArtifact
from afre.probabilistic.definitions import (
    ProbabilisticEvaluationProtocol,
    ProbabilisticModelSpec,
)
from afre.probabilistic.evaluation import evaluate_forecasts
from afre.schema import require
from afre.statistical_models.evaluation import test_record
from afre.statistical_models.schema import PredictionScope
from afre.time import validate_timestamp


class CalibrationEngine:
    def __init__(self, repository: CalibrationRepository) -> None:
        self.repository = repository
        self.last_fit_timings: dict[str, float] = {}

    def fit(
        self,
        spec: CalibrationSpec,
        requests: tuple[CalibrationRequest, ...],
        fit_started_ns: int,
        fit_completed_ns: int,
        available_ns: int,
        snapshot_hook: Callable[[], None] | None = None,
    ) -> CalibrationFitRun:
        for at in (fit_started_ns, fit_completed_ns, available_ns):
            validate_timestamp(at)
        repo = self.repository
        repo.check_calibration_bounds(spec)
        started = perf_counter()
        with repo.read_snapshot(), repo.validation_cache():
            repo._connection.execute("SELECT count(*) FROM p_forecasts").fetchone()
            if snapshot_hook is not None:
                snapshot_hook()
            bundle = fit_for(
                repo, spec, requests, fit_started_ns, fit_completed_ns, available_ns
            )
        fitted = perf_counter()
        with repo.transaction(), repo.validation_cache():
            for value in (
                spec.partition,
                spec.bins,
                spec.events,
                spec.quantiles,
                *((spec.interval,) if spec.interval else ()),
                spec,
                *bundle.values,
            ):
                repo.put(value)
        self.last_fit_timings = {
            "sample_and_fit": fitted - started,
            "persistence_and_validation": perf_counter() - fitted,
        }
        return bundle.run

    def apply(
        self, state_id: str, raw_forecast_id: str, computed_ns: int
    ) -> CalibratedForecast:
        return self.apply_batch(state_id, (raw_forecast_id,), computed_ns)[0]

    def apply_batch(
        self, state_id: str, raw_forecast_ids: tuple[str, ...], computed_ns: int | None = None
    ) -> tuple[CalibratedForecast, ...]:
        if computed_ns is not None:
            validate_timestamp(computed_ns)
        repo = self.repository
        require(
            0 < len(raw_forecast_ids) <= repo.calibration_bounds.forecasts
            and len(set(raw_forecast_ids)) == len(raw_forecast_ids),
            "calibrated forecast count/duplicates",
        )
        with repo.read_snapshot(), repo.validation_cache():
            state = repo.resolve(CalibrationState, state_id)
            forecasts = tuple(repo.resolve(ProbabilisticForecast, f) for f in raw_forecast_ids)
            map_work = sum(
                max(1, len(repo.resolve(ProbabilityMapping, identity).blocks).bit_length())
                for identity in state.mapping_ids
            )
            require(
                sum(
                    len(f.quantiles)
                    + len(f.threshold_probabilities)
                    + map_work
                    + len(state.offset_ids)
                    for f in forecasts
                )
                <= repo.calibration_bounds.work_cells,
                "calibration application work bound",
            )
            forecasts = tuple(
                sorted(
                    forecasts,
                    key=lambda f: (
                        f.input.origin.timestamp_ns,
                        f.input.origin.instrument.fingerprint,
                        f.fingerprint,
                    ),
                )
            )
            results = tuple(
                forecast_for(
                    repo,
                    state,
                    raw,
                    raw.input.origin.timestamp_ns if computed_ns is None else computed_ns,
                )
                for raw in forecasts
            )
        with repo.transaction(), repo.validation_cache():
            for result in results:
                repo.put(result)
        return results

    def evaluate(
        self,
        forecast_ids: tuple[str, ...],
        cutoff_ns: int,
        available_ns: int,
        test_evaluation_identity: str | None = None,
        purpose: str = "fixed-calibration-evaluation",
    ) -> CalibrationEvaluation:
        repo = self.repository
        require(
            0 < len(forecast_ids) <= repo.calibration_bounds.forecasts,
            "calibration evaluation count bound",
        )
        # One write transaction also pins the AFRE-6 evaluation and explicit TEST record.
        with repo.transaction(), repo.validation_cache():
            forecasts = tuple(repo.resolve(CalibratedForecast, f) for f in forecast_ids)
            state = repo.resolve(CalibrationState, forecasts[0].state_id)
            spec = repo.resolve(CalibrationSpec, state.inputs.spec_id)
            protocol = ProbabilisticEvaluationProtocol(
                (spec.interval,) if spec.interval else ()
            )
            raw_first = repo.resolve(ProbabilisticForecast, forecasts[0].raw_forecast_id)
            seal = None
            if raw_first.input.scope is PredictionScope.TEST:
                require(
                    test_evaluation_identity is not None,
                    "TEST calibration evaluation requires explicit identity",
                )
                assert test_evaluation_identity is not None
                model = repo.resolve(ProbabilisticModelArtifact, spec.raw_model_id)
                raw_spec = repo.resolve(ProbabilisticModelSpec, model.spec_id)
                seal = test_record(
                    repo, raw_spec.fold_id, test_evaluation_identity, purpose, cutoff_ns
                )
                repo.put(seal)
            else:
                require(
                    test_evaluation_identity is None,
                    "non-TEST evaluation cannot use TEST identity",
                )
            for interval in protocol.intervals:
                repo.put(interval)
            repo.put(protocol)
            raw = evaluate_forecasts(
                repo,
                tuple(f.raw_forecast_id for f in forecasts),
                protocol,
                cutoff_ns,
                available_ns,
                seal,
            )
            repo.put(raw)
            result = evaluation_for(repo, forecast_ids, raw)
            repo.put(result)
        return result

    def compare(
        self, raw_evaluation_id: str, calibrated_evaluation_id: str
    ) -> CalibrationComparison:
        with self.repository.transaction(), self.repository.validation_cache():
            result = comparison_for(
                self.repository, raw_evaluation_id, calibrated_evaluation_id
            )
            self.repository.put(result)
            return result

    def diagnose_drift(
        self, spec: CalibrationDriftSpec, evaluation_ids: tuple[str, ...]
    ) -> CalibrationDriftDiagnostics:
        with self.repository.transaction(), self.repository.validation_cache():
            result = drift_for(self.repository, spec, evaluation_ids)
            self.repository.put(spec)
            self.repository.put(result)
            return result

    def calibration_audit(self, root_id: str) -> CalibrationLineageAudit:
        with self.repository.transaction(), self.repository.validation_cache():
            result = lineage_audit(self.repository, root_id)
            self.repository.put(result)
            return result

    def history(self, raw_model_id: str) -> tuple[CalibrationFitRun, ...]:
        with self.repository.read_snapshot(), self.repository.validation_cache():
            return self.repository.calibration_history(raw_model_id)

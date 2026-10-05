"""Snapshot-frozen fitting/assembly and atomic publication/evaluation."""

from collections.abc import Callable

from afre.forecast import ForecastOrigin
from afre.multihorizon.artifacts import (
    ConsistencyAudit,
    CovarianceArtifact,
    HorizonForecastEntry,
    MultiHorizonEvaluation,
    MultiHorizonFitRun,
    MultiHorizonForecast,
    MultiHorizonLineageAudit,
    SharedPointForecast,
)
from afre.multihorizon.consistency import consistency_for
from afre.multihorizon.definitions import MultiHorizonModelSpec
from afre.multihorizon.dependence import covariance_for
from afre.multihorizon.evaluation import evaluation_for
from afre.multihorizon.forecasts import bundle_for, shared_point_for
from afre.multihorizon.lineage import lineage_audit
from afre.multihorizon.repository import MultiHorizonRepository
from afre.multihorizon.schema import Denominator
from afre.multihorizon.training import fit_for
from afre.schema import require
from afre.statistical_models.artifacts import PointForecast


class MultiHorizonEngine:
    def __init__(self, repository: MultiHorizonRepository) -> None:
        self.repository = repository

    def fit(
        self,
        spec: MultiHorizonModelSpec,
        fit_started_ns: int,
        fit_completed_ns: int,
        available_ns: int,
        snapshot_hook: Callable[[], None] | None = None,
    ) -> MultiHorizonFitRun:
        repo = self.repository
        with repo.read_snapshot(), repo.validation_cache():
            if snapshot_hook:
                snapshot_hook()
            run, state = fit_for(repo, spec, fit_started_ns, fit_completed_ns, available_ns)
        with repo.transaction(), repo.validation_cache():
            repo.put(spec.horizon_set)
            repo.put(spec)
            if state:
                repo.put(state)
            repo.put(run)
        return run

    def fit_dependence(
        self,
        fit_run_id: str,
        cutoff_ns: int,
        available_ns: int,
        denominator: Denominator = Denominator.SAMPLE,
        tolerance: float = 1e-12,
    ) -> CovarianceArtifact:
        repo = self.repository
        with repo.read_snapshot(), repo.validation_cache():
            run = repo.resolve(MultiHorizonFitRun, fit_run_id)
            result = covariance_for(repo, run, cutoff_ns, available_ns, denominator, tolerance)
        with repo.transaction(), repo.validation_cache():
            repo.put(result)
        return result

    def predict_shared(
        self, fit_run_id: str, scaffold_forecast_id: str, computed_ns: int
    ) -> SharedPointForecast:
        repo = self.repository
        with repo.read_snapshot(), repo.validation_cache():
            result = shared_point_for(
                repo,
                repo.resolve(MultiHorizonFitRun, fit_run_id),
                repo.resolve(PointForecast, scaffold_forecast_id),
                computed_ns,
            )
        with repo.transaction(), repo.validation_cache():
            repo.put(result)
        return result

    def build_bundle(
        self,
        fit_run_id: str,
        origin: ForecastOrigin,
        entries: tuple[HorizonForecastEntry, ...],
        computed_ns: int,
        covariance_id: str | None = None,
        snapshot_hook: Callable[[], None] | None = None,
    ) -> MultiHorizonForecast:
        repo = self.repository
        with repo.read_snapshot(), repo.validation_cache():
            if snapshot_hook:
                snapshot_hook()
            result = bundle_for(
                repo,
                repo.resolve(MultiHorizonFitRun, fit_run_id),
                origin,
                entries,
                computed_ns,
                covariance_id,
            )
        with repo.transaction(), repo.validation_cache():
            repo.put(result)
        return result

    def evaluate(
        self,
        bundle_ids: tuple[str, ...],
        cutoff_ns: int,
        available_ns: int,
        test_identities: tuple[str | None, ...] | None = None,
    ) -> MultiHorizonEvaluation:
        repo = self.repository
        with repo.transaction(), repo.validation_cache():
            require(
                0 < len(bundle_ids) <= repo.multihorizon_bounds.forecasts,
                "evaluation count bound",
            )
            first = repo.resolve(MultiHorizonForecast, bundle_ids[0])
            result = evaluation_for(
                repo,
                bundle_ids,
                cutoff_ns,
                available_ns,
                test_identities or tuple(None for _ in first.entries),
            )
            repo.put(result)
        return result

    def consistency_audit(self, bundle_id: str) -> ConsistencyAudit:
        with self.repository.transaction(), self.repository.validation_cache():
            result = consistency_for(
                self.repository, self.repository.resolve(MultiHorizonForecast, bundle_id)
            )
            self.repository.put(result)
            return result

    def lineage_audit(self, root_id: str) -> MultiHorizonLineageAudit:
        with self.repository.transaction(), self.repository.validation_cache():
            result = lineage_audit(self.repository, root_id)
            self.repository.put(result)
            return result

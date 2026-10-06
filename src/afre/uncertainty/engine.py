"""Frozen reads and atomic publication; no fitting during forecast application."""

from collections.abc import Callable

from afre.research_datasets.schema import Partition
from afre.schema import Artifact, require
from afre.uncertainty.artifacts import (
    ForecastUncertaintyDecomposition,
    ParameterCovariance,
    UncertaintyAudit,
)
from afre.uncertainty.definitions import ParameterUncertaintySpec, UncertaintySpec
from afre.uncertainty.evaluation_artifacts import (
    UncertaintyComparison,
    UncertaintyDrift,
    UncertaintyEvaluation,
    UncertaintyEvaluationSpec,
)
from afre.uncertainty.repository import UncertaintyRepository


class UncertaintyEngine:
    def __init__(self, repository: UncertaintyRepository) -> None:
        self.repository = repository

    def _publish(self, values: tuple[Artifact, ...]) -> None:
        with self.repository.transaction(), self.repository.validation_cache():
            for value in values:
                self.repository.put(value)

    def fit_covariance(
        self,
        spec: ParameterUncertaintySpec,
        computed_ns: int,
        snapshot_hook: Callable[[], None] | None = None,
    ) -> ParameterCovariance:
        from afre.uncertainty.parameter import covariance_for

        self._publish((spec,))
        with self.repository.read_snapshot(), self.repository.validation_cache():
            model = self.repository.get_any(spec.model_id)
            if snapshot_hook:
                snapshot_hook()
            require(model.fingerprint == spec.model_id, "exact covariance model")
            result = covariance_for(self.repository, spec, computed_ns)
        self._publish((result,))
        return result

    def decompose(
        self,
        spec: UncertaintySpec,
        computed_ns: int,
        snapshot_hook: Callable[[], None] | None = None,
    ) -> ForecastUncertaintyDecomposition:
        from afre.uncertainty.decomposition import decomposition_for

        with self.repository.feature_only():
            self._publish((*spec.requests, spec.target, spec))
            with self.repository.read_snapshot(), self.repository.validation_cache():
                self.repository.get_any(spec.forecast_id)
                if snapshot_hook:
                    snapshot_hook()
                result, interval = decomposition_for(self.repository, spec, computed_ns)
            self._publish((interval, *result.components, result))
        return result

    def evaluate(
        self,
        ids: tuple[str, ...],
        policy: UncertaintyEvaluationSpec,
        cutoff_ns: int,
        available_ns: int,
        test_identity: str | None = None,
        snapshot_hook: Callable[[], None] | None = None,
    ) -> UncertaintyEvaluation:
        from afre.statistical_models.evaluation import test_record
        from afre.uncertainty.evaluation import evaluation_for

        require(bool(ids), "uncertainty evaluation requires decompositions")
        self._publish((policy,))
        with self.repository.read_snapshot(), self.repository.validation_cache():
            first = self.repository.resolve(ForecastUncertaintyDecomposition, ids[0])
            if snapshot_hook:
                snapshot_hook()
            seal = None
            if first.partition is Partition.TEST:
                require(test_identity is not None, "explicit uncertainty TEST identity")
                seal = test_record(
                    self.repository,
                    first.fold_id,
                    test_identity or "",
                    "uncertainty-exact-matched-assessment",
                    cutoff_ns,
                )
            result = evaluation_for(self.repository, ids, policy, cutoff_ns, available_ns, seal)
        self._publish((*((seal,) if seal else ()), *result.pairs, result))
        return result

    def compare(self, left_id: str, right_id: str, available_ns: int) -> UncertaintyComparison:
        from afre.uncertainty.evaluation import comparison_for

        with self.repository.read_snapshot(), self.repository.validation_cache():
            result = comparison_for(self.repository, left_id, right_id, available_ns)
        self._publish((result,))
        return result

    def drift(self, evaluation_ids: tuple[str, ...], available_ns: int) -> UncertaintyDrift:
        from afre.uncertainty.diagnostics import drift_for

        with self.repository.read_snapshot(), self.repository.validation_cache():
            result = drift_for(self.repository, evaluation_ids, available_ns)
        self._publish((result,))
        return result

    def audit_lineage(self, root_id: str) -> UncertaintyAudit:
        from afre.uncertainty.lineage import lineage_for

        with self.repository.read_snapshot(), self.repository.validation_cache():
            result = lineage_for(self.repository, root_id)
        self._publish((result,))
        return result

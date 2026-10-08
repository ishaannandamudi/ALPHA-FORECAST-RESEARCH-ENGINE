"""Atomic descriptive publication over frozen snapshots; no model mutation APIs."""

from collections.abc import Callable

from afre.forecast import ForecastOrigin
from afre.invariance.artifacts import (
    EnvironmentMembership,
    EnvironmentMetric,
    FeatureShiftDiagnostic,
    ForecastDegradation,
    ModelStabilityDiagnostic,
    NeutralEnvironmentLabel,
    PredictionStabilityDiagnostic,
    StabilityAudit,
    StabilityComparison,
    StabilityTrend,
)
from afre.invariance.definitions import EnvironmentSet, StabilityAnalysisSpec
from afre.invariance.repository import InvarianceRepository
from afre.research_datasets.schema import Partition
from afre.schema import Artifact, require


class InvarianceEngine:
    def __init__(self, repository: InvarianceRepository) -> None:
        self.repository = repository

    def _publish(self, values: tuple[Artifact, ...]) -> None:
        with self.repository.transaction(), self.repository.validation_cache():
            for v in values:
                self.repository.put(v)

    def declare(self, value: EnvironmentSet) -> EnvironmentSet:
        bases = tuple(d for d in value.definitions if not d.component_ids)
        compounds = tuple(d for d in value.definitions if d.component_ids)
        self._publish((value.definitions[0].target, *bases, *compounds, value))
        return value

    def publish_label(self, label: NeutralEnvironmentLabel) -> NeutralEnvironmentLabel:
        self._publish(
            (
                label.source,
                *(
                    (label.clocks.historical_delivery,)
                    if label.clocks.historical_delivery
                    else ()
                ),
                label,
            )
        )
        return label

    def bind(
        self,
        environment_id: str,
        sample_id: str,
        source_ids: tuple[str, ...] = (),
        mapping_ids: tuple[str, ...] = (),
        constructed_ns: int = 0,
        snapshot_hook: Callable[[], None] | None = None,
    ) -> EnvironmentMembership:
        from afre.invariance.environments import membership_for

        with (
            self.repository.feature_only(),
            self.repository.read_snapshot(),
            self.repository.validation_cache(),
        ):
            self.repository.get_any(sample_id)
            if snapshot_hook:
                snapshot_hook()
            value = membership_for(
                self.repository,
                environment_id,
                sample_id,
                source_ids,
                mapping_ids,
                constructed_ns,
            )
        self._publish((value,))
        return value

    def metadata(self, membership_id: str, origin: ForecastOrigin) -> EnvironmentMembership:
        with (
            self.repository.feature_only(),
            self.repository.read_snapshot(),
            self.repository.validation_cache(),
        ):
            m = self.repository.resolve(EnvironmentMembership, membership_id)
            require(
                m.origin == origin and m.available_ns <= origin.availability_cutoff_ns,
                "membership not actually constructed/available by requested origin",
            )
            return m

    def register(self, spec: StabilityAnalysisSpec) -> StabilityAnalysisSpec:
        self._publish((spec,))
        return spec

    def evaluate(
        self,
        spec_id: str,
        membership_ids: tuple[str, ...],
        cutoff_ns: int,
        available_ns: int,
        comparison_environment_ids: tuple[str, ...] | None = None,
        test_identity: str | None = None,
        snapshot_hook: Callable[[], None] | None = None,
    ) -> tuple[EnvironmentMetric, ...]:
        from afre.invariance.evaluation import metric_for
        from afre.statistical_models.evaluation import test_record

        with self.repository.read_snapshot(), self.repository.validation_cache():
            spec = self.repository.resolve(StabilityAnalysisSpec, spec_id)
            envs = self.repository.resolve(EnvironmentSet, spec.environment_set_id)
            if snapshot_hook:
                snapshot_hook()
            env_ids = comparison_environment_ids or tuple(
                d.fingerprint for d in envs.definitions
            )
            seal = None
            if any(
                m.partition is Partition.TEST and m.sample_id in spec.sample_ids
                for m in self.repository.fold_memberships(spec.fold_id)
            ):
                require(
                    test_identity is not None, "explicit invariance TEST assessment identity"
                )
                seal = test_record(
                    self.repository,
                    spec.fold_id,
                    test_identity or "",
                    "invariance-frozen-declared-assessment",
                    cutoff_ns,
                )
            values = tuple(
                metric_for(
                    self.repository,
                    spec_id,
                    e,
                    name,
                    membership_ids,
                    env_ids,
                    cutoff_ns,
                    available_ns,
                    seal,
                )
                for e in sorted(env_ids)
                for name in spec.metrics
            )
        self._publish((*((seal,) if seal else ()), *values))
        return values

    def compare(
        self, left_id: str, right_id: str, available_ns: int, cross_model: bool = False
    ) -> StabilityComparison:
        from afre.invariance.comparisons import comparison_for

        with self.repository.read_snapshot(), self.repository.validation_cache():
            value = comparison_for(
                self.repository, left_id, right_id, available_ns, cross_model
            )
        self._publish((value,))
        return value

    def degradation(self, comparison_id: str) -> ForecastDegradation:
        from afre.invariance.comparisons import degradation_for

        with self.repository.read_snapshot(), self.repository.validation_cache():
            value = degradation_for(self.repository, comparison_id)
        self._publish((value,))
        return value

    def shift(
        self,
        spec_id: str,
        feature_reference_id: str,
        environment_ids: tuple[str, str],
        membership_ids: tuple[str, ...],
        observation_ids: tuple[str, ...],
        cutoff_ns: int,
        available_ns: int,
    ) -> FeatureShiftDiagnostic:
        from afre.invariance.distributions import shift_for

        with (
            self.repository.feature_only(),
            self.repository.read_snapshot(),
            self.repository.validation_cache(),
        ):
            value = shift_for(
                self.repository,
                spec_id,
                feature_reference_id,
                environment_ids,
                membership_ids,
                observation_ids,
                cutoff_ns,
                available_ns,
            )
        self._publish((value,))
        return value

    def models(
        self,
        spec_id: str,
        assignments: tuple[tuple[str, str], ...],
        cutoff_ns: int,
        available_ns: int,
        raw_scale: bool = False,
    ) -> ModelStabilityDiagnostic:
        from afre.invariance.diagnostics import model_stability_for

        with self.repository.read_snapshot(), self.repository.validation_cache():
            value = model_stability_for(
                self.repository, spec_id, assignments, raw_scale, cutoff_ns, available_ns
            )
        self._publish((value,))
        return value

    def predictions(
        self,
        left_spec_id: str,
        right_spec_id: str,
        environment_id: str,
        membership_ids: tuple[str, ...],
        cutoff_ns: int,
        available_ns: int,
    ) -> PredictionStabilityDiagnostic:
        from afre.invariance.rankings import predictions_for

        with self.repository.read_snapshot(), self.repository.validation_cache():
            value = predictions_for(
                self.repository,
                left_spec_id,
                right_spec_id,
                environment_id,
                membership_ids,
                cutoff_ns,
                available_ns,
            )
        self._publish((value,))
        return value

    def trend(self, metric_ids: tuple[str, ...], available_ns: int) -> StabilityTrend:
        from afre.invariance.comparisons import trend_for

        with self.repository.read_snapshot(), self.repository.validation_cache():
            value = trend_for(self.repository, metric_ids, available_ns)
        self._publish((value,))
        return value

    def audit(self, root_id: str) -> StabilityAudit:
        from afre.invariance.lineage import audit_for

        with self.repository.read_snapshot(), self.repository.validation_cache():
            value = audit_for(self.repository, root_id)
        self._publish((value,))
        return value

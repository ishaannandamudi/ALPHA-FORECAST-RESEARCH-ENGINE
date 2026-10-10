"""Frozen read snapshots, immutable evidence publication and descriptive history."""

from collections.abc import Callable
from contextlib import nullcontext

from afre.health.artifacts import (
    HealthDecayTrend,
    HealthObservation,
    ModelHealthSnapshot,
)
from afre.health.definitions import HealthRule, HealthSpec, MonitoredArtifactReference
from afre.health.evaluation import LATER_DIAGNOSTICS, metric_for, snapshot_for
from afre.health.inputs import input_for
from afre.health.lineage import HealthAudit, audit_for
from afre.health.repository import HealthRepository
from afre.health.sources import observation_for, reference_for
from afre.health.trends import trend_for
from afre.schema import Artifact, require


class HealthEngine:
    def __init__(self, repository: HealthRepository) -> None:
        self.repository = repository

    def _publish(self, values: tuple[Artifact, ...]) -> None:
        with self.repository.transaction(), self.repository.validation_cache():
            for value in values:
                self.repository.put(value)

    def monitor(
        self, artifact_id: str, anchor_output_id: str | None = None
    ) -> MonitoredArtifactReference:
        with self.repository.read_snapshot(), self.repository.validation_cache():
            result = reference_for(self.repository, artifact_id, anchor_output_id)
        self._publish((result,))
        return result

    def observe(
        self, reference_id: str, source_id: str, constructed_ns: int
    ) -> HealthObservation:
        with self.repository.read_snapshot(), self.repository.validation_cache():
            ref = self.repository.resolve(MonitoredArtifactReference, reference_id)
            result = observation_for(self.repository, ref, source_id, constructed_ns)
        self._publish((result,))
        return result

    def input(
        self, reference_id: str, join_id: str, sample_id: str, constructed_ns: int
    ) -> HealthObservation:
        with self.repository.feature_only():
            with self.repository.read_snapshot(), self.repository.validation_cache():
                ref = self.repository.resolve(MonitoredArtifactReference, reference_id)
                result = input_for(self.repository, ref, join_id, sample_id, constructed_ns)
            self._publish((result,))
        return result

    def declare(self, spec: HealthSpec, rules: tuple[HealthRule, ...] = ()) -> HealthSpec:
        require(
            {r.fingerprint for r in rules} <= {i for _, i in spec.rule_bindings},
            "health rules explicitly bound to spec",
        )
        self._publish(
            (
                spec.bounds,
                spec.reference_window,
                spec.current_window,
                *spec.requests,
                *rules,
                spec,
            )
        )
        return spec

    def evaluate(
        self, spec_id: str, available_ns: int, snapshot_hook: Callable[[], None] | None = None
    ) -> ModelHealthSnapshot:
        raw = self.repository.get(HealthSpec, spec_id)
        target_free = all(r.kind not in LATER_DIAGNOSTICS for r in raw.requests)
        with self.repository.feature_only() if target_free else nullcontext():
            with self.repository.read_snapshot(), self.repository.validation_cache():
                spec = self.repository.resolve(HealthSpec, spec_id)
                if snapshot_hook:
                    snapshot_hook()
                metrics = tuple(
                    metric_for(self.repository, spec, r, available_ns) for r in spec.requests
                )
                result = snapshot_for(spec, metrics, available_ns)
            self._publish((*metrics, result))
        return result

    def history(self, reference_id: str) -> tuple[ModelHealthSnapshot, ...]:
        with self.repository.read_snapshot(), self.repository.validation_cache():
            ids = tuple(
                r[0]
                for r in self.repository._connection.execute(
                    (
                        "SELECT fingerprint FROM hlt_records WHERE "
                        "kind='ModelHealthSnapshot' AND reference_id=? ORDER BY "
                        "cutoff_ns,available_ns,fingerprint"
                    ),
                    (reference_id,),
                )
            )
            require(len(ids) <= self.repository.health_bounds.artifacts, "health history bound")
            return tuple(self.repository.resolve(ModelHealthSnapshot, i) for i in ids)

    def trend(self, metric_ids: tuple[str, ...], available_ns: int) -> HealthDecayTrend:
        with self.repository.read_snapshot(), self.repository.validation_cache():
            result = trend_for(self.repository, metric_ids, available_ns)
        self._publish((result,))
        return result

    def audit(self, root_id: str) -> HealthAudit:
        with self.repository.read_snapshot(), self.repository.validation_cache():
            result = audit_for(self.repository, root_id)
        self._publish((result,))
        return result

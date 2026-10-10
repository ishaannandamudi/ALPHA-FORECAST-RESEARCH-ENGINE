"""Frozen fusion operations with target-free application and no candidate selector."""

from collections.abc import Callable

from afre.fusion.accounting import FusionTrialPool, register_pool
from afre.fusion.application import forecast_for
from afre.fusion.artifacts import (
    FrozenFusionTestChoice,
    FusedForecast,
    FusionArtifact,
    FusionObservation,
)
from afre.fusion.compatibility import admit_spec
from afre.fusion.definitions import FusionSourceReference, FusionSpec
from afre.fusion.diagnostics import DiversityMatrix, FusionComparison
from afre.fusion.diversity import diversity_for
from afre.fusion.evaluation import comparison_for
from afre.fusion.external import ExternalFusionDefinition, ExternalFusionOutput
from afre.fusion.learned import fit_for
from afre.fusion.lineage import FusionAudit, audit_for
from afre.fusion.repository import FusionRepository
from afre.fusion.sources import observation_for, reference_for
from afre.research_datasets.schema import Partition
from afre.schema import Artifact, require
from afre.statistical_models.evaluation import test_record


class FusionEngine:
    def __init__(self, repository: FusionRepository) -> None:
        self.repository = repository

    def _publish(self, values: tuple[Artifact, ...]) -> None:
        with self.repository.transaction(), self.repository.validation_cache():
            for value in values:
                self.repository.put(value)

    def external(
        self, definition: ExternalFusionDefinition, outputs: tuple[ExternalFusionOutput, ...]
    ) -> None:
        require(
            len(outputs) <= self.repository.fusion_bounds.prediction_rows,
            "external output batch bound",
        )
        require(
            all(o.definition_id == definition.fingerprint for o in outputs),
            "external exact definition",
        )
        with self.repository.feature_only():
            self._publish((definition.source, definition.target, definition, *outputs))

    def source(self, output_id: str, kind: object = None) -> FusionSourceReference:
        from afre.fusion.schema import FusionKind

        require(kind is None or isinstance(kind, FusionKind), "typed explicit source bridge")
        assert kind is None or isinstance(kind, FusionKind)
        with (
            self.repository.feature_only(),
            self.repository.read_snapshot(),
            self.repository.validation_cache(),
        ):
            result = reference_for(self.repository, output_id, kind)
        with self.repository.feature_only():
            self._publish((result,))
        return result

    def observe(
        self, reference_id: str, output_id: str, approved_attestors: tuple[str, ...] = ()
    ) -> FusionObservation:
        with (
            self.repository.feature_only(),
            self.repository.read_snapshot(),
            self.repository.validation_cache(),
        ):
            ref = self.repository.resolve(FusionSourceReference, reference_id)
            result = observation_for(self.repository, ref, output_id, approved_attestors)
        with self.repository.feature_only():
            self._publish((result,))
        return result

    def declare(self, spec: FusionSpec) -> FusionSpec:
        with self.repository.feature_only():
            admit_spec(self.repository, spec)
            self._publish((spec.bounds, spec))
        return spec

    def fit(
        self,
        spec: FusionSpec,
        cutoff_ns: int,
        computed_ns: int,
        available_ns: int,
        bindings: tuple[tuple[str, tuple[str, ...]], ...] = (),
        snapshot_hook: Callable[[], None] | None = None,
    ) -> FusionArtifact:
        self.declare(spec)
        with self.repository.read_snapshot(), self.repository.validation_cache():
            self.repository.resolve(FusionSpec, spec.fingerprint)
            if snapshot_hook:
                snapshot_hook()
            result = fit_for(
                self.repository, spec, bindings, cutoff_ns, computed_ns, available_ns
            )
        self._publish((result,))
        return result

    def apply(
        self,
        artifact_id: str,
        sample_id: str,
        observation_ids: tuple[str, ...],
        computed_ns: int,
        fallback_id: str | None = None,
        snapshot_hook: Callable[[], None] | None = None,
    ) -> FusedForecast:
        with self.repository.feature_only():
            with self.repository.read_snapshot(), self.repository.validation_cache():
                self.repository.resolve(FusionArtifact, artifact_id)
                if snapshot_hook:
                    snapshot_hook()
                result = forecast_for(
                    self.repository,
                    artifact_id,
                    sample_id,
                    observation_ids,
                    computed_ns,
                    fallback_id,
                )
            self._publish((result,))
        return result

    def diversity(
        self,
        source_ids: tuple[str, ...],
        observation_ids: tuple[str, ...],
        available_ns: int,
        cutoff_ns: int | None = None,
    ) -> DiversityMatrix:
        with self.repository.read_snapshot(), self.repository.validation_cache():
            result = diversity_for(
                self.repository, source_ids, observation_ids, available_ns, cutoff_ns
            )
        self._publish((result,))
        return result

    def trial_pool(
        self,
        bindings: tuple[tuple[str, tuple[str, ...]], ...],
        failure_anchor_ids: tuple[str, ...] = (),
    ) -> FusionTrialPool:
        from afre.fusion.snapshots import frozen_copy, publish_stage

        stage = frozen_copy(self.repository)
        try:
            result = register_pool(stage, bindings, failure_anchor_ids)
            with stage.transaction(), stage.validation_cache():
                stage.put(result)
            publish_stage(self.repository, stage)
            return result
        finally:
            stage.close()

    def choose_test(
        self, artifact_id: str, declared_ns: int, rationale: str
    ) -> FrozenFusionTestChoice:
        result = FrozenFusionTestChoice(artifact_id, declared_ns, rationale)
        self._publish((result,))
        return result

    def evaluate(
        self,
        ids: tuple[str, ...],
        pool_id: str,
        cutoff_ns: int,
        available_ns: int,
        choice_id: str | None = None,
        test_identity: str | None = None,
        snapshot_hook: Callable[[], None] | None = None,
    ) -> FusionComparison:
        seal = None
        with self.repository.read_snapshot(), self.repository.validation_cache():
            require(bool(ids), "evaluation requires frozen forecasts")
            first = self.repository.resolve(FusedForecast, ids[0])
            artifact = self.repository.resolve(FusionArtifact, first.artifact_id)
            pool = self.repository.resolve(FusionTrialPool, pool_id)
            require(
                artifact.spec_id in pool.spec_ids
                and artifact.spec_id not in pool.failed_spec_ids,
                "fusion evaluation requires prior full AFRE19 opportunity accounting",
            )
            if snapshot_hook:
                snapshot_hook()
            if first.partition is Partition.TEST:
                require(
                    choice_id is not None and test_identity is not None,
                    "TEST frozen choice and explicit access identity required",
                )
                assert test_identity is not None
                seal = test_record(
                    self.repository,
                    first.fold_id,
                    test_identity,
                    "frozen-fusion-final-heldout-evaluation",
                    cutoff_ns,
                )
            else:
                require(
                    choice_id is None and test_identity is None, "VALIDATION no TEST authority"
                )
        if seal:
            self._publish((seal,))
        with self.repository.read_snapshot(), self.repository.validation_cache():
            result = comparison_for(
                self.repository,
                ids,
                cutoff_ns,
                available_ns,
                choice_id,
                seal.fingerprint if seal else None,
                pool_id,
            )
        self._publish((result,))
        return result

    def audit(self, root_id: str) -> FusionAudit:
        with self.repository.read_snapshot(), self.repository.validation_cache():
            result = audit_for(self.repository, root_id)
        self._publish((result,))
        return result

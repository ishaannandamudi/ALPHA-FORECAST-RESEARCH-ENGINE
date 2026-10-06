"""Frozen snapshot computations followed by atomic immutable publication."""

from collections.abc import Callable

from afre.cross_sectional.definitions import CrossSectionSpec
from afre.forecast import ForecastOrigin
from afre.nonlinear.artifacts import (
    FittedTransformArtifact,
    InteractionMatrix,
    InteractionStability,
    InteractionValue,
    NonlinearAudit,
    NonlinearCalibrationAssessment,
    NonlinearEvaluation,
    NonlinearForecast,
    NonlinearInput,
    NonlinearModelArtifact,
    NonlinearRankEvaluation,
    NonlinearRanking,
    ScalarInput,
)
from afre.nonlinear.definitions import InteractionDefinition, NonlinearModelSpec
from afre.nonlinear.repository import NonlinearRepository
from afre.probabilistic.definitions import ThresholdRequest
from afre.research_datasets.schema import Partition
from afre.schema import Artifact, require


class NonlinearEngine:
    def __init__(self, repository: NonlinearRepository) -> None:
        self.repository = repository

    def _publish(self, values: tuple[Artifact, ...]) -> None:
        with self.repository.transaction(), self.repository.validation_cache():
            for value in values:
                self.repository.put(value)

    def publish_spec(self, spec: NonlinearModelSpec) -> str:
        self._publish(
            (
                *spec.features,
                *spec.interaction_set.definitions,
                spec.target,
                spec.interaction_set,
                spec,
            )
        )
        return spec.fingerprint

    def scalar(
        self,
        source_id: str,
        origin: ForecastOrigin,
        selector: str = "value",
        approved_attestors: tuple[str, ...] = (),
    ) -> ScalarInput:
        from afre.nonlinear.sources import scalar_for

        with self.repository.read_snapshot():
            result = scalar_for(
                self.repository, source_id, origin, selector, approved_attestors
            )
        self._publish((result.definition, result))
        return result

    def input(self, sample_id: str, scalar_ids: tuple[str, ...]) -> NonlinearInput:
        from afre.nonlinear.sources import input_for

        with self.repository.read_snapshot():
            result = input_for(self.repository, sample_id, scalar_ids)
        self._publish((result,))
        return result

    def apply(
        self,
        definition: InteractionDefinition,
        input_id: str,
        computed_ns: int,
        transform_id: str | None = None,
    ) -> InteractionValue:
        from afre.nonlinear.interactions import interaction_for

        with self.repository.read_snapshot():
            inputs = self.repository.resolve(NonlinearInput, input_id)
            state = (
                self.repository.resolve(FittedTransformArtifact, transform_id)
                if transform_id
                else None
            )
            result = interaction_for(self.repository, definition, inputs, computed_ns, state)
        self._publish((*definition.inputs, definition, result))
        return result

    def fit_transform(
        self,
        spec: NonlinearModelSpec,
        definition: InteractionDefinition,
        input_ids: tuple[str, ...],
        started_ns: int,
        completed_ns: int,
        available_ns: int,
        snapshot_hook: Callable[[], None] | None = None,
    ) -> FittedTransformArtifact:
        from afre.nonlinear.matrix import fit_transform

        self.publish_spec(spec)
        with self.repository.read_snapshot(), self.repository.validation_cache():
            self.repository.resolve(NonlinearModelSpec, spec.fingerprint)
            if snapshot_hook:
                snapshot_hook()
            result = fit_transform(
                self.repository,
                spec,
                definition,
                input_ids,
                started_ns,
                completed_ns,
                available_ns,
            )
        self._publish((result,))
        return result

    def matrix(
        self,
        spec: NonlinearModelSpec,
        input_ids: tuple[str, ...],
        transform_ids: tuple[str, ...],
        computed_ns: int,
        snapshot_hook: Callable[[], None] | None = None,
    ) -> InteractionMatrix:
        from afre.nonlinear.matrix import matrix_for

        self.publish_spec(spec)
        with self.repository.read_snapshot(), self.repository.validation_cache():
            self.repository.resolve(NonlinearModelSpec, spec.fingerprint)
            if snapshot_hook:
                snapshot_hook()
            states = tuple(
                self.repository.resolve(FittedTransformArtifact, i) for i in transform_ids
            )
            matrix, interactions = matrix_for(
                self.repository, spec, input_ids, states, computed_ns
            )
        self._publish((*interactions, *matrix.rows, matrix))
        return matrix

    def fit(
        self,
        spec: NonlinearModelSpec,
        matrix_id: str,
        started_ns: int,
        completed_ns: int,
        available_ns: int,
        snapshot_hook: Callable[[], None] | None = None,
    ) -> NonlinearModelArtifact:
        from afre.nonlinear.fitting import fit_model

        self.publish_spec(spec)
        with self.repository.read_snapshot(), self.repository.validation_cache():
            matrix = self.repository.resolve(InteractionMatrix, matrix_id)
            if snapshot_hook:
                snapshot_hook()
            self.repository._validate_links(matrix)
            result = fit_model(
                spec,
                matrix,
                started_ns,
                completed_ns,
                available_ns,
                self.repository.nonlinear_bounds,
            )
        self._publish((*result.nodes, result))
        return result

    def predict(
        self,
        model_id: str,
        input_id: str,
        computed_ns: int,
        base_probability_id: str | None = None,
        snapshot_hook: Callable[[], None] | None = None,
    ) -> NonlinearForecast:
        from afre.nonlinear.predictions import forecast_for

        with self.repository.read_snapshot(), self.repository.validation_cache():
            model = self.repository.resolve(NonlinearModelArtifact, model_id)
            inputs = self.repository.resolve(NonlinearInput, input_id)
            if snapshot_hook:
                snapshot_hook()
            result, interactions = forecast_for(
                self.repository, model, inputs, computed_ns, base_probability_id
            )
        self._publish(
            (
                *interactions,
                *result.path,
                *((result.probability,) if result.probability else ()),
                result,
            )
        )
        return result

    def evaluate(
        self,
        ids: tuple[str, ...],
        cutoff_ns: int,
        available_ns: int,
        baselines: tuple[tuple[str, str], ...] = (),
        test_identity: str | None = None,
        thresholds: tuple[ThresholdRequest, ...] = (),
        snapshot_hook: Callable[[], None] | None = None,
    ) -> NonlinearEvaluation:
        from afre.nonlinear.evaluation import evaluation_for
        from afre.statistical_models.evaluation import test_record

        require(bool(ids), "evaluation requires forecasts")
        with self.repository.read_snapshot(), self.repository.validation_cache():
            first = self.repository.resolve(NonlinearForecast, ids[0])
            spec = self.repository.resolve(NonlinearModelSpec, first.spec_id)
            if snapshot_hook:
                snapshot_hook()
            seal = None
            if first.partition is Partition.TEST:
                require(test_identity is not None, "explicit nonlinear TEST identity")
                seal = test_record(
                    self.repository,
                    spec.fold_id,
                    test_identity or "",
                    "nonlinear-exact-matched-comparison",
                    cutoff_ns,
                )
            result = evaluation_for(
                self.repository, ids, cutoff_ns, available_ns, baselines, seal, thresholds
            )
        self._publish((*((seal,) if seal else ()), *result.pairs, result))
        return result

    def stability(self, model_ids: tuple[str, ...], available_ns: int) -> InteractionStability:
        from afre.nonlinear.stability import stability_for

        with self.repository.read_snapshot(), self.repository.validation_cache():
            result = stability_for(self.repository, model_ids, available_ns)
        self._publish((result,))
        return result

    def assess_calibration(
        self,
        forecast_id: str,
        ids: tuple[str, ...],
        cutoff_ns: int,
        minimum_count: int = 2,
        proposed_state_id: str | None = None,
    ) -> NonlinearCalibrationAssessment:
        from afre.nonlinear.calibration import assessment_for

        with self.repository.read_snapshot(), self.repository.validation_cache():
            result = assessment_for(
                self.repository, forecast_id, ids, cutoff_ns, minimum_count, proposed_state_id
            )
        self._publish((result,))
        return result

    def rank(
        self,
        template: CrossSectionSpec,
        ids: tuple[str, ...],
        groups: tuple[tuple[str, str], ...] = (),
    ) -> NonlinearRanking:
        from afre.cross_sectional.engine import CrossSectionEngine
        from afre.nonlinear.cross_sectional import nonlinear_signal, ranking_for, ranking_spec

        require(
            0 < len(ids) <= self.repository.nonlinear_bounds.forecasts,
            "nonlinear ranking request bound",
        )
        with self.repository.read_snapshot(), self.repository.validation_cache():
            forecasts = tuple(
                self.repository.resolve(NonlinearForecast, i) for i in sorted(ids)
            )
            spec = ranking_spec(template, forecasts[0])
            signals = tuple(nonlinear_signal(f) for f in forecasts)
        engine = CrossSectionEngine(self.repository)
        for signal in signals:
            engine.publish_external(signal)
        rank = engine.build_ranking(
            spec, tuple((s.security.fingerprint, s.fingerprint) for s in signals), groups
        )
        with self.repository.read_snapshot():
            result = ranking_for(self.repository, rank.fingerprint, ids)
        self._publish((result,))
        return result

    def evaluate_rank(
        self,
        ranking_id: str,
        cutoff_ns: int,
        available_ns: int,
        test_identity: str | None = None,
    ) -> NonlinearRankEvaluation:
        from afre.cross_sectional.artifacts import CrossSectionRanking
        from afre.cross_sectional.engine import CrossSectionEngine
        from afre.cross_sectional.schema import TruthPolicy

        with self.repository.read_snapshot():
            rank = self.repository.resolve(NonlinearRanking, ranking_id)
        matched = self.evaluate(
            rank.forecast_ids, cutoff_ns, available_ns, test_identity=test_identity
        )
        with self.repository.read_snapshot():
            underlying = self.repository.resolve(CrossSectionRanking, rank.ranking_id)
            targets = {
                self.repository.resolve(
                    NonlinearForecast, p.forecast_id
                ).security.fingerprint: p.target_id
                for p in matched.pairs
            }
            grid = tuple(
                (e.security.fingerprint, targets.get(e.security.fingerprint))
                for e in underlying.entries
            )
        cross = CrossSectionEngine(self.repository).evaluate(
            rank.ranking_id,
            grid,
            cutoff_ns,
            available_ns,
            policy=TruthPolicy.AVAILABLE_INTERSECTION,
        )
        result = NonlinearRankEvaluation(
            rank.fingerprint, matched.fingerprint, cross.fingerprint
        )
        self._publish((result,))
        return result

    def audit_lineage(self, root_id: str) -> NonlinearAudit:
        from afre.nonlinear.lineage import lineage_for

        with self.repository.read_snapshot(), self.repository.validation_cache():
            result = lineage_for(self.repository, root_id)
        self._publish((result,))
        return result

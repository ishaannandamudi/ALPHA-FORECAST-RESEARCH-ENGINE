"""Frozen read computation and atomic publication of immutable sequence artifacts."""

from collections.abc import Callable

from afre.cross_sectional.definitions import CrossSectionSpec
from afre.forecast import ForecastOrigin
from afre.probabilistic.definitions import ThresholdRequest
from afre.research_datasets.schema import Partition
from afre.schema import Artifact, require
from afre.sequence.artifacts import (
    SequenceAudit,
    SequenceCalibrationAssessment,
    SequenceCoverage,
    SequenceDataset,
    SequenceEvaluation,
    SequenceForecast,
    SequenceModelArtifact,
    SequenceObservation,
    SequenceRankEvaluation,
    SequenceRanking,
    SequenceSnapshot,
    SequenceStability,
    SequenceTransformArtifact,
)
from afre.sequence.definitions import (
    SequenceFeatureDefinition,
    SequenceModelSpec,
    SequenceWindowSpec,
)
from afre.sequence.repository import SequenceRepository


class SequenceEngine:
    def __init__(self, repository: SequenceRepository) -> None:
        self.repository = repository

    def _publish(self, values: tuple[Artifact, ...]) -> None:
        with self.repository.transaction(), self.repository.validation_cache():
            for value in values:
                self.repository.put(value)

    def publish_spec(self, spec: SequenceModelSpec) -> str:
        self._publish((*spec.features, spec.window, spec.target, spec))
        return spec.fingerprint

    def observation(
        self, feature: SequenceFeatureDefinition, source_id: str
    ) -> SequenceObservation:
        from afre.sequence.observations import observation_for

        with self.repository.read_snapshot(), self.repository.validation_cache():
            result = observation_for(self.repository, feature, source_id)
        self._publish((feature, result))
        return result

    def snapshot(
        self,
        origin: ForecastOrigin,
        features: tuple[SequenceFeatureDefinition, ...],
        window: SequenceWindowSpec,
        computed_ns: int,
        candidate_ids: tuple[str, ...] | None = None,
        snapshot_hook: Callable[[], None] | None = None,
    ) -> SequenceSnapshot:
        from afre.sequence.windows import snapshot_for

        self._publish((*features, window))
        with self.repository.read_snapshot(), self.repository.validation_cache():
            if candidate_ids is None:
                candidate_ids = self.repository.observation_ids(features, origin, computed_ns)
            if snapshot_hook:
                snapshot_hook()
            result = snapshot_for(
                self.repository, origin, features, window, candidate_ids, computed_ns
            )
        self._publish((result,))
        return result

    def fit_transform(
        self,
        spec: SequenceModelSpec,
        bindings: tuple[tuple[str, str], ...],
        started_ns: int,
        completed_ns: int,
        available_ns: int,
        snapshot_hook: Callable[[], None] | None = None,
    ) -> SequenceTransformArtifact:
        from afre.sequence.transforms import fit_transform

        self.publish_spec(spec)
        with self.repository.read_snapshot(), self.repository.validation_cache():
            if snapshot_hook:
                snapshot_hook()
            result = fit_transform(
                self.repository, spec, bindings, started_ns, completed_ns, available_ns
            )
        self._publish((result,))
        return result

    def dataset(
        self,
        spec: SequenceModelSpec,
        transform_id: str,
        computed_ns: int,
        snapshot_hook: Callable[[], None] | None = None,
    ) -> SequenceDataset:
        from afre.sequence.datasets import dataset_for

        self.publish_spec(spec)
        with self.repository.read_snapshot(), self.repository.validation_cache():
            state = self.repository.resolve(SequenceTransformArtifact, transform_id)
            if snapshot_hook:
                snapshot_hook()
            result = dataset_for(self.repository, spec, state, computed_ns)
        self._publish((*result.rows, result))
        return result

    def fit(
        self,
        spec: SequenceModelSpec,
        dataset_id: str,
        started_ns: int,
        completed_ns: int,
        available_ns: int,
        snapshot_hook: Callable[[], None] | None = None,
    ) -> SequenceModelArtifact:
        from afre.sequence.fitting import fit_model

        self.publish_spec(spec)
        with self.repository.read_snapshot(), self.repository.validation_cache():
            dataset = self.repository.resolve(SequenceDataset, dataset_id)
            self.repository._validate_links(dataset)
            if snapshot_hook:
                snapshot_hook()
            result = fit_model(
                self.repository, spec, dataset, started_ns, completed_ns, available_ns
            )
        self._publish((result,))
        return result

    def predict(
        self,
        model_id: str,
        sample_id: str,
        snapshot_id: str,
        computed_ns: int,
        base_probability_id: str | None = None,
        snapshot_hook: Callable[[], None] | None = None,
    ) -> SequenceForecast:
        from afre.sequence.predictions import forecast_for

        with self.repository.feature_only():
            with self.repository.read_snapshot(), self.repository.validation_cache():
                model = self.repository.resolve(SequenceModelArtifact, model_id)
                snapshot = self.repository.resolve(SequenceSnapshot, snapshot_id)
                if snapshot_hook:
                    snapshot_hook()
                result = forecast_for(
                    self.repository,
                    model,
                    sample_id,
                    snapshot,
                    computed_ns,
                    base_probability_id,
                )
            self._publish(
                (
                    *((result.probability,) if result.probability else ()),
                    *result.contributions,
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
    ) -> SequenceEvaluation:
        from afre.sequence.definitions import SequenceModelSpec
        from afre.sequence.evaluation import evaluation_for
        from afre.statistical_models.evaluation import test_record

        require(bool(ids), "sequence evaluation requires forecasts")
        with self.repository.read_snapshot(), self.repository.validation_cache():
            first = self.repository.resolve(SequenceForecast, ids[0])
            spec = self.repository.resolve(SequenceModelSpec, first.spec_id)
            if snapshot_hook:
                snapshot_hook()
            seal = None
            if first.partition is Partition.TEST:
                require(test_identity is not None, "explicit sequence TEST identity")
                seal = test_record(
                    self.repository,
                    spec.fold_id,
                    test_identity or "",
                    "sequence-exact-matched-comparison",
                    cutoff_ns,
                )
            result = evaluation_for(
                self.repository, ids, cutoff_ns, available_ns, baselines, seal, thresholds
            )
        self._publish((*((seal,) if seal else ()), *result.pairs, result))
        return result

    def stability(self, model_ids: tuple[str, ...], available_ns: int) -> SequenceStability:
        from afre.sequence.diagnostics import stability_for

        with self.repository.read_snapshot(), self.repository.validation_cache():
            result = stability_for(self.repository, model_ids, available_ns)
        self._publish((result,))
        return result

    def coverage(self, snapshot_ids: tuple[str, ...], available_ns: int) -> SequenceCoverage:
        from afre.sequence.diagnostics import coverage_for

        with self.repository.read_snapshot(), self.repository.validation_cache():
            result = coverage_for(self.repository, snapshot_ids, available_ns)
        self._publish((result,))
        return result

    def assess_calibration(
        self,
        forecast_id: str,
        ids: tuple[str, ...],
        cutoff_ns: int,
        minimum_count: int = 2,
        proposed_state_id: str | None = None,
    ) -> SequenceCalibrationAssessment:
        from afre.sequence.calibration import assessment_for

        with self.repository.read_snapshot(), self.repository.validation_cache():
            result = assessment_for(
                self.repository, forecast_id, ids, cutoff_ns, minimum_count, proposed_state_id
            )
        self._publish((result,))
        return result

    def audit_lineage(self, root_id: str) -> SequenceAudit:
        from afre.sequence.lineage import lineage_for

        with self.repository.read_snapshot(), self.repository.validation_cache():
            result = lineage_for(self.repository, root_id)
        self._publish((result,))
        return result

    def rank(
        self,
        template: CrossSectionSpec,
        ids: tuple[str, ...],
        groups: tuple[tuple[str, str], ...] = (),
    ) -> SequenceRanking:
        from afre.cross_sectional.engine import CrossSectionEngine
        from afre.sequence.cross_sectional import ranking_for, ranking_spec, sequence_signal

        require(
            0 < len(ids) <= self.repository.sequence_bounds.forecasts,
            "sequence ranking request bound",
        )
        with self.repository.read_snapshot(), self.repository.validation_cache():
            forecasts = tuple(self.repository.resolve(SequenceForecast, i) for i in sorted(ids))
            spec = ranking_spec(template, forecasts[0])
            signals = tuple(sequence_signal(f) for f in forecasts)
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
    ) -> SequenceRankEvaluation:
        from afre.cross_sectional.artifacts import CrossSectionRanking
        from afre.cross_sectional.engine import CrossSectionEngine
        from afre.cross_sectional.schema import TruthPolicy

        with self.repository.read_snapshot():
            rank = self.repository.resolve(SequenceRanking, ranking_id)
        matched = self.evaluate(
            rank.forecast_ids, cutoff_ns, available_ns, test_identity=test_identity
        )
        with self.repository.read_snapshot():
            underlying = self.repository.resolve(CrossSectionRanking, rank.ranking_id)
            targets = {
                self.repository.resolve(
                    SequenceForecast, p.forecast_id
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
        result = SequenceRankEvaluation(
            rank.fingerprint, matched.fingerprint, cross.fingerprint
        )
        self._publish((result,))
        return result

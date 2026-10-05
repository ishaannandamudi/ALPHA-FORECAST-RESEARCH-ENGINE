"""Frozen reads followed by atomic publication; no implicit latest-state substitution."""

from collections.abc import Callable

from afre.cross_sectional.definitions import CrossSectionSpec
from afre.cross_sectional.engine import CrossSectionEngine
from afre.event_conditioned.artifacts import (
    EventAudit,
    EventCalibrationAssessment,
    EventConditionedEvaluation,
    EventConditionedForecast,
    EventConditionedModel,
    EventConditionedObservation,
    EventRankEvaluation,
    EventRanking,
)
from afre.event_conditioned.calibration import assessment_for
from afre.event_conditioned.cross_sectional import event_signal, ranking_for, ranking_spec
from afre.event_conditioned.definitions import EventConditioningSpec
from afre.event_conditioned.evaluation import evaluation_for
from afre.event_conditioned.events import EventReference, EventSurprise, EventValue
from afre.event_conditioned.fitting import fit_for
from afre.event_conditioned.forecasts import forecast_for
from afre.event_conditioned.matching import base_context, matching_for, observations_for
from afre.event_conditioned.repository import EventRepository
from afre.feature_store.models import AvailabilityEvidence, SourceReference
from afre.schema import Artifact, require
from afre.statistical_models.artifacts import PointForecast
from afre.statistical_models.evaluation import test_record
from afre.statistical_models.schema import PredictionScope


class EventEngine:
    def __init__(self, repository: EventRepository) -> None:
        self.repository = repository

    def _publish(self, values: tuple[Artifact, ...]) -> None:
        with self.repository.transaction(), self.repository.validation_cache():
            for value in values:
                self.repository.put(value)

    def publish_event(self, event: EventReference) -> str:
        values: list[Artifact] = []

        def source(source: SourceReference, clocks: AvailabilityEvidence) -> None:
            values.append(source)
            if clocks.historical_delivery:
                values.append(clocks.historical_delivery)

        source(event.source, event.clocks)
        for attr in (event.materiality, event.novelty, event.surprise):
            if isinstance(attr, EventSurprise):
                for component in (attr.actual, attr.expected):
                    source(component.source, component.clocks)
                    values.append(component)
                values.append(attr)
            elif isinstance(attr, EventValue):
                source(attr.source, attr.clocks)
                values.append(attr)
        self._publish(
            (
                *values,
                *((event.subject.group_policy,) if event.subject.group_policy else ()),
                event.subject,
                event,
            )
        )
        return event.fingerprint

    def _publish_spec(self, spec: EventConditioningSpec) -> None:
        self._publish((spec.window, *spec.value_rules, *spec.reaction_specs, spec))

    def observe(
        self,
        spec: EventConditioningSpec,
        sample_id: str,
        event_ids: tuple[str, ...],
        reaction_ids: tuple[str, ...] = (),
        mapping_ids: tuple[str, ...] = (),
        snapshot_hook: Callable[[], None] | None = None,
    ) -> tuple[EventConditionedObservation, ...]:
        self._publish_spec(spec)
        repo = self.repository
        with repo.read_snapshot(), repo.validation_cache():
            repo.resolve(EventConditioningSpec, spec.fingerprint)
            if snapshot_hook:
                snapshot_hook()
            matches = matching_for(repo, spec, sample_id, event_ids, reaction_ids, mapping_ids)
            observations = observations_for(repo, matches)
        self._publish((matches, *observations))
        return observations

    def fit(
        self,
        spec: EventConditioningSpec,
        ids: tuple[str, ...],
        started_ns: int,
        completed_ns: int,
        available_ns: int,
    ) -> EventConditionedModel:
        self._publish_spec(spec)
        with self.repository.read_snapshot(), self.repository.validation_cache():
            model = fit_for(self.repository, spec, ids, started_ns, completed_ns, available_ns)
        self._publish((model,))
        return model

    def forecast(
        self,
        model_id: str,
        observation_id: str,
        base_id: str,
        computed_ns: int,
        probability_id: str | None = None,
        snapshot_hook: Callable[[], None] | None = None,
    ) -> EventConditionedForecast:
        repo = self.repository
        with repo.read_snapshot(), repo.validation_cache():
            model = repo.resolve(EventConditionedModel, model_id)
            if snapshot_hook:
                snapshot_hook()
            result = forecast_for(
                repo,
                model,
                repo.resolve(EventConditionedObservation, observation_id),
                base_id,
                probability_id,
                computed_ns,
            )
        self._publish((result,))
        return result

    def evaluate(
        self,
        ids: tuple[str, ...],
        cutoff_ns: int,
        available_ns: int,
        test_identity: str | None = None,
    ) -> EventConditionedEvaluation:
        repo = self.repository
        require(bool(ids), "event evaluation requires forecasts")
        with repo.read_snapshot(), repo.validation_cache():
            first = repo.resolve(EventConditionedForecast, ids[0])
            base = repo.resolve(PointForecast, first.base_forecast_id)
            spec = repo.resolve(EventConditioningSpec, first.spec_id)
            seal = None
            if base.input.scope is PredictionScope.TEST:
                require(test_identity is not None, "explicit event TEST evaluation identity")
                seal = test_record(
                    repo,
                    base_context(repo, spec).fold_id,
                    test_identity or "",
                    "event-conditioned-matched-comparison",
                    cutoff_ns,
                )
            result = evaluation_for(repo, ids, cutoff_ns, available_ns, seal)
        self._publish((*((seal,) if seal else ()), result))
        return result

    def assess_calibration(
        self, forecast_id: str, ids: tuple[str, ...], cutoff_ns: int, minimum_count: int = 2
    ) -> EventCalibrationAssessment:
        with self.repository.read_snapshot(), self.repository.validation_cache():
            result = assessment_for(self.repository, forecast_id, ids, cutoff_ns, minimum_count)
        self._publish((result,))
        return result

    def rank(
        self,
        template: CrossSectionSpec,
        ids: tuple[str, ...],
        groups: tuple[tuple[str, str], ...] = (),
    ) -> EventRanking:
        repo = self.repository
        require(bool(ids), "event rank requires forecasts")
        with repo.read_snapshot(), repo.validation_cache():
            forecasts = tuple(repo.resolve(EventConditionedForecast, i) for i in sorted(ids))
            spec = ranking_spec(template, forecasts[0])
            signals = tuple(event_signal(f) for f in forecasts)
        cs = CrossSectionEngine(repo)
        for signal in signals:
            cs.publish_external(signal)
        ranking = cs.build_ranking(
            spec, tuple((s.security.fingerprint, s.fingerprint) for s in signals), groups
        )
        with repo.read_snapshot(), repo.validation_cache():
            result = ranking_for(repo, ranking.fingerprint, ids)
        self._publish((result,))
        return result

    def evaluate_rank(
        self,
        ranking_id: str,
        cutoff_ns: int,
        available_ns: int,
        test_identity: str | None = None,
    ) -> EventRankEvaluation:
        repo = self.repository
        with repo.read_snapshot():
            rank = repo.resolve(EventRanking, ranking_id)
        matched = self.evaluate(rank.forecast_ids, cutoff_ns, available_ns, test_identity)
        from afre.cross_sectional.artifacts import CrossSectionRanking
        from afre.cross_sectional.schema import TruthPolicy

        with repo.read_snapshot():
            underlying = repo.resolve(CrossSectionRanking, rank.ranking_id)
            lookup = {
                repo.resolve(
                    EventConditionedForecast, p.forecast_id
                ).security.fingerprint: p.target_id
                for p in matched.pairs
            }
            targets = tuple(
                (e.security.fingerprint, lookup.get(e.security.fingerprint))
                for e in underlying.entries
            )
        result = CrossSectionEngine(repo).evaluate(
            rank.ranking_id,
            targets,
            cutoff_ns,
            available_ns,
            policy=TruthPolicy.AVAILABLE_INTERSECTION,
        )
        wrapper = EventRankEvaluation(rank.fingerprint, matched.fingerprint, result.fingerprint)
        self._publish((wrapper,))
        return wrapper

    def audit_lineage(self, root_id: str) -> EventAudit:
        from afre.event_conditioned.lineage import lineage_for

        with self.repository.read_snapshot(), self.repository.validation_cache():
            audit = lineage_for(self.repository, root_id)
        self._publish((audit,))
        return audit

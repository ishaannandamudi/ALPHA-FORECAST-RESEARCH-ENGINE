"""Frozen reads followed by atomic publication; no implicit latest-state substitution."""

from collections.abc import Callable

from afre.cross_sectional.definitions import CrossSectionSpec
from afre.cross_sectional.engine import CrossSectionEngine
from afre.regime_conditioned.artifacts import (
    RegimeAudit,
    RegimeCalibrationAssessment,
    RegimeConditionedEvaluation,
    RegimeConditionedForecast,
    RegimeConditionedModel,
    RegimeConditionedSample,
    RegimeDriftDiagnostic,
    RegimeRankEvaluation,
    RegimeRanking,
)
from afre.regime_conditioned.calibration import assessment_for
from afre.regime_conditioned.cross_sectional import ranking_for, ranking_spec, regime_signal
from afre.regime_conditioned.definitions import RegimeConditioningSpec
from afre.regime_conditioned.drift import drift_for
from afre.regime_conditioned.evaluation import evaluation_for
from afre.regime_conditioned.fitting import fit_for
from afre.regime_conditioned.forecasts import forecast_for, native_base
from afre.regime_conditioned.matching import base_context, matching_for, observation_for
from afre.regime_conditioned.regimes import RegimeSnapshot, RegimeTaxonomy
from afre.regime_conditioned.repository import RegimeRepository
from afre.schema import Artifact, require
from afre.statistical_models.evaluation import test_record
from afre.statistical_models.schema import PredictionScope


class RegimeEngine:
    def __init__(self, repository: RegimeRepository) -> None:
        self.repository = repository

    def _publish(self, values: tuple[Artifact, ...]) -> None:
        with self.repository.transaction(), self.repository.validation_cache():
            for value in values:
                self.repository.put(value)

    def publish_taxonomy(self, taxonomy: RegimeTaxonomy) -> str:
        self._publish((taxonomy.provider.source, taxonomy.provider, taxonomy))
        return taxonomy.fingerprint

    def publish_snapshot(self, snapshot: RegimeSnapshot) -> str:
        values: list[Artifact] = [
            snapshot.taxonomy.provider.source,
            snapshot.taxonomy.provider,
            snapshot.taxonomy,
            snapshot.source,
        ]
        if snapshot.clocks.historical_delivery:
            values.append(snapshot.clocks.historical_delivery)
        if snapshot.subject.group_policy:
            values.append(snapshot.subject.group_policy)
        self._publish((*values, snapshot.subject, snapshot.membership, snapshot))
        return snapshot.fingerprint

    def _publish_spec(self, spec: RegimeConditioningSpec) -> None:
        self._publish((spec,))

    def observe(
        self,
        spec: RegimeConditioningSpec,
        sample_id: str,
        snapshot_ids: tuple[str, ...],
        mapping_ids: tuple[str, ...] = (),
        snapshot_hook: Callable[[], None] | None = None,
    ) -> RegimeConditionedSample:
        self._publish_spec(spec)
        repo = self.repository
        with repo.read_snapshot(), repo.validation_cache():
            repo.resolve(RegimeConditioningSpec, spec.fingerprint)
            if snapshot_hook:
                snapshot_hook()
            match = matching_for(repo, spec, sample_id, snapshot_ids, mapping_ids)
            observation, transitions = observation_for(repo, match)
        self._publish((match, *transitions, observation))
        return observation

    def fit(
        self,
        spec: RegimeConditioningSpec,
        ids: tuple[str, ...],
        started_ns: int,
        completed_ns: int,
        available_ns: int,
        snapshot_hook: Callable[[], None] | None = None,
    ) -> RegimeConditionedModel:
        self._publish_spec(spec)
        with self.repository.read_snapshot(), self.repository.validation_cache():
            self.repository.resolve(RegimeConditioningSpec, spec.fingerprint)
            if snapshot_hook:
                snapshot_hook()
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
    ) -> RegimeConditionedForecast:
        repo = self.repository
        with repo.read_snapshot(), repo.validation_cache():
            model = repo.resolve(RegimeConditionedModel, model_id)
            if snapshot_hook:
                snapshot_hook()
            result = forecast_for(
                repo,
                model,
                repo.resolve(RegimeConditionedSample, observation_id),
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
    ) -> RegimeConditionedEvaluation:
        repo = self.repository
        require(bool(ids), "regime evaluation requires forecasts")
        with repo.read_snapshot(), repo.validation_cache():
            first = repo.resolve(RegimeConditionedForecast, ids[0])
            base = native_base(repo, first.base_forecast_id)
            spec = repo.resolve(RegimeConditioningSpec, first.spec_id)
            seal = None
            if base.input.scope is PredictionScope.TEST:
                require(test_identity is not None, "explicit regime TEST evaluation identity")
                seal = test_record(
                    repo,
                    base_context(repo, spec).fold_id,
                    test_identity or "",
                    "regime-conditioned-matched-comparison",
                    cutoff_ns,
                )
            result = evaluation_for(repo, ids, cutoff_ns, available_ns, seal)
        self._publish((*((seal,) if seal else ()), result))
        return result

    def assess_calibration(
        self,
        forecast_id: str,
        ids: tuple[str, ...],
        cutoff_ns: int,
        minimum_count: int = 2,
        global_state_id: str | None = None,
    ) -> RegimeCalibrationAssessment:
        with self.repository.read_snapshot(), self.repository.validation_cache():
            result = assessment_for(
                self.repository, forecast_id, ids, cutoff_ns, minimum_count, global_state_id
            )
        self._publish((result,))
        return result

    def drift(
        self, reference_id: str, current_id: str, cutoff_ns: int, minimum_count: int = 2
    ) -> RegimeDriftDiagnostic:
        with self.repository.read_snapshot(), self.repository.validation_cache():
            result = drift_for(
                self.repository, reference_id, current_id, cutoff_ns, minimum_count
            )
        self._publish((result,))
        return result

    def rank(
        self,
        template: CrossSectionSpec,
        ids: tuple[str, ...],
        groups: tuple[tuple[str, str], ...] = (),
    ) -> RegimeRanking:
        repo = self.repository
        require(bool(ids), "regime rank requires forecasts")
        with repo.read_snapshot(), repo.validation_cache():
            forecasts = tuple(repo.resolve(RegimeConditionedForecast, i) for i in sorted(ids))
            spec = ranking_spec(template, forecasts[0])
            signals = tuple(regime_signal(f) for f in forecasts)
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
    ) -> RegimeRankEvaluation:
        repo = self.repository
        with repo.read_snapshot():
            rank = repo.resolve(RegimeRanking, ranking_id)
        matched = self.evaluate(rank.forecast_ids, cutoff_ns, available_ns, test_identity)
        from afre.cross_sectional.artifacts import CrossSectionRanking
        from afre.cross_sectional.schema import TruthPolicy

        with repo.read_snapshot():
            underlying = repo.resolve(CrossSectionRanking, rank.ranking_id)
            lookup = {
                repo.resolve(
                    RegimeConditionedForecast, p.forecast_id
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
        wrapper = RegimeRankEvaluation(
            rank.fingerprint, matched.fingerprint, result.fingerprint
        )
        self._publish((wrapper,))
        return wrapper

    def audit_lineage(self, root_id: str) -> RegimeAudit:
        from afre.regime_conditioned.lineage import lineage_for

        with self.repository.read_snapshot(), self.repository.validation_cache():
            audit = lineage_for(self.repository, root_id)
        self._publish((audit,))
        return audit

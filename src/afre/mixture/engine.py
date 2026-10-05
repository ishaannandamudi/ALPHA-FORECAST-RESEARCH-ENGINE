"""Frozen read stages and atomic publication with exact supplied artifact identities."""

from collections.abc import Callable

from afre.cross_sectional.definitions import CrossSectionSpec
from afre.cross_sectional.engine import CrossSectionEngine
from afre.mixture.artifacts import (
    GateDriftDiagnostic,
    GateModelArtifact,
    GateTrainingRow,
    MixtureAudit,
    MixtureCalibrationAssessment,
    MixtureDiagnostics,
    MixtureEvaluation,
    MixtureForecast,
    MixtureRankEvaluation,
    MixtureRanking,
    MixtureRequest,
)
from afre.mixture.availability import binding_for
from afre.mixture.calibration import assessment_for
from afre.mixture.definitions import ExpertSet, FixedGateSpec, LearnedGateSpec
from afre.mixture.diagnostics import diagnostics_for, drift_for
from afre.mixture.evaluation import evaluation_for
from afre.mixture.experts import (
    ExpertForecastBinding,
    ExpertReference,
    ExternalExpertForecast,
    GatingFeatureReference,
)
from afre.mixture.fitting import fit_for, row_for
from afre.mixture.forecasts import forecast_for
from afre.mixture.repository import MixtureRepository
from afre.probabilistic.definitions import ThresholdRequest
from afre.research_datasets.schema import Partition
from afre.schema import Artifact, require
from afre.statistical_models.evaluation import test_record


class MixtureEngine:
    def __init__(self, repository: MixtureRepository) -> None:
        self.repository = repository

    def _publish(self, values: tuple[Artifact, ...]) -> None:
        with self.repository.transaction(), self.repository.validation_cache():
            for value in values:
                self.repository.put(value)

    def register_expert(self, expert: ExpertReference) -> str:
        self._publish((expert.source, expert.target, expert))
        return expert.fingerprint

    def publish_external(self, forecast: ExternalExpertForecast) -> str:
        self.register_expert(forecast.expert)
        proof = forecast.clocks.historical_delivery
        self._publish((forecast.source, *((proof,) if proof else ()), forecast))
        return forecast.fingerprint

    def bind(self, expert_id: str, forecast_id: str) -> ExpertForecastBinding:
        with self.repository.read_snapshot(), self.repository.validation_cache():
            result = binding_for(
                self.repository,
                self.repository.resolve(ExpertReference, expert_id),
                forecast_id,
            )
        self._publish((result,))
        return result

    def publish_gate(self, spec: FixedGateSpec | LearnedGateSpec) -> str:
        for expert in spec.expert_set.experts:
            self.register_expert(expert)
        self._publish((spec.expert_set, spec))
        return spec.fingerprint

    def publish_gating_feature(self, feature: GatingFeatureReference) -> str:
        self._publish((feature,))
        return feature.fingerprint

    def training_row(
        self,
        spec: LearnedGateSpec,
        sample_id: str,
        bindings: tuple[str, ...],
        features: tuple[str, ...] = (),
        snapshot_hook: Callable[[], None] | None = None,
    ) -> GateTrainingRow:
        self.publish_gate(spec)
        repo = self.repository
        with repo.read_snapshot(), repo.validation_cache():
            repo.resolve(LearnedGateSpec, spec.fingerprint)
            if snapshot_hook:
                snapshot_hook()
            result = row_for(repo, spec, sample_id, bindings, features)
        self._publish((result,))
        return result

    def fit(
        self,
        spec: LearnedGateSpec,
        row_ids: tuple[str, ...],
        started_ns: int,
        completed_ns: int,
        available_ns: int,
        snapshot_hook: Callable[[], None] | None = None,
    ) -> GateModelArtifact:
        self.publish_gate(spec)
        repo = self.repository
        with repo.read_snapshot(), repo.validation_cache():
            repo.resolve(LearnedGateSpec, spec.fingerprint)
            if snapshot_hook:
                snapshot_hook()
            require(
                len(row_ids) <= repo.mixture_bounds.training_samples, "gate row request bound"
            )
            rows = tuple(repo.resolve(GateTrainingRow, i) for i in row_ids)
            result = fit_for(repo, spec, rows, started_ns, completed_ns, available_ns)
        self._publish((result,))
        return result

    def forecast(
        self, request: MixtureRequest, snapshot_hook: Callable[[], None] | None = None
    ) -> MixtureForecast:
        repo = self.repository
        with repo.read_snapshot(), repo.validation_cache():
            repo.resolve(ExpertSet, request.expert_set_id)
            if snapshot_hook:
                snapshot_hook()
            result = forecast_for(repo, request)
        probability: tuple[Artifact, ...] = (
            (*result.distribution.components, result.distribution)
            if result.distribution
            else ()
        )
        self._publish((*probability, request, result))
        return result

    def evaluate(
        self,
        ids: tuple[str, ...],
        cutoff_ns: int,
        available_ns: int,
        test_identity: str | None = None,
        thresholds: tuple[ThresholdRequest, ...] = (),
    ) -> MixtureEvaluation:
        require(bool(ids), "mixture evaluation requires forecasts")
        repo = self.repository
        with repo.read_snapshot(), repo.validation_cache():
            first = repo.resolve(MixtureForecast, ids[0])
            seal = None
            if first.partition is Partition.TEST:
                require(test_identity is not None, "explicit mixture TEST identity")
                seal = test_record(
                    repo,
                    first.request.fold_id,
                    test_identity or "",
                    "mixture-exact-matched-comparison",
                    cutoff_ns,
                )
            result = evaluation_for(repo, ids, cutoff_ns, available_ns, seal, thresholds)
        self._publish((*((seal,) if seal else ()), result))
        return result

    def diagnostics(self, evaluation_id: str) -> MixtureDiagnostics:
        with self.repository.read_snapshot(), self.repository.validation_cache():
            result = diagnostics_for(self.repository, evaluation_id)
        self._publish((result,))
        return result

    def drift(
        self, reference_id: str, current_id: str, cutoff_ns: int, minimum_count: int = 2
    ) -> GateDriftDiagnostic:
        with self.repository.read_snapshot(), self.repository.validation_cache():
            result = drift_for(
                self.repository, reference_id, current_id, cutoff_ns, minimum_count
            )
        self._publish((result,))
        return result

    def assess_calibration(
        self,
        forecast_id: str,
        ids: tuple[str, ...],
        cutoff_ns: int,
        minimum_count: int = 2,
        component_state_id: str | None = None,
    ) -> MixtureCalibrationAssessment:
        with self.repository.read_snapshot(), self.repository.validation_cache():
            result = assessment_for(
                self.repository, forecast_id, ids, cutoff_ns, minimum_count, component_state_id
            )
        self._publish((result,))
        return result

    def rank(
        self,
        template: CrossSectionSpec,
        ids: tuple[str, ...],
        groups: tuple[tuple[str, str], ...] = (),
    ) -> MixtureRanking:
        from afre.mixture.cross_sectional import mixture_signal, ranking_for, ranking_spec

        require(bool(ids), "mixture ranking requires forecasts")
        repo = self.repository
        with repo.read_snapshot(), repo.validation_cache():
            forecasts = tuple(repo.resolve(MixtureForecast, i) for i in sorted(ids))
            spec = ranking_spec(template, forecasts[0])
            signals = tuple(mixture_signal(f) for f in forecasts)
        cs = CrossSectionEngine(repo)
        for signal in signals:
            cs.publish_external(signal)
        rank = cs.build_ranking(
            spec, tuple((s.security.fingerprint, s.fingerprint) for s in signals), groups
        )
        with repo.read_snapshot(), repo.validation_cache():
            result = ranking_for(repo, rank.fingerprint, ids)
        self._publish((result,))
        return result

    def evaluate_rank(
        self,
        ranking_id: str,
        cutoff_ns: int,
        available_ns: int,
        test_identity: str | None = None,
    ) -> MixtureRankEvaluation:
        from afre.cross_sectional.artifacts import CrossSectionRanking
        from afre.cross_sectional.schema import TruthPolicy

        repo = self.repository
        with repo.read_snapshot():
            rank = repo.resolve(MixtureRanking, ranking_id)
        matched = self.evaluate(rank.forecast_ids, cutoff_ns, available_ns, test_identity)
        with repo.read_snapshot():
            underlying = repo.resolve(CrossSectionRanking, rank.ranking_id)
            targets_by_security = {
                repo.resolve(MixtureForecast, p.forecast_id).security.fingerprint: p.target_id
                for p in matched.pairs
            }
            targets = tuple(
                (e.security.fingerprint, targets_by_security.get(e.security.fingerprint))
                for e in underlying.entries
            )
        result = CrossSectionEngine(repo).evaluate(
            rank.ranking_id,
            targets,
            cutoff_ns,
            available_ns,
            policy=TruthPolicy.AVAILABLE_INTERSECTION,
        )
        wrapper = MixtureRankEvaluation(
            rank.fingerprint, matched.fingerprint, result.fingerprint
        )
        self._publish((wrapper,))
        return wrapper

    def audit_lineage(self, root_id: str) -> MixtureAudit:
        from afre.mixture.lineage import lineage_for

        with self.repository.read_snapshot(), self.repository.validation_cache():
            result = lineage_for(self.repository, root_id)
        self._publish((result,))
        return result

"""Explicit frozen-snapshot research API; all publication is atomic."""

from collections.abc import Callable
from dataclasses import replace

from afre.cross_sectional.artifacts import (
    CrossSectionAudit,
    CrossSectionEvaluation,
    CrossSectionObservation,
    CrossSectionRanking,
    ICSeries,
    RankStability,
)
from afre.cross_sectional.cross_section import eligible_grid, ranking_for
from afre.cross_sectional.definitions import CrossSectionSpec
from afre.cross_sectional.evaluation import evaluation_for, series_for, truth_for
from afre.cross_sectional.external import ExternalSignal
from afre.cross_sectional.groups import GroupMembership
from afre.cross_sectional.models import (
    CrossSectionModel,
    CrossSectionModelSpec,
    CrossSectionPrediction,
    fit_relative,
    relative_prediction,
)
from afre.cross_sectional.repository import CrossSectionRepository
from afre.cross_sectional.schema import StabilityMembership, TruthPolicy
from afre.cross_sectional.scoring import point_scaffold
from afre.cross_sectional.stability import stability_for
from afre.schema import Artifact, require
from afre.statistical_models.artifacts import FittedModelArtifact, PointForecast
from afre.statistical_models.definitions import BaselineModelSpec
from afre.statistical_models.evaluation import test_record
from afre.statistical_models.schema import PredictionScope
from afre.universe.schema import EligibilityState


class CrossSectionEngine:
    def __init__(self, repository: CrossSectionRepository) -> None:
        self.repository = repository

    def _publish(self, values: tuple[Artifact, ...]) -> None:
        with self.repository.transaction(), self.repository.validation_cache():
            for value in values:
                self.repository.put(value)

    def publish_external(self, signal: ExternalSignal) -> str:
        values: tuple[Artifact, ...] = (signal.source,)
        if signal.clocks.historical_delivery:
            values += (signal.clocks.historical_delivery,)
        self._publish((*values, signal))
        return signal.fingerprint

    def publish_group(self, membership: GroupMembership) -> str:
        values: tuple[Artifact, ...] = (membership.source,)
        if membership.clocks.historical_delivery:
            values += (membership.clocks.historical_delivery,)
        self._publish((*values, membership))
        return membership.fingerprint

    def build_ranking(
        self,
        spec: CrossSectionSpec,
        sources: tuple[tuple[str, str], ...],
        groups: tuple[tuple[str, str], ...] = (),
        computed_ns: int | None = None,
        snapshot_hook: Callable[[], None] | None = None,
    ) -> CrossSectionRanking:
        repo = self.repository
        source_map, group_map = dict(sources), dict(groups)
        require(
            len(sources) == len(source_map) and len(groups) == len(group_map),
            "duplicate input security",
        )
        with repo.read_snapshot(), repo.validation_cache():
            snapshot = eligible_grid(repo, spec)
            if snapshot_hook:
                snapshot_hook()
            eligible = tuple(
                e for e in snapshot.eligibility if e.state is EligibilityState.ELIGIBLE
            )
            keys = {e.membership.security.fingerprint for e in eligible}
            require(
                set(source_map) <= keys and set(group_map) <= keys,
                "input security ineligible/outside snapshot",
            )
            observations = tuple(
                CrossSectionObservation(
                    spec.fingerprint,
                    e.membership.security,
                    replace(
                        spec.identity.anchor_origin, instrument=e.membership.security.instrument
                    ),
                    source_map.get(e.membership.security.fingerprint),
                    group_map.get(e.membership.security.fingerprint),
                    listing=e.listing,
                )
                for e in eligible
            )
            ranking, raw, normalized, neutral = ranking_for(
                repo,
                spec,
                observations,
                spec.identity.anchor_origin.timestamp_ns
                if computed_ns is None
                else computed_ns,
            )
        self._publish(
            (
                spec.identity,
                spec,
                *observations,
                *raw,
                normalized,
                *((neutral,) if neutral else ()),
                ranking,
            )
        )
        return ranking

    def evaluate(
        self,
        ranking_id: str,
        targets: tuple[tuple[str, str | None], ...],
        cutoff_ns: int,
        available_ns: int,
        top_k: int = 1,
        bucket_count: int = 2,
        policy: TruthPolicy = TruthPolicy.REQUIRE_COMPLETE,
        test_evaluation_identity: str | None = None,
    ) -> CrossSectionEvaluation:
        repo = self.repository
        with repo.read_snapshot(), repo.validation_cache():
            ranking = repo.resolve(CrossSectionRanking, ranking_id)
            repo._validate_links(ranking)
            folds: set[str] = set()
            for entry in ranking.entries:
                o = repo.resolve(CrossSectionObservation, entry.observation_id)
                scaffold = point_scaffold(repo, o.source_id) if o.source_id else None
                if scaffold and scaffold.input.scope is PredictionScope.TEST:
                    base = repo.resolve(FittedModelArtifact, scaffold.model_artifact_id)
                    folds.add(repo.resolve(BaselineModelSpec, base.spec_id).fold_id)
            require(
                not folds or test_evaluation_identity is not None,
                "explicit TEST evaluation identity required",
            )
            seals = tuple(
                test_record(
                    repo,
                    fold,
                    f"{test_evaluation_identity}:{ranking_id}",
                    "cross-sectional-ranking",
                    cutoff_ns,
                )
                for fold in sorted(folds)
            )
            truth = truth_for(repo, ranking, targets, cutoff_ns, available_ns, policy, seals)
            evaluation = evaluation_for(repo, ranking, truth, top_k, bucket_count, available_ns)
        self._publish((*seals, truth, evaluation))
        return evaluation

    def aggregate_ic(self, evaluation_ids: tuple[str, ...], rank_ic: bool = False) -> ICSeries:
        with self.repository.read_snapshot(), self.repository.validation_cache():
            result = series_for(self.repository, evaluation_ids, rank_ic)
        self._publish((result,))
        return result

    def stability(
        self,
        previous_id: str,
        current_id: str,
        top_k: int = 1,
        policy: StabilityMembership = StabilityMembership.INTERSECTION,
    ) -> RankStability:
        repo = self.repository
        with repo.read_snapshot(), repo.validation_cache():
            result = stability_for(
                repo,
                repo.resolve(CrossSectionRanking, previous_id),
                repo.resolve(CrossSectionRanking, current_id),
                top_k,
                policy,
            )
        self._publish((result,))
        return result

    def fit(
        self, spec: CrossSectionModelSpec, started_ns: int, completed_ns: int, available_ns: int
    ) -> CrossSectionModel:
        with self.repository.read_snapshot(), self.repository.validation_cache():
            model = fit_relative(self.repository, spec, started_ns, completed_ns, available_ns)
        self._publish((spec, model))
        return model

    def predict(
        self, model_id: str, scaffold_id: str, computed_ns: int
    ) -> CrossSectionPrediction:
        repo = self.repository
        with repo.read_snapshot(), repo.validation_cache():
            result = relative_prediction(
                repo,
                repo.resolve(CrossSectionModel, model_id),
                repo.resolve(PointForecast, scaffold_id),
                computed_ns,
            )
        self._publish((result,))
        return result

    def audit_lineage(self, root_id: str) -> CrossSectionAudit:
        from afre.cross_sectional.lineage import lineage_for

        with self.repository.read_snapshot(), self.repository.validation_cache():
            result = lineage_for(self.repository, root_id)
        self._publish((result,))
        return result

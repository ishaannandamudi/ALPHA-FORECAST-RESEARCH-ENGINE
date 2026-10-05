"""Fail-closed semantic replay, kept separate from target-free application."""

from typing import TYPE_CHECKING

from afre.cross_sectional.artifacts import (
    CrossSectionAudit,
    CrossSectionEvaluation,
    CrossSectionObservation,
    CrossSectionRanking,
    CrossSectionTruth,
    ICSeries,
    PeerState,
    RankStability,
    RawScore,
)
from afre.cross_sectional.cross_section import eligible_grid, ranking_for
from afre.cross_sectional.definitions import CrossSectionIdentity, CrossSectionSpec
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
from afre.cross_sectional.normalization import peer_state
from afre.cross_sectional.scoring import score_for
from afre.cross_sectional.stability import stability_for
from afre.feature_store.models import QualifiedHistoricalDelivery, SourceReference
from afre.research_datasets.splits import TestEvaluation
from afre.schema import Artifact, require
from afre.statistical_models.artifacts import PointForecast
from afre.universe.schema import EligibilityState

if TYPE_CHECKING:
    from afre.cross_sectional.repository import CrossSectionRepository


def validate_links(repo: "CrossSectionRepository", value: Artifact) -> None:
    if isinstance(value, CrossSectionSpec):
        eligible_grid(repo, value)
        require(
            repo.resolve(CrossSectionIdentity, value.identity.fingerprint) == value.identity,
            "cross-section identity persistence",
        )
    elif isinstance(value, (ExternalSignal, GroupMembership)):
        require(
            repo.resolve(SourceReference, value.source.fingerprint) == value.source,
            "source provenance",
        )
        if value.clocks.historical_delivery:
            proof = value.clocks.historical_delivery
            require(
                repo.resolve(QualifiedHistoricalDelivery, proof.fingerprint) == proof,
                "delivery provenance",
            )
    elif isinstance(value, CrossSectionObservation):
        spec = repo.resolve(CrossSectionSpec, value.spec_id)
        snapshot = eligible_grid(repo, spec)
        eligibility = next(
            (e for e in snapshot.eligibility if e.membership.security == value.security), None
        )
        require(
            eligibility is not None
            and eligibility.state is EligibilityState.ELIGIBLE
            and (value.listing is None or value.listing == eligibility.listing),
            "observation listing/universe",
        )
        require(
            value.issuer is None, "issuer enrichment needs explicit security record evidence"
        )
        score_for(repo, spec, value)
    elif isinstance(value, RawScore):
        observation = repo.resolve(CrossSectionObservation, value.observation_id)
        require(
            value
            == score_for(
                repo, repo.resolve(CrossSectionSpec, observation.spec_id), observation
            ),
            "raw score contamination",
        )
    elif isinstance(value, PeerState):
        spec = repo.resolve(CrossSectionSpec, value.spec_id)
        scores = tuple(repo.resolve(RawScore, i) for i in value.raw_ids)
        observations = tuple(
            repo.resolve(CrossSectionObservation, s.observation_id) for s in scores
        )
        groups = tuple(
            repo.resolve(GroupMembership, o.group_id) for o in observations if o.group_id
        )
        require(
            value == peer_state(spec, scores, value.available_ns, groups, value.group_neutral),
            "peer normalization contamination",
        )
    elif isinstance(value, CrossSectionRanking):
        spec = repo.resolve(CrossSectionSpec, value.spec_id)
        observations = tuple(
            repo.resolve(CrossSectionObservation, e.observation_id) for e in value.entries
        )
        expected, scores, normalized, neutral = ranking_for(
            repo, spec, observations, value.computed_ns
        )
        require(
            value == expected
            and repo.resolve(PeerState, normalized.fingerprint) == normalized
            and all(repo.resolve(RawScore, s.fingerprint) == s for s in scores),
            "rank contamination",
        )
        require(
            neutral is None or repo.resolve(PeerState, neutral.fingerprint) == neutral,
            "group score contamination",
        )
    elif isinstance(value, CrossSectionTruth):
        ranking = repo.resolve(CrossSectionRanking, value.ranking_id)
        seals = tuple(repo.resolve(TestEvaluation, s) for s in value.test_evaluation_ids)
        require(
            value
            == truth_for(
                repo,
                ranking,
                tuple((r.security.fingerprint, r.target_id) for r in value.rows),
                value.cutoff_ns,
                value.available_ns,
                value.policy,
                seals,
            ),
            "truth contamination",
        )
    elif isinstance(value, CrossSectionEvaluation):
        require(
            value
            == evaluation_for(
                repo,
                repo.resolve(CrossSectionRanking, value.ranking_id),
                repo.resolve(CrossSectionTruth, value.truth_id),
                value.top_k,
                value.bucket_count,
                value.available_ns,
            ),
            "IC/evaluation contamination",
        )
    elif isinstance(value, ICSeries):
        require(
            value == series_for(repo, value.evaluation_ids, value.rank_ic),
            "IC aggregation contamination",
        )
    elif isinstance(value, RankStability):
        require(
            value
            == stability_for(
                repo,
                repo.resolve(CrossSectionRanking, value.previous_id),
                repo.resolve(CrossSectionRanking, value.current_id),
                value.top_k,
                value.policy,
            ),
            "stability contamination",
        )
    elif isinstance(value, CrossSectionModelSpec):
        repo.get_any(value.baseline_model_id)
    elif isinstance(value, CrossSectionModel):
        model_spec = repo.resolve(CrossSectionModelSpec, value.spec_id)
        require(
            value
            == fit_relative(
                repo,
                model_spec,
                value.fit_started_ns,
                value.fit_completed_ns,
                value.available_ns,
            ),
            "relative TRAIN/fit contamination",
        )
    elif isinstance(value, CrossSectionPrediction):
        require(
            value
            == relative_prediction(
                repo,
                repo.resolve(CrossSectionModel, value.model_id),
                repo.resolve(PointForecast, value.scaffold_id),
                value.computed_ns,
            ),
            "relative prediction contamination",
        )
    elif isinstance(value, CrossSectionAudit):
        from afre.cross_sectional.lineage import lineage_for

        require(
            value == lineage_for(repo, value.root_id), "cross-sectional lineage contamination"
        )

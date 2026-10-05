"""Descriptive rank continuity on explicit intersection; no turnover cost model."""

from typing import TYPE_CHECKING

from afre.cross_sectional.artifacts import CrossSectionRanking, RankStability
from afre.cross_sectional.definitions import CrossSectionSpec
from afre.cross_sectional.ranks import rank_values
from afre.cross_sectional.schema import RankDirection, StabilityMembership
from afre.schema import require
from afre.statistical_models.artifacts import PointMetric
from afre.statistical_models.metrics import correlation
from afre.statistical_models.schema import MetricName
from afre.universe.models import UniverseSnapshot

if TYPE_CHECKING:
    from afre.cross_sectional.repository import CrossSectionRepository


def stability_for(
    repo: "CrossSectionRepository",
    previous: CrossSectionRanking,
    current: CrossSectionRanking,
    top_k: int,
    policy: StabilityMembership,
) -> RankStability:
    a, b = (
        repo.resolve(CrossSectionSpec, previous.spec_id),
        repo.resolve(CrossSectionSpec, current.spec_id),
    )

    def signature(s: CrossSectionSpec) -> tuple[object, ...]:
        return (
            s.identity.target,
            s.identity.eligibility_policy_id,
            s.score,
            s.direction,
            s.ties,
            s.normalization,
            s.group,
            s.ranking_layer,
            s.missing,
            s.maximum_missing_fraction,
            s.approved_delivery_attestors,
            repo.resolve(UniverseSnapshot, s.identity.snapshot_id).definition,
        )

    require(
        signature(a) == signature(b)
        and a.identity.anchor_origin.timestamp_ns < b.identity.anchor_origin.timestamp_ns
        and top_k > 0,
        "incompatible/ unordered stability origins",
    )
    left = {e.security.fingerprint: e.rank for e in previous.entries if e.rank is not None}
    right = {e.security.fingerprint: e.rank for e in current.entries if e.rank is not None}
    same = set(left) == set(right)
    eligible_left = {e.security.fingerprint for e in previous.entries}
    eligible_right = {e.security.fingerprint for e in current.entries}
    eligible_same = eligible_left == eligible_right
    require(
        policy is not StabilityMembership.SAME_MEMBERS or (same and eligible_same),
        "stability requires same ranked membership",
    )
    keys = tuple(sorted(set(left) & set(right)))
    left_ranks = {
        k: r
        for k, r, _ in rank_values(
            tuple((k, left[k]) for k in keys), RankDirection.LOWER_BETTER, a.ties
        )
    }
    right_ranks = {
        k: r
        for k, r, _ in rank_values(
            tuple((k, right[k]) for k in keys), RankDirection.LOWER_BETTER, a.ties
        )
    }
    metric = correlation(
        tuple(left_ranks[k] for k in keys), tuple(right_ranks[k] for k in keys)
    )
    spearman = PointMetric(
        MetricName.SPEARMAN_CORRELATION, metric.value, metric.state, len(keys)
    )
    ltop, rtop = (
        set(sorted(left, key=lambda k: (left[k], k))[:top_k]),
        set(sorted(right, key=lambda k: (right[k], k))[:top_k]),
    )
    overlap = len(ltop & rtop)
    union = set(left) | set(right)
    return RankStability(
        previous.fingerprint,
        current.fingerprint,
        policy,
        keys,
        tuple(sorted(set(right) - set(left))),
        tuple(sorted(set(left) - set(right))),
        same,
        eligible_same,
        tuple(sorted(eligible_right - eligible_left)),
        tuple(sorted(eligible_left - eligible_right)),
        len(eligible_left ^ eligible_right) / len(eligible_left | eligible_right)
        if eligible_left or eligible_right
        else 0.0,
        spearman,
        top_k,
        overlap,
        overlap / top_k if len(ltop) == len(rtop) == top_k else None,
        len(set(left) ^ set(right)) / len(union) if union else 0.0,
        sum(abs(left[k] - right[k]) for k in keys) / len(keys) if keys else None,
    )

"""Exact declared later truth, sealed TEST evidence and descriptive rank metrics."""

import math
from statistics import median
from typing import TYPE_CHECKING

from afre.cross_sectional.artifacts import (
    CrossSectionEvaluation,
    CrossSectionObservation,
    CrossSectionRanking,
    CrossSectionTruth,
    ICSeries,
    ScoreBucket,
    TruthRow,
)
from afre.cross_sectional.definitions import CrossSectionSpec
from afre.cross_sectional.groups import GroupMembership
from afre.cross_sectional.normalization import average
from afre.cross_sectional.ranks import rank_values
from afre.cross_sectional.schema import RankingLayer, TruthPolicy
from afre.cross_sectional.scoring import point_scaffold
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.splits import TestEvaluation
from afre.schema import require
from afre.statistical_models.artifacts import FittedModelArtifact, PointMetric
from afre.statistical_models.definitions import BaselineModelSpec
from afre.statistical_models.metrics import correlation
from afre.statistical_models.schema import MetricName, PredictionScope
from afre.target_engine.models import TargetVintage
from afre.target_engine.validation import target_known_by_cutoff
from afre.universe.models import UniverseSnapshot

if TYPE_CHECKING:
    from afre.cross_sectional.repository import CrossSectionRepository


def truth_for(
    repo: "CrossSectionRepository",
    ranking: CrossSectionRanking,
    targets: tuple[tuple[str, str | None], ...],
    cutoff_ns: int,
    available_ns: int,
    policy: TruthPolicy,
    seals: tuple[TestEvaluation, ...],
) -> CrossSectionTruth:
    spec = repo.resolve(CrossSectionSpec, ranking.spec_id)
    lookup = dict(targets)
    require(
        len(lookup) == len(targets)
        and set(lookup) == {e.security.fingerprint for e in ranking.entries},
        "truth requires exact eligible security grid",
    )
    require(ranking.available_ns <= cutoff_ns, "ranking unavailable at evaluation")
    require(len(targets) <= repo.cross_section_bounds.truths, "cross-sectional truth bound")
    rows = []
    used_seals: set[str] = set()
    for entry in ranking.entries:
        observation = repo.resolve(CrossSectionObservation, entry.observation_id)
        scaffold = (
            point_scaffold(repo, observation.source_id) if observation.source_id else None
        )
        sample = (
            repo.resolve(ResearchSample, scaffold.input.sample_id)
            if scaffold and scaffold.input.sample_id
            else None
        )
        target_id = lookup[entry.security.fingerprint]
        if target_id:
            target = repo.resolve(TargetVintage, target_id)
            require(
                target.origin == observation.origin
                and target.definition == spec.identity.target,
                "truth full origin/target mismatch",
            )
            if sample is not None:
                require(sample.target_id == target_id, "truth must match pinned AFRE-4 sample")
            repo._validate_links(target)
        else:
            target = None
        usable = target is not None and target_known_by_cutoff(target, cutoff_ns)
        if scaffold and scaffold.input.scope is PredictionScope.TEST:
            model = repo.resolve(FittedModelArtifact, scaffold.model_artifact_id)
            base = repo.resolve(BaselineModelSpec, model.spec_id)
            seal = next((s for s in seals if s.fold_id == base.fold_id), None)
            require(
                seal is not None and seal.evaluated_ns == cutoff_ns,
                "TEST truth requires sealed evidence",
            )
            assert seal is not None
            require(
                not usable or sample is not None and sample.fingerprint in seal.sample_ids,
                "TEST truth outside exact seal",
            )
            used_seals.add(seal.fingerprint)
        require(
            policy is not TruthPolicy.REQUIRE_COMPLETE or entry.rank is None or usable,
            "complete truth policy failed",
        )
        rows.append(
            TruthRow(
                entry.security,
                target_id,
                sample.fingerprint if sample else None,
                target.value if usable and target else None,
                None,
                "available" if usable else "truth-unavailable-at-cutoff",
            )
        )
    require(used_seals == {s.fingerprint for s in seals}, "unused or duplicate TEST evidence")
    known = tuple((r.security.fingerprint, r.value) for r in rows if r.value is not None)
    realized = {s: rank for s, rank, _ in rank_values(known, spec.direction, spec.ties)}
    from dataclasses import replace

    return CrossSectionTruth(
        ranking.fingerprint,
        tuple(replace(r, realized_rank=realized.get(r.security.fingerprint)) for r in rows),
        policy,
        cutoff_ns,
        available_ns,
        tuple(used_seals),
    )


def selected_value(spec: CrossSectionSpec, ranking: CrossSectionRanking) -> dict[str, float]:
    return {
        e.security.fingerprint: value
        for e in ranking.entries
        if e.rank is not None
        and (
            value := (
                e.raw
                if spec.ranking_layer is RankingLayer.RAW
                else e.normalized
                if spec.ranking_layer is RankingLayer.NORMALIZED
                else e.group_neutral
            )
        )
        is not None
    }


def evaluation_for(
    repo: "CrossSectionRepository",
    ranking: CrossSectionRanking,
    truth: CrossSectionTruth,
    top_k: int,
    bucket_count: int,
    available_ns: int,
) -> CrossSectionEvaluation:
    require(
        truth.ranking_id == ranking.fingerprint and top_k > 0 and bucket_count >= 2,
        "evaluation ranking/protocol",
    )
    require(available_ns >= truth.available_ns, "evaluation computation before truth")
    spec = repo.resolve(CrossSectionSpec, ranking.spec_id)
    scores = selected_value(spec, ranking)
    y = {r.security.fingerprint: r.value for r in truth.rows if r.value is not None}
    keys = tuple(sorted(set(scores) & set(y)))
    exclusions = tuple(
        (e.security.fingerprint, e.reason if e.rank is None else "truth-unavailable-at-cutoff")
        for e in ranking.entries
        if e.security.fingerprint not in keys
    )
    x_values, y_values = tuple(scores[s] for s in keys), tuple(y[s] for s in keys)
    pearson = correlation(x_values, y_values)
    xr = {
        s: r
        for s, r, _ in rank_values(
            tuple((s, scores[s]) for s in keys), spec.direction, spec.ties
        )
    }
    yr = {
        s: r
        for s, r, _ in rank_values(tuple((s, y[s]) for s in keys), spec.direction, spec.ties)
    }
    ranked_ic = correlation(tuple(xr[s] for s in keys), tuple(yr[s] for s in keys))
    rank_ic = PointMetric(
        MetricName.SPEARMAN_CORRELATION, ranked_ic.value, ranked_ic.state, len(keys)
    )
    by_group: dict[str, list[str]] = {}
    if spec.group is not None:
        for entry in ranking.entries:
            if entry.security.fingerprint in keys:
                o = repo.resolve(CrossSectionObservation, entry.observation_id)
                if o.group_id:
                    g = repo.resolve(GroupMembership, o.group_id)
                    by_group.setdefault(g.group_id, []).append(entry.security.fingerprint)
    # Pooled, sample-intersection group demeaning on both axes, never current taxonomy.
    gx, gy, group_keys = [], [], []
    for members in by_group.values():
        if len(members) >= (spec.group.minimum_count if spec.group else 2):
            mx, my = (
                average(tuple(scores[s] for s in members)),
                average(tuple(y[s] for s in members)),
            )
            for s in members:
                gx.append(scores[s] - mx)
                gy.append(y[s] - my)
                group_keys.append(s)
    group_ic = correlation(tuple(gx), tuple(gy))
    # Exact K only with N>=2K. Boundary ties split by canonical stable ID explicitly.
    ordered = sorted(keys, key=lambda s: (xr[s], s))
    sufficient = len(keys) >= 2 * top_k
    top, bottom = (
        tuple(ordered[:top_k]) if sufficient else (),
        tuple(ordered[-top_k:]) if sufficient else (),
    )
    top_mean = average(tuple(y[s] for s in top)) if top else None
    bottom_mean = average(tuple(y[s] for s in bottom)) if bottom else None
    buckets = []
    if len(keys) >= bucket_count:
        # Ascending quality: worst bucket first; balanced sizes differ by at most one.
        worst = tuple(reversed(ordered))
        for i in range(bucket_count):
            ids = worst[i * len(keys) // bucket_count : (i + 1) * len(keys) // bucket_count]
            buckets.append(ScoreBucket(i, ids, average(tuple(y[s] for s in ids))))
    monotone = (
        sum(
            (
                a.mean_truth <= b.mean_truth
                if spec.direction.value == "higher_better"
                else a.mean_truth >= b.mean_truth
            )
            for a, b in zip(buckets, buckets[1:], strict=False)
        )
        / (len(buckets) - 1)
        if buckets
        else None
    )
    return CrossSectionEvaluation(
        ranking.fingerprint,
        truth.fingerprint,
        keys,
        exclusions,
        pearson,
        rank_ic,
        group_ic,
        tuple(sorted(group_keys)),
        top_k,
        top,
        bottom,
        top_mean,
        bottom_mean,
        top_mean - bottom_mean if top_mean is not None and bottom_mean is not None else None,
        bucket_count,
        tuple(buckets),
        monotone,
        truth.cutoff_ns,
        available_ns,
    )


def series_for(
    repo: "CrossSectionRepository", evaluation_ids: tuple[str, ...], rank_ic: bool
) -> ICSeries:
    require(
        0 < len(evaluation_ids) <= repo.cross_section_bounds.series
        and len(set(evaluation_ids)) == len(evaluation_ids),
        "IC series count",
    )
    pairs = []
    template = None
    for identity in evaluation_ids:
        evaluation = repo.resolve(CrossSectionEvaluation, identity)
        ranking = repo.resolve(CrossSectionRanking, evaluation.ranking_id)
        spec = repo.resolve(CrossSectionSpec, ranking.spec_id)
        signature = (
            spec.identity.target,
            spec.score,
            spec.direction,
            spec.ties,
            spec.normalization,
            spec.group,
            spec.ranking_layer,
            spec.missing,
            spec.maximum_missing_fraction,
            spec.identity.eligibility_policy_id,
            spec.approved_delivery_attestors,
            repo.resolve(UniverseSnapshot, spec.identity.snapshot_id).definition,
        )
        require(template is None or template == signature, "incompatible IC series")
        template = signature
        metric = evaluation.rank_ic if rank_ic else evaluation.pearson
        pairs.append(
            (
                spec.identity.anchor_origin.timestamp_ns,
                spec.identity.fingerprint,
                identity,
                metric.value,
            )
        )
    pairs.sort()
    values = tuple(v for _, _, _, v in pairs if v is not None)
    mean = average(values) if values else None
    return ICSeries(
        tuple(i for _, _, i, _ in pairs),
        rank_ic,
        tuple(k for _, k, _, _ in pairs),
        len(pairs),
        len(values),
        mean,
        float(median(values)) if values else None,
        math.hypot(*(v - mean for v in values)) / math.sqrt(len(values))
        if values and mean is not None
        else None,
        sum(v > 0 for v in values) / len(values) if values else None,
    )

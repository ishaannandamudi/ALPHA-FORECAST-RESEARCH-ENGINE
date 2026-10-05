"""Explicit later truth with identical expert-vs-mixture sample/vintage intersections."""

from dataclasses import replace
from typing import TYPE_CHECKING

from afre.mixture.artifacts import (
    MatchedExpertComparison,
    MixtureComponent,
    MixtureDistribution,
    MixtureEvaluation,
    MixtureEvaluationPair,
    MixtureForecast,
)
from afre.mixture.definitions import ExpertSet
from afre.mixture.experts import ExpertForecastBinding
from afre.mixture.probabilistic import mixture_scores
from afre.probabilistic.artifacts import ProbabilityScore
from afre.probabilistic.definitions import ThresholdRequest
from afre.probabilistic.scoring import aggregate_scores
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.research_datasets.splits import TestEvaluation
from afre.schema import require
from afre.statistical_models.artifacts import PointMetric
from afre.statistical_models.metrics import point_metrics
from afre.statistical_models.schema import MetricState
from afre.target_engine.models import TargetVintage
from afre.target_engine.validation import target_known_by_cutoff

if TYPE_CHECKING:
    from afre.mixture.repository import MixtureRepository


def score_mean(
    groups: tuple[tuple[ProbabilityScore, ...], ...],
) -> tuple[ProbabilityScore, ...]:
    return aggregate_scores(groups, groups[0]) if groups else ()


def metric_deltas(
    left: tuple[PointMetric, ...], right: tuple[PointMetric, ...]
) -> tuple[PointMetric, ...]:
    return tuple(
        PointMetric(
            a.name,
            a.value - b.value if a.value is not None and b.value is not None else None,
            MetricState.AVAILABLE
            if a.value is not None and b.value is not None
            else a.state
            if a.value is None
            else b.state,
            a.sample_count,
        )
        for a, b in zip(left, right, strict=True)
    )


def evaluation_for(
    repo: "MixtureRepository",
    ids: tuple[str, ...],
    cutoff_ns: int,
    available_ns: int,
    seal: TestEvaluation | None,
    thresholds: tuple[ThresholdRequest, ...] = (),
) -> MixtureEvaluation:
    require(
        0 < len(ids) <= repo.mixture_bounds.forecasts and len(set(ids)) == len(ids),
        "mixture evaluation count/duplicates",
    )
    require(
        len(thresholds) <= 256 and len(set(thresholds)) == len(thresholds),
        "mixture evaluation threshold bound/duplicates",
    )
    thresholds = tuple(sorted(thresholds, key=lambda t: (t.value, t.comparison.value)))
    forecasts = tuple(repo.resolve(MixtureForecast, i) for i in sorted(ids))
    first = forecasts[0]
    require(
        all(
            (f.request.expert_set_id, f.request.gate_id, f.request.fold_id, f.partition)
            == (
                first.request.expert_set_id,
                first.request.gate_id,
                first.request.fold_id,
                first.partition,
            )
            for f in forecasts
        ),
        "mixture evaluation comparable exact gate/set/fold/partition",
    )
    require(
        len({f.request.sample_id for f in forecasts}) == len(forecasts),
        "mixture evaluation unique samples",
    )
    require(
        (seal is not None) == (first.partition is Partition.TEST), "mixture TEST seal required"
    )
    if seal:
        require(
            seal.fold_id == first.request.fold_id and seal.evaluated_ns == cutoff_ns,
            "mixture exact TEST seal",
        )
    pairs, excluded = [], []
    grouped: dict[str, list[MixtureEvaluationPair]] = {}
    for f in forecasts:
        require(f.available_ns <= cutoff_ns, "mixture unavailable at evaluation cutoff")
        sample = repo.resolve(ResearchSample, f.request.sample_id)
        target = repo.resolve(TargetVintage, sample.target_id) if sample.target_id else None
        if target is None or not target_known_by_cutoff(target, cutoff_ns):
            excluded.append((f.fingerprint, "truth-unavailable-at-cutoff"))
            continue
        require(
            target.origin == f.origin
            and target.definition.fingerprint == f.target_definition_id
            and (seal is None or sample.fingerprint in seal.sample_ids),
            "mixture exact truth/TEST evidence",
        )
        assert target.value is not None
        scores = (
            mixture_scores(
                f.distribution, target.value, thresholds, repo.mixture_bounds.work_cells
            )
            if f.distribution
            else ()
        )
        pair = MixtureEvaluationPair(
            f.fingerprint,
            sample.fingerprint,
            target.fingerprint,
            f.origin.timestamp_ns,
            f.value,
            target.value,
            tuple((c.expert_id, c.value) for c in f.contributions),
            scores,
        )
        pairs.append(pair)
        for cohort in (
            "gate:" + f.gating_mode.value,
            "missingness:"
            + (
                "missing"
                if any(c.reason != "available" for c in f.contributions)
                else "complete"
            ),
            "fallback:" + ("used" if f.fallback_id else "unused"),
        ):
            grouped.setdefault(cohort, []).append(pair)
    experts = repo.resolve(ExpertSet, first.request.expert_set_id)
    by_id = {f.fingerprint: f for f in forecasts}
    comparisons = []
    for expert_id in experts.expert_ids:
        matched = tuple(p for p in pairs if dict(p.experts)[expert_id] is not None)
        truth = tuple(p.truth for p in matched)
        values = tuple(dict(p.experts)[expert_id] for p in matched)
        mixture_metrics = point_metrics(tuple(p.mixture for p in matched), truth)
        expert_metrics = point_metrics(tuple(v for v in values if v is not None), truth)
        mixture_groups, expert_groups = [], []
        for p in matched:
            f = by_id[p.forecast_id]
            contribution = next(c for c in f.contributions if c.expert_id == expert_id)
            binding = repo.resolve(ExpertForecastBinding, contribution.binding_id or "")
            if f.distribution and binding.distribution:
                single = MixtureDistribution(
                    (
                        MixtureComponent(
                            expert_id, binding.fingerprint, 1.0, binding.distribution
                        ),
                    )
                )
                mixture_groups.append(p.probability_scores)
                expert_groups.append(
                    mixture_scores(single, p.truth, thresholds, repo.mixture_bounds.work_cells)
                )
        mix_scores, expert_scores = (
            score_mean(tuple(mixture_groups)),
            score_mean(tuple(expert_groups)),
        )
        probability_deltas = tuple(
            replace(
                a,
                value=a.value - b.value
                if a.value is not None and b.value is not None
                else None,
                state=a.state if a.value is None else b.state,
            )
            for a, b in zip(mix_scores, expert_scores, strict=True)
        )
        comparisons.append(
            MatchedExpertComparison(
                expert_id,
                tuple((p.sample_id, p.target_id) for p in matched),
                mixture_metrics,
                expert_metrics,
                metric_deltas(mixture_metrics, expert_metrics),
                mix_scores,
                expert_scores,
                probability_deltas,
            )
        )
    return MixtureEvaluation(
        experts.fingerprint,
        first.request.gate_id,
        first.request.fold_id,
        first.partition,
        tuple(sorted(ids)),
        tuple(pairs),
        tuple(excluded),
        point_metrics(tuple(p.mixture for p in pairs), tuple(p.truth for p in pairs)),
        tuple(comparisons),
        tuple(
            (
                name,
                point_metrics(
                    tuple(p.mixture for p in members), tuple(p.truth for p in members)
                ),
            )
            for name, members in sorted(grouped.items())
        ),
        score_mean(tuple(p.probability_scores for p in pairs if p.probability_scores)),
        cutoff_ns,
        available_ns,
        seal.fingerprint if seal else None,
        thresholds,
    )

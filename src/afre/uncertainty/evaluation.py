"""Exact later truth and native TEST seals; assessment cannot fit uncertainty methods."""

from typing import TYPE_CHECKING

from afre.event_conditioned.artifacts import EventConditionedForecast
from afre.event_conditioned.events import EventReference
from afre.mixture.evaluation import score_mean
from afre.regime_conditioned.artifacts import RegimeConditionedForecast
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.research_datasets.splits import TestEvaluation
from afre.schema import require
from afre.statistical_models.linear_algebra import finite, total
from afre.target_engine.models import TargetVintage
from afre.target_engine.validation import target_known_by_cutoff
from afre.uncertainty.artifacts import ForecastUncertaintyDecomposition, UncertaintyInterval
from afre.uncertainty.definitions import UncertaintySpec
from afre.uncertainty.diagnostics import buckets_for, error_for
from afre.uncertainty.evaluation_artifacts import (
    UncertaintyComparison,
    UncertaintyCoverage,
    UncertaintyEvaluation,
    UncertaintyEvaluationPair,
    UncertaintyEvaluationSpec,
)
from afre.uncertainty.schema import IdentifiabilityStatus as Status
from afre.uncertainty.scoring import scores_for
from afre.uncertainty.sources import source_for

if TYPE_CHECKING:
    from afre.uncertainty.repository import UncertaintyRepository


def coverage_for(
    pairs: tuple[UncertaintyEvaluationPair, ...], nominal: float, minimum: int
) -> UncertaintyCoverage:
    interval_pairs = tuple(p for p in pairs if p.covered is not None)
    variances = tuple(p.variance for p in pairs if p.variance is not None)
    count = len(interval_pairs)
    coverage = (
        sum(bool(p.covered) for p in interval_pairs) / count if count >= minimum else None
    )
    width = (
        total([p.interval_width for p in interval_pairs if p.interval_width is not None])
        / count
        if count >= minimum
        else None
    )
    mean_var = total(list(variances)) / len(variances) if len(variances) >= minimum else None
    status = (
        Status.IDENTIFIED
        if count >= minimum
        else Status.INSUFFICIENT_DATA
        if count
        else Status.UNAVAILABLE
    )
    return UncertaintyCoverage(
        tuple(p.sample_id for p in pairs),
        count,
        len(variances),
        nominal,
        coverage,
        coverage - nominal if coverage is not None else None,
        width,
        mean_var,
        status,
    )


def evaluation_for(
    repo: "UncertaintyRepository",
    ids: tuple[str, ...],
    policy: UncertaintyEvaluationSpec,
    cutoff_ns: int,
    available_ns: int,
    seal: TestEvaluation | None,
) -> UncertaintyEvaluation:
    require(
        0 < len(ids) <= repo.uncertainty_bounds.samples
        and len(set(ids)) == len(ids)
        and policy.bucket_count <= repo.uncertainty_bounds.buckets,
        "uncertainty evaluation bounds/duplicates",
    )
    decompositions = tuple(
        repo.resolve(ForecastUncertaintyDecomposition, i) for i in sorted(ids)
    )
    first = decompositions[0]
    require(
        all(
            d.target_id == first.target_id
            and d.horizon_id == first.horizon_id
            and d.fold_id == first.fold_id
            and d.partition is first.partition
            for d in decompositions
        ),
        "uncertainty evaluation target/horizon/fold/partition agreement",
    )
    require(
        len({d.sample_id for d in decompositions}) == len(decompositions),
        "one uncertainty method per evaluation sample",
    )
    require(
        (seal is not None) == (first.partition is Partition.TEST),
        "uncertainty TEST access seal required",
    )
    if seal:
        require(
            seal.fold_id == first.fold_id and seal.evaluated_ns == cutoff_ns,
            "uncertainty exact TEST seal",
        )
    specs = tuple(repo.resolve(UncertaintySpec, d.spec_id) for d in decompositions)
    levels = specs[0].interval_levels
    require(
        all(s.interval_levels == levels for s in specs),
        "evaluation exact nominal interval levels",
    )
    pairs: list[UncertaintyEvaluationPair] = []
    groups: dict[str, list[UncertaintyEvaluationPair]] = {}
    for decomposition in decompositions:
        repo._validate_links(decomposition)
        source = source_for(repo, decomposition.forecast_id)
        sample = repo.resolve(ResearchSample, decomposition.sample_id)
        require(
            sample.target_id is not None and decomposition.available_ns <= cutoff_ns,
            "uncertainty evaluation unavailable forecast/truth",
        )
        assert sample.target_id is not None
        target = repo.resolve(TargetVintage, sample.target_id)
        require(
            target_known_by_cutoff(target, cutoff_ns)
            and target.origin == decomposition.origin
            and target.definition.fingerprint == decomposition.target_id
            and (seal is None or sample.fingerprint in seal.sample_ids),
            "uncertainty exact known matched truth/TEST",
        )
        assert target.value is not None
        interval = repo.resolve(UncertaintyInterval, decomposition.interval_id)
        pair = UncertaintyEvaluationPair(
            policy.fingerprint,
            decomposition.fingerprint,
            source.artifact.fingerprint,
            sample.fingerprint,
            target.fingerprint,
            source.prediction,
            target.value,
            decomposition.total_variance,
            interval.width,
            interval.lower <= target.value <= interval.upper
            if interval.lower is not None and interval.upper is not None
            else None,
            scores_for(
                source,
                target.value,
                levels,
                policy.thresholds,
                repo.uncertainty_bounds.work_cells,
            ),
        )
        pairs.append(pair)
        names = {"horizon:" + decomposition.horizon_id, *decomposition.quality_states}
        if isinstance(source.artifact, EventConditionedForecast):
            for identity in source.artifact.event_ids:
                event = repo.resolve(EventReference, identity)
                names.add("event:" + event.event_class.value + ":" + event.subtype)
        elif (
            isinstance(source.artifact, RegimeConditionedForecast)
            and source.artifact.membership
        ):
            membership = source.artifact.membership
            names.add("regime-kind:" + membership.kind.value)
            names.update(
                "regime-active:" + s
                for s, w in zip(membership.states, membership.weights, strict=True)
                if w > 0
            )
        for name in sorted(names):
            groups.setdefault(name, []).append(pair)
        require(len(groups) <= repo.uncertainty_bounds.cohorts, "uncertainty cohort bound")
    result_pairs = tuple(pairs)
    buckets = buckets_for(result_pairs, policy.bucket_count, policy.minimum_count)
    nominal = levels[1] - levels[0]
    return UncertaintyEvaluation(
        policy.fingerprint,
        ids,
        result_pairs,
        first.fold_id,
        first.target_id,
        first.horizon_id,
        first.partition,
        levels,
        coverage_for(result_pairs, nominal, policy.minimum_count),
        tuple(
            (name, coverage_for(tuple(group), nominal, policy.minimum_count))
            for name, group in sorted(groups.items())
        ),
        buckets,
        error_for(result_pairs, buckets, policy.minimum_count),
        score_mean(tuple(p.scores for p in pairs)),
        cutoff_ns,
        available_ns,
        seal.fingerprint if seal else None,
    )


def comparison_for(
    repo: "UncertaintyRepository", left_id: str, right_id: str, available_ns: int
) -> UncertaintyComparison:
    left, right = (repo.resolve(UncertaintyEvaluation, i) for i in (left_id, right_id))
    grid = tuple(sorted((p.sample_id, p.target_id) for p in left.pairs))
    require(
        grid == tuple(sorted((p.sample_id, p.target_id) for p in right.pairs))
        and tuple((p.sample_id, p.truth) for p in left.pairs)
        == tuple((p.sample_id, p.truth) for p in right.pairs)
        and (
            left.fold_id,
            left.target_definition_id,
            left.horizon_id,
            left.partition,
            left.interval_levels,
            left.cutoff_ns,
        )
        == (
            right.fold_id,
            right.target_definition_id,
            right.horizon_id,
            right.partition,
            right.interval_levels,
            right.cutoff_ns,
        )
        and available_ns >= max(left.available_ns, right.available_ns),
        "uncertainty comparison exact truth/cutoff grid",
    )
    differences = tuple(
        finite(a - b) if a is not None and b is not None else None
        for a, b in (
            (left.coverage.empirical_coverage, right.coverage.empirical_coverage),
            (left.coverage.mean_width, right.coverage.mean_width),
            (left.coverage.mean_variance, right.coverage.mean_variance),
        )
    )
    return UncertaintyComparison(
        left_id, right_id, grid, differences[0], differences[1], differences[2], available_ns
    )

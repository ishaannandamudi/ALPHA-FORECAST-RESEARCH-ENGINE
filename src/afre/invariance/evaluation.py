"""Frozen later-truth assessment of declared environments with exact intersections."""

from typing import TYPE_CHECKING

from afre.invariance.artifacts import (
    EnvironmentCounts,
    EnvironmentMembership,
    EnvironmentMetric,
)
from afre.invariance.definitions import (
    EnvironmentDefinition,
    EnvironmentSet,
    StabilityAnalysisSpec,
)
from afre.invariance.forecasts import forecast_source
from afre.invariance.schema import (
    ComparabilityStatus,
    SampleIntersectionPolicy,
    StabilityMetricName,
    StabilitySampleMode,
    StabilityWeighting,
)
from afre.invariance.scoring import (
    POINT_NAMES,
    point_score,
    probabilistic_score,
    reliability_for,
    weighted_mean,
)
from afre.orthogonalization.source_policy import producer_key
from afre.regime_conditioned.memberships import effective_support
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.research_datasets.splits import TestEvaluation
from afre.schema import require
from afre.statistical_models.metrics import correlation
from afre.statistical_models.schema import MetricName
from afre.target_engine.models import TargetVintage
from afre.target_engine.validation import target_known_by_cutoff

if TYPE_CHECKING:
    from afre.invariance.repository import InvarianceRepository


def metric_for(
    repo: "InvarianceRepository",
    spec_id: str,
    environment_id: str,
    name: StabilityMetricName,
    membership_ids: tuple[str, ...],
    comparison_environment_ids: tuple[str, ...],
    cutoff_ns: int,
    available_ns: int,
    seal: TestEvaluation | None,
) -> EnvironmentMetric:
    spec = repo.resolve(StabilityAnalysisSpec, spec_id)
    envset = repo.resolve(EnvironmentSet, spec.environment_set_id)
    d = repo.resolve(EnvironmentDefinition, environment_id)
    require(
        name in spec.metrics and d in envset.definitions and available_ns >= cutoff_ns,
        "declared metric/environment/availability",
    )
    env_ids = tuple(sorted(comparison_environment_ids))
    require(
        len(set(env_ids)) == len(env_ids)
        and environment_id in env_ids
        and set(env_ids) <= {d.fingerprint for d in envset.definitions},
        "exact comparison environments",
    )
    if spec.intersection is SampleIntersectionPolicy.COMMON_INTERSECTION:
        require(
            set(env_ids) == {d.fingerprint for d in envset.definitions},
            "common intersection of entire declared set",
        )
    if spec.intersection is SampleIntersectionPolicy.PAIRWISE_INTERSECTION:
        require(len(env_ids) == 2, "pairwise exact two environments")
    require(
        len(membership_ids) == len(set(membership_ids))
        and len(membership_ids)
        == len(env_ids) * len(spec.sample_ids)
        <= repo.invariance_bounds.shift_cells,
        "complete bounded environment/sample grid",
    )
    memberships = tuple(repo.resolve(EnvironmentMembership, i) for i in sorted(membership_ids))
    grid = {(m.environment_id, m.sample_id): m for m in memberships}
    require(
        len(grid) == len(memberships)
        and set(grid) == {(e, s) for e in env_ids for s in spec.sample_ids}
        and all(m.available_ns <= cutoff_ns for m in memberships),
        "exact immutable membership grid/cutoff",
    )
    require(
        spec.weighting is StabilityWeighting.EXPLICIT_MEMBERSHIP
        or all(not m.soft for m in memberships),
        "soft membership requires explicit weighting",
    )
    sources = {
        s.sample_id: s
        for i in spec.forecast_ids
        if (s := forecast_source(repo, i)).available_ns <= cutoff_ns
    }
    partitions = {m.sample_id: m.partition for m in repo.fold_memberships(spec.fold_id)}
    test_samples = tuple(s for s in spec.sample_ids if partitions[s] is Partition.TEST)
    require(bool(test_samples) == (seal is not None), "explicit TEST assessment seal")
    if seal:
        require(
            seal.fold_id == spec.fold_id
            and seal.evaluated_ns == cutoff_ns
            and set(test_samples) <= set(seal.sample_ids),
            "TEST exact fold/samples/cutoff",
        )
    truth: dict[str, TargetVintage] = {}
    for identity in spec.sample_ids:
        sample = repo.resolve(ResearchSample, identity)
        if sample.target_id:
            t = repo.resolve(TargetVintage, sample.target_id)
            require(
                t.origin == sample.origin and t.definition == spec.target,
                "exact immutable sample truth/target/horizon",
            )
            if target_known_by_cutoff(t, cutoff_ns) and t.value is not None:
                truth[identity] = t
    selected = {e: {s for s in spec.sample_ids if grid[e, s].weight > 0} for e in env_ids}
    included = selected[environment_id] & sources.keys() & truth.keys()
    if spec.intersection is not SampleIntersectionPolicy.PER_ENVIRONMENT_NATIVE:
        included &= selected[env_ids[0]].intersection(*(selected[e] for e in env_ids[1:]))
    sample_ids = tuple(sorted(included))
    fs = tuple(sources[s] for s in sample_ids)
    ys = tuple(v for s in sample_ids if (v := truth[s].value) is not None)
    ws = tuple(grid[environment_id, s].weight for s in sample_ids)
    n_eff = effective_support(ws)
    counts = EnvironmentCounts(
        len(spec.sample_ids),
        len(selected[environment_id]),
        len(sample_ids),
        len(spec.sample_ids) - len(sample_ids),
        len(selected[environment_id] - (sources.keys() & truth.keys())),
        len(selected[environment_id] & truth.keys()),
        n_eff,
    )
    minimum = max(
        spec.minimum_count, d.minimum_count, d.window.minimum_count if d.window else 1
    )
    reliability: tuple[tuple[float, float, int, float | None, float | None], ...]
    value, status, reason, reliability = (
        None,
        ComparabilityStatus.INSUFFICIENT_DATA,
        "minimum-count-or-effective-support",
        (),
    )
    if len(sample_ids) >= minimum and n_eff + spec.tolerance >= minimum:
        status, reason = ComparabilityStatus.COMPARABLE, "exact-declared-metric"
        ps = tuple(s.prediction for s in fs)
        if name in POINT_NAMES:
            value, reason = point_score(name, ps, ys, ws)
        elif name is StabilityMetricName.PREDICTION_MEAN:
            value = weighted_mean(ps, ws)
        elif name in (StabilityMetricName.PEARSON_IC, StabilityMetricName.RANK_IC):
            require(
                spec.sample_mode is StabilitySampleMode.SAME_ORIGIN_CROSS_SECTION,
                "IC requires explicit same-origin cross-section mode",
            )
            if any(m.soft for m in memberships):
                reason = "weighted-IC-not-supported"
            else:
                groups: dict[tuple[int, str, str, str], list[int]] = {}
                for i, s in enumerate(fs):
                    key = (
                        s.origin.timestamp_ns,
                        s.origin.universe_id,
                        s.origin.market_session_id,
                        s.origin.build_context,
                    )
                    groups.setdefault(key, []).append(i)
                require(
                    len(groups) == len({s.origin.timestamp_ns for s in fs}),
                    "same-time different universe/origin contexts cannot be pooled",
                )
                scores = tuple(
                    correlation(
                        tuple(ps[i] for i in indexes),
                        tuple(ys[i] for i in indexes),
                        MetricName.PEARSON_CORRELATION
                        if name is StabilityMetricName.PEARSON_IC
                        else MetricName.SPEARMAN_CORRELATION,
                    ).value
                    if len(indexes) >= minimum
                    else None
                    for _, indexes in sorted(groups.items())
                )
                valid = tuple(v for v in scores if v is not None)
                if valid:
                    value = weighted_mean(valid, (1.0,) * len(valid))
                    status = (
                        ComparabilityStatus.COMPARABLE
                        if len(valid) == len(scores)
                        else ComparabilityStatus.PARTIALLY_COMPARABLE
                    )
                    reason = (
                        "equal-origin-IC-mean"
                        if len(valid) == len(scores)
                        else "insufficient-or-constant-origin-excluded-explicitly"
                    )
                else:
                    status, reason = (
                        ComparabilityStatus.INSUFFICIENT_DATA,
                        "no-origin-meets-IC-count-or-variance",
                    )
        elif name in (StabilityMetricName.ECE, StabilityMetricName.MCE):
            reliability, ece, mce = reliability_for(fs, ys, ws, spec)
            value = ece if name is StabilityMetricName.ECE else mce
            reason = (
                "fixed-bin-reliability-no-refit"
                if value is not None
                else "probability-semantics-unavailable"
            )
        elif name in (
            StabilityMetricName.PREDICTIVE_VARIANCE,
            StabilityMetricName.EXPERT_DISAGREEMENT,
            StabilityMetricName.COMPONENT_SHARE,
        ):
            from afre.invariance.uncertainty import uncertainty_score

            uncertainty_values, reason = uncertainty_score(repo, spec, fs, name)
            if uncertainty_values is not None:
                value = weighted_mean(uncertainty_values, ws)
        else:
            score_name = (
                StabilityMetricName.COVERAGE
                if name is StabilityMetricName.COVERAGE_ERROR
                else name
            )
            scores_p = tuple(
                probabilistic_score(score_name, s, y, spec, repo.invariance_bounds.shift_cells)
                for s, y in zip(fs, ys, strict=True)
            )
            if all(v is not None for v in scores_p):
                value = weighted_mean(tuple(v for v in scores_p if v is not None), ws)
                if name is StabilityMetricName.COVERAGE_ERROR:
                    value = abs(value - (spec.interval_levels[1] - spec.interval_levels[0]))
            else:
                reason = "law-interval-or-marginal-semantics-unavailable"
        if value is None and status is ComparabilityStatus.COMPARABLE:
            status = ComparabilityStatus.UNAVAILABLE
        if value is not None and counts.missing > 0:
            status, reason = (
                ComparabilityStatus.PARTIALLY_COMPARABLE,
                "declared-intersection-or-missing-truth-forecast",
            )
    return EnvironmentMetric(
        spec_id,
        environment_id,
        membership_ids,
        env_ids,
        name,
        value,
        status,
        reason,
        sample_ids,
        tuple(s.artifact.fingerprint for s in fs),
        tuple(truth[s].fingerprint for s in sample_ids),
        tuple(zip(sample_ids, ws, strict=True)),
        counts,
        spec.target.fingerprint,
        spec.target.horizon.fingerprint,
        producer_key(repo, spec.forecast_ids[0]),
        minimum,
        cutoff_ns,
        available_ns,
        seal.fingerprint if seal else None,
        reliability,
    )

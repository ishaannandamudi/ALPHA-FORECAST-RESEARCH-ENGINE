"""Compatible environment deltas, explicit degradation orientation, descriptive trends."""

from math import fsum
from typing import TYPE_CHECKING

from afre.invariance.artifacts import (
    EnvironmentMetric,
    ForecastDegradation,
    StabilityComparison,
    StabilityTrend,
)
from afre.invariance.definitions import EnvironmentDefinition, StabilityAnalysisSpec
from afre.invariance.schema import (
    ComparabilityStatus,
    SampleIntersectionPolicy,
    StabilityMetricName,
)
from afre.schema import require
from afre.statistical_models.linear_algebra import finite

if TYPE_CHECKING:
    from afre.invariance.repository import InvarianceRepository


def score_policy(s: StabilityAnalysisSpec) -> tuple[object, ...]:
    return (
        s.target,
        s.fold_id,
        s.weighting,
        s.sample_mode,
        s.minimum_count,
        s.interval_levels,
        s.pinball_level,
        s.threshold,
        s.reliability_edges,
        s.tolerance,
        s.implementation_version,
    )


def comparison_for(
    repo: "InvarianceRepository",
    left_id: str,
    right_id: str,
    available_ns: int,
    cross_model: bool = False,
) -> StabilityComparison:
    a, b = repo.resolve(EnvironmentMetric, left_id), repo.resolve(EnvironmentMetric, right_id)
    sa, sb = (
        repo.resolve(StabilityAnalysisSpec, a.spec_id),
        repo.resolve(StabilityAnalysisSpec, b.spec_id),
    )
    require(available_ns >= max(a.available_ns, b.available_ns), "comparison availability")
    compatible = (
        a.name is b.name
        and score_policy(sa) == score_policy(sb)
        and a.minimum_count == b.minimum_count
        and a.truth_cutoff_ns == b.truth_cutoff_ns
        and sa.intersection is sb.intersection
        and (a.producer_ids == b.producer_ids or cross_model)
    )
    if cross_model:
        from afre.calibration.artifacts import CalibratedForecast
        from afre.invariance.forecasts import forecast_source

        left_source, right_source = (
            forecast_source(repo, sa.forecast_ids[0]),
            forecast_source(repo, sb.forecast_ids[0]),
        )
        compatible = compatible and type(left_source.artifact) is type(right_source.artifact)
        if isinstance(left_source.artifact, CalibratedForecast):
            compatible = (
                compatible
                and isinstance(right_source.artifact, CalibratedForecast)
                and left_source.artifact.state_id == right_source.artifact.state_id
            )
    status, reason, delta, relative = (
        ComparabilityStatus.INCOMPARABLE,
        "target-horizon-score-model-or-cutoff-mismatch",
        None,
        None,
    )
    if compatible and sa.intersection is not SampleIntersectionPolicy.PER_ENVIRONMENT_NATIVE:
        compatible = (
            a.sample_ids == b.sample_ids
            and a.target_ids == b.target_ids
            and a.comparison_environment_ids == b.comparison_environment_ids
        )
        reason = "exact-common-truth-intersection-mismatch"
    if compatible:
        if a.value is None or b.value is None:
            status = (
                ComparabilityStatus.INSUFFICIENT_DATA
                if ComparabilityStatus.INSUFFICIENT_DATA in (a.status, b.status)
                else ComparabilityStatus.UNAVAILABLE
            )
            reason = "source-metric-insufficient-or-unavailable"
        else:
            delta = finite(b.value - a.value)
            relative = finite(delta / abs(a.value)) if abs(a.value) > sa.tolerance else None
            native_different = a.sample_ids != b.sample_ids or a.target_ids != b.target_ids
            status = (
                ComparabilityStatus.PARTIALLY_COMPARABLE
                if native_different
                or any(m.status is ComparabilityStatus.PARTIALLY_COMPARABLE for m in (a, b))
                else ComparabilityStatus.COMPARABLE
            )
            reason = (
                "native-cohorts-differ-descriptive-only"
                if native_different
                else "exact-compatible-samples"
            )
    return StabilityComparison(
        left_id,
        right_id,
        a.spec_id,
        b.spec_id,
        (a.environment_id, b.environment_id),
        a.name,
        sa.intersection,
        cross_model,
        status,
        reason,
        delta,
        relative,
        available_ns,
    )


def degradation_for(repo: "InvarianceRepository", comparison_id: str) -> ForecastDegradation:
    c = repo.resolve(StabilityComparison, comparison_id)
    a = repo.resolve(StabilityAnalysisSpec, c.left_spec_id)
    b = repo.resolve(StabilityAnalysisSpec, c.right_spec_id)
    require(
        a.baseline_environment_id == b.baseline_environment_id == c.environment_ids[0],
        "baseline predeclared before evaluation",
    )
    higher_worse = {
        StabilityMetricName.MAE,
        StabilityMetricName.MSE,
        StabilityMetricName.RMSE,
        StabilityMetricName.CRPS,
        StabilityMetricName.NLL,
        StabilityMetricName.BRIER,
        StabilityMetricName.PINBALL,
        StabilityMetricName.COVERAGE_ERROR,
        StabilityMetricName.ECE,
        StabilityMetricName.MCE,
    }
    lower_worse = {
        StabilityMetricName.R_SQUARED,
        StabilityMetricName.PEARSON_IC,
        StabilityMetricName.RANK_IC,
        StabilityMetricName.PEARSON,
        StabilityMetricName.SPEARMAN,
        StabilityMetricName.SIGN_ACCURACY,
    }
    orientation = (
        "higher-is-worse"
        if c.name in higher_worse
        else "lower-is-worse"
        if c.name in lower_worse
        else "descriptive-only"
    )
    return ForecastDegradation(
        c.fingerprint,
        c.environment_ids[0],
        c.environment_ids[1],
        c.name,
        c.delta,
        orientation,
        c.status,
        c.available_ns,
    )


def trend_for(
    repo: "InvarianceRepository", metric_ids: tuple[str, ...], available_ns: int
) -> StabilityTrend:
    require(
        2 <= len(metric_ids) <= repo.invariance_bounds.windows
        and len(set(metric_ids)) == len(metric_ids),
        "bounded trend metrics",
    )
    ms = tuple(repo.resolve(EnvironmentMetric, i) for i in metric_ids)
    require(
        len({m.environment_id for m in ms}) == len(ms)
        and len({m.spec_id for m in ms}) == 1
        and len({m.name for m in ms}) == 1
        and available_ns >= max(m.available_ns for m in ms),
        "trend one exact spec/metric/windows",
    )
    envs = {m.environment_id: repo.resolve(EnvironmentDefinition, m.environment_id) for m in ms}
    require(
        all(d.window is not None for d in envs.values()), "trend declared time windows only"
    )
    ordered = tuple(
        sorted(
            ms,
            key=lambda m: (
                w.start_ns if (w := envs[m.environment_id].window) else 0,
                m.environment_id,
            ),
        )
    )
    centers = tuple(
        d.window.start_ns + d.window.end_ns
        for m in ordered
        if (d := envs[m.environment_id]).window is not None
    )
    status, reason, slope, monotonic = (
        ComparabilityStatus.INSUFFICIENT_DATA,
        "missing-or-insufficient-window-metric",
        None,
        "unavailable",
    )
    if all(m.value is not None for m in ordered):
        x0 = centers[0]
        xs = tuple((c - x0) / 2 for c in centers)
        values = tuple(float(m.value) for m in ordered if m.value is not None)
        mean_x, mean_y = fsum(xs) / len(xs), fsum(values) / len(values)
        denominator = fsum((x - mean_x) ** 2 for x in xs)
        if denominator:
            slope = finite(
                fsum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values, strict=True))
                / denominator
            )
            increasing = all(a <= b for a, b in zip(values, values[1:], strict=False))
            decreasing = all(a >= b for a, b in zip(values, values[1:], strict=False))
            monotonic = (
                "constant"
                if increasing and decreasing
                else "nondecreasing"
                if increasing
                else "nonincreasing"
                if decreasing
                else "nonmonotonic"
            )
            status, reason = (
                ComparabilityStatus.PARTIALLY_COMPARABLE,
                "descriptive-window-center-slope-overlap-and-cohort-effects-unadjusted",
            )
        else:
            status, reason = ComparabilityStatus.INCOMPARABLE, "identical-window-centers"
    return StabilityTrend(
        ordered[0].spec_id,
        tuple(m.fingerprint for m in ordered),
        tuple(m.environment_id for m in ordered),
        slope,
        monotonic,
        status,
        reason,
        available_ns,
    )

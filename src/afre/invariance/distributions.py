"""Type7 quantiles and exact empirical CDF distance; no causal or significance claims."""

from math import fsum, hypot, sqrt
from statistics import fmean, pstdev
from typing import TYPE_CHECKING

from afre.invariance.artifacts import (
    DistributionSummary,
    EnvironmentMembership,
    FeatureShiftDiagnostic,
)
from afre.invariance.definitions import (
    EnvironmentDefinition,
    EnvironmentSet,
    StabilityAnalysisSpec,
)
from afre.invariance.schema import ComparabilityStatus, SampleIntersectionPolicy
from afre.orthogonalization.definitions import SignalReference
from afre.orthogonalization.signals import SignalObservation
from afre.research_datasets.preprocessing import quantile
from afre.schema import require
from afre.statistical_models.linear_algebra import finite

if TYPE_CHECKING:
    from afre.invariance.repository import InvarianceRepository


def empirical_ks(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    require(bool(left) and bool(right), "KS needs nonempty distributions")
    for v in (*left, *right):
        finite(v)
    a, b = sorted(left), sorted(right)
    i, j, distance = 0, 0, 0.0
    for x in sorted(set((*a, *b))):
        while i < len(a) and a[i] <= x:
            i += 1
        while j < len(b) and b[j] <= x:
            j += 1
        distance = max(distance, abs(i / len(a) - j / len(b)))
    return distance


def summary_for(
    values: tuple[tuple[str, float | None], ...], levels: tuple[float, ...]
) -> DistributionSummary:
    numbers = tuple(v for _, v in sorted(values) if v is not None)
    return DistributionSummary(
        tuple(s for s, _ in values),
        values,
        finite(fmean(numbers)) if numbers else None,
        finite(pstdev(numbers)) if numbers else None,
        tuple((q, finite(quantile(numbers, q)) if numbers else None) for q in levels),
        sum(v is None for _, v in values) / len(values) if values else 0.0,
    )


def shift_for(
    repo: "InvarianceRepository",
    spec_id: str,
    feature_reference_id: str,
    environment_ids: tuple[str, str],
    membership_ids: tuple[str, ...],
    observation_ids: tuple[str, ...],
    cutoff_ns: int,
    available_ns: int,
) -> FeatureShiftDiagnostic:
    s = repo.resolve(StabilityAnalysisSpec, spec_id)
    ref = repo.resolve(SignalReference, feature_reference_id)
    require(ref.fingerprint in s.feature_reference_ids, "feature shift selector predeclared")
    require(ref.target is None or ref.target == s.target, "feature shift target/horizon")
    envset = repo.resolve(EnvironmentSet, s.environment_set_id)
    require(
        len(set(environment_ids)) == 2
        and set(environment_ids) <= {e.fingerprint for e in envset.definitions},
        "shift declared environment pair",
    )
    require(
        len(set(membership_ids)) == len(membership_ids)
        and len(membership_ids) <= repo.invariance_bounds.shift_cells
        and len(set(observation_ids)) == len(observation_ids)
        and len(observation_ids) <= repo.invariance_bounds.samples
        and available_ns >= cutoff_ns,
        "shift bounds/duplicates/availability",
    )
    ms = tuple(repo.resolve(EnvironmentMembership, i) for i in sorted(membership_ids))
    grid = {(m.environment_id, m.sample_id): m for m in ms}
    require(
        set(grid) == {(e, i) for e in environment_ids for i in s.sample_ids}
        and len(grid) == len(ms)
        and all(m.available_ns <= cutoff_ns for m in ms),
        "shift exact frozen membership grid",
    )
    obs = tuple(repo.resolve(SignalObservation, i) for i in sorted(observation_ids))
    require(
        len({o.sample_id for o in obs}) == len(obs)
        and all(
            o.reference_id == ref.fingerprint
            and o.sample_id in s.sample_ids
            and o.available_ns <= cutoff_ns
            and all(o.origin == grid[e, o.sample_id].origin for e in environment_ids)
            for o in obs
        ),
        "feature shift exact source/origin/reference",
    )
    values = {o.sample_id: o.value for o in obs}
    pools = [{i for i in s.sample_ids if grid[e, i].weight > 0} for e in environment_ids]
    if s.intersection is SampleIntersectionPolicy.COMMON_INTERSECTION:
        require(
            len(envset.definitions) == 2,
            "feature pair common policy requires whole declared set",
        )
    if s.intersection is not SampleIntersectionPolicy.PER_ENVIRONMENT_NATIVE:
        pools = [pools[0] & pools[1]] * 2
    left, right = tuple(
        summary_for(tuple((i, values.get(i)) for i in sorted(pool)), s.quantile_levels)
        for pool in pools
    )
    definitions = tuple(repo.resolve(EnvironmentDefinition, e) for e in environment_ids)
    minimum = max(
        s.minimum_count,
        *(max(d.minimum_count, d.window.minimum_count if d.window else 1) for d in definitions),
    )
    a, b = (
        tuple(v for _, v in left.values if v is not None),
        tuple(v for _, v in right.values if v is not None),
    )
    status, reason = (
        ComparabilityStatus.COMPARABLE,
        "descriptive-input-shift-Type7-population-std-exact-KS",
    )
    mean = std = standardized = ks = distance = None
    shifts: tuple[tuple[float, float | None], ...] = tuple((q, None) for q in s.quantile_levels)
    if any(m.soft for m in ms):
        status, reason = (
            ComparabilityStatus.INCOMPARABLE,
            "weighted-distribution-distance-not-supported",
        )
    elif min(len(a), len(b)) < minimum:
        status, reason = ComparabilityStatus.INSUFFICIENT_DATA, "minimum-observed-feature-count"
    else:
        assert (
            left.mean is not None
            and right.mean is not None
            and left.std is not None
            and right.std is not None
        )
        mean, std = finite(right.mean - left.mean), finite(right.std - left.std)
        pooled = hypot(left.std, right.std) / sqrt(2)
        standardized = finite(mean / pooled) if pooled > s.tolerance else None
        ks = empirical_ks(a, b)
        shifts = tuple(
            (q, finite(float(y) - float(x)))
            for (q, x), (_, y) in zip(left.quantiles, right.quantiles, strict=True)
            if x is not None and y is not None
        )
        distance = finite(fsum(abs(v) for _, v in shifts if v is not None) / len(shifts))
    return FeatureShiftDiagnostic(
        spec_id,
        feature_reference_id,
        environment_ids,
        membership_ids,
        observation_ids,
        left,
        right,
        status,
        reason,
        mean,
        std,
        shifts,
        right.missing_fraction - left.missing_fraction,
        standardized,
        ks,
        distance,
        cutoff_ns,
        available_ns,
    )

"""Frozen window admission and independent drift, performance and health decisions."""

from contextlib import nullcontext
from statistics import fmean, pvariance
from typing import TYPE_CHECKING

from afre.health.artifacts import HealthMetric, HealthObservation, ModelHealthSnapshot
from afre.health.calibration import calibration_score
from afre.health.definitions import (
    HealthDiagnosticRequest,
    HealthRule,
    HealthSpec,
    MonitoredArtifactReference,
)
from afre.health.drift import distribution_pair
from afre.health.errors import error_score, truth_for
from afre.health.probabilities import event_probability, interval_for
from afre.health.rules import classify
from afre.health.schema import (
    TRUTH_DIAGNOSTICS,
    HealthIntersection,
    HealthPairKey,
    HealthStatistic,
    HealthStatus,
)
from afre.health.schema import HealthDiagnostic as D
from afre.health.vectors import VECTOR_KINDS, vector_pair
from afre.health.windows import MonitoringWindow
from afre.invariance.artifacts import EnvironmentMembership
from afre.schema import ContractError, require
from afre.statistical_models.linear_algebra import finite

if TYPE_CHECKING:
    from afre.health.repository import HealthRepository

LATER_DIAGNOSTICS = TRUTH_DIAGNOSTICS | frozenset(
    {D.GROSS_EDGE, D.COST, D.NET_EDGE, D.TURNOVER, D.BREAK_EVEN_COST, D.INCREMENTAL_VALUE}
)
SCALAR_COLUMNS = {
    D.PREDICTIVE_VARIANCE: "predictive_variance",
    D.INTERVAL_WIDTH: "prediction",
    D.UNCERTAINTY_VARIANCE: "total_variance",
    D.FUSION_DOMINANCE: "dominance",
    D.EFFECTIVE_SOURCE_COUNT: "effective_count",
    D.WEIGHT_ENTROPY: "entropy",
    D.GROSS_EDGE: "gross",
    D.COST: "cost",
    D.NET_EDGE: "net",
    D.TURNOVER: "turnover",
    D.BREAK_EVEN_COST: "break_even",
    D.SEQUENCE_DECAY: "sequence_decay",
    D.SEQUENCE_STATE_NORM: "state_norm",
    D.INTERCEPT: "intercept",
    D.RESIDUAL_VARIANCE_RATIO: "prediction",
    D.RAW_REFERENCE_CORRELATION: "prediction",
}


def pair_key(spec: HealthSpec, row: HealthObservation) -> str:
    return (
        row.security_id if spec.pair_key is HealthPairKey.SECURITY else row.sample_id
    ) or row.source_id


def admitted(
    repo: "HealthRepository",
    spec: HealthSpec,
    window: MonitoringWindow,
    identities: tuple[str, ...],
    target_free: bool,
) -> tuple[tuple[HealthObservation, ...], tuple[tuple[str, str], ...]]:
    rows = []
    exclusions = []
    memberships = {}
    if spec.environment_id:
        for identity in spec.membership_ids:
            m = repo.resolve(EnvironmentMembership, identity)
            require(m.environment_id == spec.environment_id, "health exact declared cohort")
            require(m.sample_id not in memberships, "duplicate health cohort sample")
            memberships[m.sample_id] = m
    for identity in identities:
        raw = repo.get(HealthObservation, identity)
        if target_free and "truth-dependent-native-evaluation" in raw.quality:
            exclusions.append(
                (identity, "incomparable-truth-dependent-source-on-target-free-path")
            )
            continue
        row = repo.resolve(HealthObservation, identity)
        if not window.contains(row.valid_ns):
            exclusions.append((identity, "outside-declared-valid-time-window"))
        elif row.available_ns > window.evaluation_cutoff_ns:
            exclusions.append((identity, "source-unavailable-at-window-cutoff"))
        elif spec.environment_id and row.sample_id not in memberships:
            exclusions.append((identity, "missing-exact-cohort-membership"))
        elif spec.environment_id:
            assert row.sample_id is not None
            m = memberships[row.sample_id]
            if m.available_ns > window.evaluation_cutoff_ns:
                exclusions.append((identity, "cohort-unavailable-at-window-cutoff"))
            elif m.soft or m.weight not in (0.0, 1.0):
                exclusions.append((identity, "incomparable-soft-weighted-health-not-supported"))
            elif m.weight == 0:
                exclusions.append((identity, "outside-declared-cohort"))
            else:
                rows.append(row)
        else:
            rows.append(row)
    return tuple(rows), tuple(exclusions)


def _calculate(
    repo: "HealthRepository",
    spec: HealthSpec,
    request: HealthDiagnosticRequest,
    left: tuple[HealthObservation, ...],
    right: tuple[HealthObservation, ...],
    minimum: int,
) -> tuple[
    float | None,
    float | None,
    int,
    int,
    tuple[str, ...],
    tuple[tuple[str, str], ...],
    tuple[tuple[str, float | None], ...],
    str,
]:
    kind = request.kind
    if kind is D.SCORE_DISPERSION:

        def dispersion(rows: tuple[HealthObservation, ...]) -> float | None:
            vectors = tuple(
                tuple(v for k, v in row.values if k.startswith("score:") and v is not None)
                for row in rows
            )
            return (
                fmean(pvariance(v) ** 0.5 for v in vectors)
                if vectors and all(len(v) >= request.minimum_count for v in vectors)
                else None
            )

        return (
            dispersion(left),
            dispersion(right),
            len(left),
            len(right),
            (),
            (),
            (),
            "population-score-dispersion-per-native-cross-section",
        )
    if kind in VECTOR_KINDS:
        vector_a, vector_b, reason = vector_pair(request, left, right)
        return vector_a, vector_b, len(left), len(right), (), (), (), reason
    column = SCALAR_COLUMNS.get(kind, request.column)

    def selected(
        rows: tuple[HealthObservation, ...],
    ) -> tuple[tuple[HealthObservation, float], ...]:
        return tuple((r, v) for r in rows if (v := dict(r.values).get(column)) is not None)

    a, b = selected(left), selected(right)
    excluded = tuple(
        (r.fingerprint, "explicit-missing-column:" + column)
        for rows in (left, right)
        for r in rows
        if dict(r.values).get(column) is None
    )
    if kind is D.MISSINGNESS:
        return (
            sum(dict(r.values).get(column) is None for r in left) / len(left) if left else None,
            sum(dict(r.values).get(column) is None for r in right) / len(right)
            if right
            else None,
            len(left),
            len(right),
            (),
            (),
            (),
            "observed-missingness-fraction-no-zero-fill",
        )
    if kind is D.QUALITY_FRACTION:
        return (
            sum(request.column in r.quality for r in left) / len(left) if left else None,
            sum(request.column in r.quality for r in right) / len(right) if right else None,
            len(left),
            len(right),
            (),
            (),
            (),
            "explicit-quality-state-fraction",
        )
    if kind in TRUTH_DIAGNOSTICS:
        require(
            request.column == "prediction",
            "health truth scores exact native prediction column only",
        )
        windows = (spec.reference_window, spec.current_window)
        truth_ids = []
        errors = []
        results: list[float | None] = []
        details: list[tuple[str, float | None]] = []
        counts = []
        pools: list[tuple[tuple[HealthObservation, float, float], ...]] = []
        for group, window in zip((a, b), windows, strict=True):
            records: list[tuple[HealthObservation, float, float]] = []
            for row, prediction in group:
                target = truth_for(repo, spec, row, window.evaluation_cutoff_ns)
                if target is None or target.value is None:
                    errors.append(
                        (row.fingerprint, "truth-unavailable-or-unverified-at-window-cutoff")
                    )
                    continue
                truth_ids.append(target.fingerprint)
                records.append((row, prediction, target.value))
            pools.append(tuple(records))
        if spec.intersection is not HealthIntersection.NATIVE_PER_WINDOW:
            common = {pair_key(spec, r[0]) for r in pools[0]} & {
                pair_key(spec, r[0]) for r in pools[1]
            }
            errors.extend(
                (r[0].fingerprint, "outside-known-truth-intersection")
                for pool in pools
                for r in pool
                if pair_key(spec, r[0]) not in common
            )
            pools = [tuple(r for r in pool if pair_key(spec, r[0]) in common) for pool in pools]
        for j, truth_records in enumerate(pools):
            counts.append(len(truth_records))
            if len(truth_records) < minimum:
                results.append(None)
            elif kind in (D.CRPS, D.NLL, D.COVERAGE, D.COVERAGE_ERROR, D.ECE, D.MCE):
                value, extra = calibration_score(repo, request, truth_records)
                results.append(value)
                details.extend(
                    (f"{'reference' if j == 0 else 'current'}:{k}", v) for k, v in extra
                )
            else:
                results.append(error_score(request, truth_records))
        return (
            results[0],
            results[1],
            counts[0],
            counts[1],
            tuple(sorted(set(truth_ids))),
            tuple(errors) + excluded,
            tuple(details),
            "later-cutoff-native-truth;delta=current-minus-reference",
        )
    if min(len(a), len(b)) < minimum:
        return None, None, len(a), len(b), (), excluded, (), "minimum-observed-support"
    if kind in (D.THRESHOLD_PROBABILITY, D.INTERVAL_WIDTH):
        probability_pools = []
        for group in (a, b):
            values = []
            for row, _ in group:
                if kind is D.THRESHOLD_PROBABILITY:
                    value = event_probability(repo, row.source_id, request.threshold)
                else:
                    interval = interval_for(repo, row.source_id, request.interval_levels)
                    value = interval[1] - interval[0] if interval else None
                values.append(value)
            probability_pools.append(
                fmean(v for v in values if v is not None)
                if all(v is not None for v in values)
                else None
            )
        return (
            probability_pools[0],
            probability_pools[1],
            len(a),
            len(b),
            (),
            excluded,
            (),
            "exact-native-law-query-only",
        )
    av, bv = tuple(v for _, v in a), tuple(v for _, v in b)
    if kind in (D.RESIDUAL_VARIANCE_RATIO, D.RAW_REFERENCE_CORRELATION):
        from afre.statistical_models.metrics import correlation

        results = []
        for group in (a, b):
            pairs = tuple((v, dict(row.values).get(request.column)) for row, v in group)
            if any(raw is None for _, raw in pairs):
                results.append(None)
            else:
                base = tuple(float(raw) for _, raw in pairs if raw is not None)
                residual = tuple(v for v, _ in pairs)
                variance = pvariance(base)
                results.append(
                    pvariance(residual) / variance
                    if kind is D.RESIDUAL_VARIANCE_RATIO and variance > request.tolerance
                    else correlation(residual, base).value
                    if kind is D.RAW_REFERENCE_CORRELATION
                    else None
                )
        return (
            results[0],
            results[1],
            len(a),
            len(b),
            (),
            excluded,
            (),
            "explicit-residual-to-raw-or-reference;no-causal-attribution",
        )
    result_a, result_b = distribution_pair(request, av, bv)
    return (
        result_a,
        result_b,
        len(a),
        len(b),
        (),
        excluded,
        (),
        "descriptive-native-population-moments-Type7-KS;delta=current-minus-reference",
    )


def metric_for(
    repo: "HealthRepository",
    spec: HealthSpec,
    request: HealthDiagnosticRequest,
    available_ns: int,
) -> HealthMetric:
    cutoff = max(
        spec.reference_window.evaluation_cutoff_ns, spec.current_window.evaluation_cutoff_ns
    )
    require(
        available_ns >= cutoff, "health snapshot cannot be backdated before evaluation cutoff"
    )
    target_free = request.kind not in LATER_DIAGNOSTICS
    with repo.feature_only() if target_free else nullcontext():
        left, exc_a = admitted(
            repo, spec, spec.reference_window, spec.reference_observation_ids, target_free
        )
        right, exc_b = admitted(
            repo, spec, spec.current_window, spec.current_observation_ids, target_free
        )
        for rows in (left, right):
            samples = tuple(r.sample_id for r in rows if r.sample_id is not None)
            require(
                len(samples) == len(set(samples)),
                "health exact one observation per sample/window",
            )
        require(
            all(r.constructed_ns <= available_ns for r in (*left, *right)),
            "health construction after snapshot computation",
        )
        rule_id = dict(spec.rule_bindings).get(request.fingerprint)
        rule = repo.resolve(HealthRule, rule_id) if rule_id else None
        minimum = max(
            spec.minimum_count,
            request.minimum_count,
            spec.reference_window.minimum_count,
            spec.current_window.minimum_count,
            rule.minimum_count if rule else 1,
        )
        if spec.intersection is not HealthIntersection.NATIVE_PER_WINDOW:
            column = SCALAR_COLUMNS.get(request.kind, request.column)
            columns = (
                {r.column for r in spec.requests}
                if spec.intersection is HealthIntersection.COMMON_INTERSECTION
                else {column}
            )
            pools = [
                tuple(
                    row
                    for row in group
                    if request.kind in VECTOR_KINDS
                    or all(dict(row.values).get(c) is not None for c in columns)
                )
                for group in (left, right)
            ]
            common = {pair_key(spec, r) for r in pools[0]} & {
                pair_key(spec, r) for r in pools[1]
            }
            kept = [tuple(r for r in group if pair_key(spec, r) in common) for group in pools]
            dropped = tuple(
                (r.fingerprint, "outside-declared-sample-intersection")
                for r in (*left, *right)
                if r not in (*kept[0], *kept[1])
            )
            left, right = kept
            exc_a += dropped
        refs = tuple(
            repo.get(MonitoredArtifactReference, r.reference_id) for r in (*left, *right)
        )
        primary = repo.get(MonitoredArtifactReference, spec.reference_id)
        compatible = all(
            (r.target_id, r.horizon_id, r.unit, r.output_semantics)
            == (primary.target_id, primary.horizon_id, primary.unit, primary.output_semantics)
            for r in refs
        )
        parameter_kinds = VECTOR_KINDS | frozenset(
            {
                D.INTERCEPT,
                D.FUSION_DOMINANCE,
                D.EFFECTIVE_SOURCE_COUNT,
                D.WEIGHT_ENTROPY,
                D.SEQUENCE_DECAY,
            }
        )
        if request.kind in parameter_kinds:
            compatible = compatible and all(
                r.artifact_type == primary.artifact_type for r in refs
            )
            if primary.artifact_type == "CrossSectionRanking":
                from afre.cross_sectional.artifacts import CrossSectionRanking
                from afre.cross_sectional.definitions import CrossSectionSpec

                policies = tuple(
                    repo.get(
                        CrossSectionSpec, repo.get(CrossSectionRanking, r.artifact_id).spec_id
                    )
                    for r in (primary, *refs)
                )
                fields = (
                    "score",
                    "direction",
                    "ties",
                    "normalization",
                    "missing",
                    "maximum_missing_fraction",
                    "group",
                    "ranking_layer",
                    "membership_rule",
                    "implementation_version",
                    "approved_delivery_attestors",
                )
                compatible = (
                    compatible
                    and len({tuple(getattr(s, name) for name in fields) for s in policies}) == 1
                )
        compatible = compatible and (
            request.kind in parameter_kinds
            or all(r.producer_id == primary.producer_id for r in refs)
        )
        if request.kind in (
            D.INPUT_MEAN,
            D.INPUT_STD,
            D.INPUT_QUANTILE,
            D.INPUT_KS,
            D.STANDARDIZED_MEAN,
        ):
            compatible = compatible and all(
                "input-grid" in row.quality for row in (*left, *right)
            )
        incompatible_exclusion = any("incomparable" in why for _, why in (*exc_a, *exc_b))
        if not compatible or incompatible_exclusion:
            a = b = None
            na, nb = len(left), len(right)
            truths: tuple[str, ...] = ()
            extra: tuple[tuple[str, str], ...] = ()
            details: tuple[tuple[str, float | None], ...] = ()
            reason = (
                "incomparable-target-horizon-unit-semantics-or-unsupported-"
                "weighted/label-source"
            )
            status = HealthStatus.INCOMPARABLE
        else:
            try:
                a, b, na, nb, truths, extra, details, reason = _calculate(
                    repo, spec, request, left, right, minimum
                )
            except (OverflowError, ZeroDivisionError) as error:
                raise ContractError("health numerical overflow/undefined arithmetic") from error
            status = (
                HealthStatus.INSUFFICIENT_DATA
                if min(na, nb) < minimum
                else HealthStatus.INCOMPARABLE
                if "incomparable" in reason
                else HealthStatus.UNAVAILABLE
                if a is None or b is None
                else HealthStatus.HEALTHY
            )
        delta = finite(b - a) if a is not None and b is not None else None
        ratio = (
            finite(b / a)
            if a is not None and b is not None and abs(a) > request.tolerance
            else None
        )
        score = (
            b
            if rule and rule.statistic is HealthStatistic.CURRENT
            else ratio
            if rule and rule.statistic is HealthStatistic.RATIO
            else delta
        )
        if status is HealthStatus.HEALTHY:
            if rule is None:
                status, reason = (
                    HealthStatus.UNAVAILABLE,
                    "no-explicit-health-rule;no-default-threshold",
                )
            elif score is None:
                status, reason = HealthStatus.UNAVAILABLE, "undefined-requested-rule-statistic"
            else:
                status = classify(rule, score)
        excluded_ids = {i for i, _ in (*exc_a, *exc_b, *extra)}
        orientation = (
            "positive-delta-worse"
            if request.kind
            in (
                D.MAE,
                D.MSE,
                D.RMSE,
                D.CRPS,
                D.NLL,
                D.COVERAGE_ERROR,
                D.ECE,
                D.MCE,
                D.RANK_DISPLACEMENT,
                D.COST,
                D.TURNOVER,
            )
            else "positive-delta-better"
            if request.kind
            in (
                D.R_SQUARED,
                D.IC,
                D.RANK_IC,
                D.TOP_K_OVERLAP,
                D.SIGN_PERSISTENCE,
                D.GROSS_EDGE,
                D.NET_EDGE,
            )
            else "descriptive-change-only;direction-supplied-by-rule"
        )
        return HealthMetric(
            spec.fingerprint,
            request.fingerprint,
            request.kind,
            rule_id,
            spec.reference_window.fingerprint,
            spec.current_window.fingerprint,
            tuple(r.fingerprint for r in left),
            tuple(r.fingerprint for r in right),
            tuple(
                sorted(
                    {
                        r.sample_id
                        for r in left
                        if r.sample_id and r.fingerprint not in excluded_ids
                    }
                )
            ),
            tuple(
                sorted(
                    {
                        r.sample_id
                        for r in right
                        if r.sample_id and r.fingerprint not in excluded_ids
                    }
                )
            ),
            na,
            nb,
            a,
            b,
            delta,
            ratio,
            score,
            status,
            reason,
            (*exc_a, *exc_b, *extra),
            tuple(q for r in (*left, *right) for q in r.quality),
            truths,
            details,
            cutoff,
            available_ns,
            spec.test_evaluation_id,
            orientation,
        )


def snapshot_for(
    spec: HealthSpec, metrics: tuple[HealthMetric, ...], available_ns: int
) -> ModelHealthSnapshot:
    require(
        {m.request_id for m in metrics} == {r.fingerprint for r in spec.requests}
        and len(metrics) == len(spec.requests)
        and all(m.spec_id == spec.fingerprint for m in metrics),
        "health snapshot exact full declared metric set",
    )
    cutoff = max(
        spec.reference_window.evaluation_cutoff_ns, spec.current_window.evaluation_cutoff_ns
    )
    require(
        available_ns >= max(cutoff, *(m.available_ns for m in metrics)),
        "health snapshot availability floor",
    )
    status = next(s for s in spec.precedence if any(m.status is s for m in metrics))
    return ModelHealthSnapshot(
        spec.fingerprint,
        spec.reference_id,
        tuple(m.fingerprint for m in metrics),
        tuple(set(m.rule_id for m in metrics if m.rule_id)),
        status,
        cutoff,
        available_ns,
        (
            "explicit-WORST_STATUS;unknown-states-precede-severity;no-causal-"
            "profit-or-lifecycle-action"
        ),
    )

"""Exact native scores on the same global support; unsupported laws stay unavailable."""

from math import fsum
from statistics import fmean
from typing import TYPE_CHECKING

from afre.challenger.artifacts import (
    CommonMatchedEvidence,
    ParticipantMetricResult,
    ShadowForecast,
)
from afre.challenger.programs import ChallengeMetricRequest, ChallengeProgram
from afre.challenger.schema import COST_METRICS, DESCRIPTIVE, HIGHER_BETTER
from afre.challenger.schema import ChallengeMetric as M
from afre.challenger.schema import ChallengeStatus as S
from afre.fusion.probabilistic import FusionDistribution
from afre.health.probabilities import event_probability, interval_for, law_for, proper_score
from afre.probabilistic.artifacts import DistributionParameters
from afre.probabilistic.distributions import quantile
from afre.statistical_models.metrics import correlation, point_metrics, ranks
from afre.statistical_models.schema import MetricName
from afre.target_engine.models import TargetVintage

if TYPE_CHECKING:
    from afre.challenger.repository import ChallengeRepository

POINT_NAMES = {
    M.MAE: MetricName.MAE,
    M.MSE: MetricName.MSE,
    M.RMSE: MetricName.RMSE,
    M.R_SQUARED: MetricName.R_SQUARED,
    M.PEARSON: MetricName.PEARSON_CORRELATION,
    M.SPEARMAN: MetricName.SPEARMAN_CORRELATION,
    M.SIGN_ACCURACY: MetricName.DIRECTIONAL_ACCURACY,
}
RANKING = {M.IC, M.RANK_IC, M.RANK_DISPLACEMENT, M.TOP_K_OVERLAP}


def orientation(kind: M) -> str:
    return (
        "descriptive-only"
        if kind in DESCRIPTIVE
        else ("higher-is-better" if kind in HIGHER_BETTER else "lower-is-better")
    )


def rank_score(
    request: ChallengeMetricRequest, rows: tuple[tuple[ShadowForecast, float], ...]
) -> tuple[float | None, tuple[tuple[str, float], ...]]:
    scores = []
    for at in sorted({s.origin_ns for s, _ in rows}):
        group = tuple(
            sorted(
                (r for r in rows if r[0].origin_ns == at),
                key=lambda r: (r[0].security_id, r[0].sample_id),
            )
        )
        if len(group) < max(request.cross_section_minimum, request.top_k):
            return None, ()
        p = tuple(float(s.value) for s, _ in group if s.value is not None)
        y = tuple(y for _, y in group)
        if request.kind in (M.IC, M.RANK_IC):
            value = correlation(
                p,
                y,
                MetricName.SPEARMAN_CORRELATION
                if request.kind is M.RANK_IC
                else MetricName.PEARSON_CORRELATION,
            ).value
            if value is None:
                return None, ()
        elif request.kind is M.RANK_DISPLACEMENT:
            value = fmean(abs(a - b) for a, b in zip(ranks(p), ranks(y), strict=True))
        else:
            top_p = set(
                sorted(range(len(p)), key=lambda i: (-p[i], group[i][0].security_id))[
                    : request.top_k
                ]
            )
            top_y = set(
                sorted(range(len(y)), key=lambda i: (-y[i], group[i][0].security_id))[
                    : request.top_k
                ]
            )
            value = len(top_p & top_y) / request.top_k
        scores.append((str(at), value))
    return (fmean(v for _, v in scores), tuple(scores)) if scores else (None, ())


def probability_score(
    repo: "ChallengeRepository",
    request: ChallengeMetricRequest,
    rows: tuple[tuple[ShadowForecast, float], ...],
) -> float | None:
    values = []
    for shadow, truth in rows:
        if shadow.source_id.startswith("afre.ort_"):
            return None
        kind = request.kind
        value = None
        if kind in (M.CRPS, M.NLL):
            value = proper_score(repo, shadow.source_id, truth, kind is M.NLL)
        elif kind is M.BRIER:
            p = event_probability(repo, shadow.source_id, request.threshold)
            if p is not None:
                value = (p - float(truth > request.threshold)) ** 2
        elif kind is M.PINBALL:
            law, _ = law_for(repo, shadow.source_id)
            if isinstance(law, FusionDistribution) and len(law.components) == 1:
                law = law.components[0].distribution
            if isinstance(law, DistributionParameters):
                error = truth - quantile(law, request.quantile_level)
                value = max(
                    request.quantile_level * error, (request.quantile_level - 1) * error
                )
        elif kind in (M.COVERAGE, M.SHARPNESS):
            interval = interval_for(repo, shadow.source_id, request.interval_levels)
            if interval is None:
                law, _ = law_for(repo, shadow.source_id)
                if isinstance(law, FusionDistribution) and len(law.components) == 1:
                    native = law.components[0].distribution
                    interval = (
                        quantile(native, request.interval_levels[0]),
                        quantile(native, request.interval_levels[1]),
                    )
            if interval is not None:
                lo, hi = interval
                value = float(lo <= truth <= hi) if kind is M.COVERAGE else hi - lo
        if value is None:
            return None
        values.append(value)
    return fsum(values) / len(values) if values else None


def metric_for(
    repo: "ChallengeRepository",
    program: ChallengeProgram,
    common: CommonMatchedEvidence,
    participant_id: str,
    request: ChallengeMetricRequest,
) -> ParticipantMetricResult:
    shadows = tuple(repo.resolve(ShadowForecast, i) for i in common.shadow_ids)
    by_sample = {s.sample_id: s for s in shadows if s.participant_id == participant_id}
    rows = tuple(
        (by_sample[s], repo.resolve(TargetVintage, t).value) for s, t in common.assignments
    )
    valid = tuple((s, float(y)) for s, y in rows if y is not None)
    status, reason = common.status, common.reason
    value: float | None = None
    details: tuple[tuple[str, float], ...] = ()
    if status is S.AVAILABLE:
        if len(valid) < request.minimum_count:
            status, reason = S.INSUFFICIENT_DATA, "request-minimum-common-support"
        elif request.kind in COST_METRICS:
            from afre.challenger.costs import cost_score

            value, status, reason = cost_score(
                repo, program, common, participant_id, request.kind
            )
        elif request.kind in POINT_NAMES or request.kind in RANKING:
            if any(s.value is None for s, _ in valid):
                reason = "native-point-value-unavailable"
            elif (
                request.kind in POINT_NAMES
                and program.unit != "target-value:" + program.target_id
            ):
                status, reason = S.INCOMPARABLE, "point-error-requires-target-units"
            elif request.kind in RANKING:
                value, details = rank_score(request, valid)
                reason = (
                    "same-origin-cross-section"
                    if value is not None
                    else "undefined-or-small-cross-section"
                )
            else:
                value = next(
                    m.value
                    for m in point_metrics(
                        tuple(float(s.value) for s, _ in valid if s.value is not None),
                        tuple(y for _, y in valid),
                    )
                    if m.name is POINT_NAMES[request.kind]
                )
                reason = (
                    "exact-native-point-score"
                    if value is not None
                    else "undefined-native-point-score"
                )
        else:
            if program.unit != "target-value:" + program.target_id:
                status, reason = S.INCOMPARABLE, "probability-score-requires-target-units"
            else:
                value = probability_score(repo, request, valid)
                reason = (
                    "exact-native-law-score"
                    if value is not None
                    else "unsupported-exact-native-law"
                )
        if status is S.AVAILABLE and value is None:
            status = S.UNAVAILABLE
    return ParticipantMetricResult(
        program.fingerprint,
        participant_id,
        request.fingerprint,
        common.fingerprint,
        request.kind,
        program.target_id,
        program.horizon_id,
        program.unit,
        len(common.assignments),
        value,
        status,
        reason,
        tuple(s for s, _ in common.assignments),
        tuple(t for _, t in common.assignments),
        common.cutoff_ns,
        common.available_ns,
        orientation(request.kind),
        details,
    )

"""Descriptive weights, contributions, matched correlations and known-window drift."""

from math import fsum, log
from statistics import median
from typing import TYPE_CHECKING

from afre.mixture.artifacts import (
    ExpertDiagnostic,
    GateDriftDiagnostic,
    MixtureDiagnostics,
    MixtureEvaluation,
    MixtureForecast,
)
from afre.schema import require
from afre.statistical_models.metrics import correlation
from afre.statistical_models.schema import MetricName

if TYPE_CHECKING:
    from afre.mixture.repository import MixtureRepository


def diagnostics_for(repo: "MixtureRepository", evaluation_id: str) -> MixtureDiagnostics:
    evaluation = repo.resolve(MixtureEvaluation, evaluation_id)
    forecasts = tuple(repo.resolve(MixtureForecast, i) for i in evaluation.forecast_ids)
    experts = []
    ids = tuple(c.expert_id for c in forecasts[0].contributions)
    n = len(forecasts)
    for identity in ids:
        contributions = tuple(
            next(c for c in f.contributions if c.expert_id == identity) for f in forecasts
        )
        weights = tuple(c.effective_weight for c in contributions)
        values = tuple(c.contribution for c in contributions if c.contribution is not None)
        experts.append(
            ExpertDiagnostic(
                identity,
                fsum(weights) / n,
                median(weights),
                min(weights),
                max(weights),
                sum(w == 0 for w in weights) / n,
                sum(c.reason == "available" for c in contributions) / n,
                fsum(values) / len(values) if values else None,
                fsum(abs(v) for v in values) / len(values) if values else None,
                sum(c.effective_weight > 0 for c in contributions) / n,
            )
        )
    correlations = []
    for index, a in enumerate(ids):
        for b in ids[index + 1 :]:
            matched = tuple(
                p
                for p in evaluation.pairs
                if dict(p.experts)[a] is not None and dict(p.experts)[b] is not None
            )
            left = tuple(dict(p.experts)[a] for p in matched)
            right = tuple(dict(p.experts)[b] for p in matched)
            x, y = (
                tuple(v for v in left if v is not None),
                tuple(v for v in right if v is not None),
            )
            correlations.append(
                (
                    a,
                    b,
                    correlation(x, y),
                    correlation(
                        tuple(v - p.truth for v, p in zip(x, matched, strict=True)),
                        tuple(v - p.truth for v, p in zip(y, matched, strict=True)),
                    ),
                    fsum(abs(u - v) for u, v in zip(x, y, strict=True)) / len(x) if x else None,
                )
            )
    return MixtureDiagnostics(
        evaluation.forecast_ids,
        evaluation_id,
        tuple(experts),
        tuple(correlations),
        fsum(1 / fsum(c.effective_weight**2 for c in f.contributions) for f in forecasts) / n,
        fsum(
            -fsum(
                c.effective_weight * log(c.effective_weight)
                for c in f.contributions
                if c.effective_weight > 0
            )
            / log(len(ids))
            if len(ids) > 1
            else 0.0
            for f in forecasts
        )
        / n,
        sum(f.fallback_id is not None for f in forecasts) / n,
        sum(any(c.reason != "available" for c in f.contributions) for f in forecasts) / n,
    )


def drift_for(
    repo: "MixtureRepository",
    reference_id: str,
    current_id: str,
    cutoff_ns: int,
    minimum_count: int,
) -> GateDriftDiagnostic:
    reference, current = (
        repo.resolve(MixtureDiagnostics, reference_id),
        repo.resolve(MixtureDiagnostics, current_id),
    )
    a, b = (
        repo.resolve(MixtureEvaluation, reference.evaluation_id),
        repo.resolve(MixtureEvaluation, current.evaluation_id),
    )
    require(
        a.gate_id == b.gate_id
        and a.expert_set_id == b.expert_set_id
        and a.available_ns <= cutoff_ns
        and b.available_ns <= cutoff_ns,
        "drift exact gate/expert set/known windows",
    )
    windows = tuple(
        tuple(repo.resolve(MixtureForecast, i).origin.timestamp_ns for i in d.forecast_ids)
        for d in (reference, current)
    )
    require(max(windows[0]) < min(windows[1]), "drift ordered disjoint windows")
    enough = min(len(a.pairs), len(b.pairs)) >= minimum_count
    error_a, error_b = (
        next(m for m in a.metrics if m.name is MetricName.MAE),
        next(m for m in b.metrics if m.name is MetricName.MAE),
    )
    return GateDriftDiagnostic(
        reference_id,
        current_id,
        tuple(
            (y.expert_id, y.mean_weight - x.mean_weight)
            for x, y in zip(reference.experts, current.experts, strict=True)
        )
        if enough
        else (),
        tuple(
            (y.expert_id, y.availability_rate - x.availability_rate)
            for x, y in zip(reference.experts, current.experts, strict=True)
        )
        if enough
        else (),
        error_b.value - error_a.value
        if enough and error_a.value is not None and error_b.value is not None
        else None,
        cutoff_ns,
        minimum_count,
        "available" if enough else "insufficient-data",
    )

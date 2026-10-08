"""Exact matched prediction comparisons; PIT same-origin ranks use AFRE-9 conventions."""

from math import fsum
from typing import TYPE_CHECKING

from afre.cross_sectional.ranks import rank_values
from afre.cross_sectional.schema import RankDirection, RankTiePolicy
from afre.invariance.artifacts import EnvironmentMembership, PredictionStabilityDiagnostic
from afre.invariance.comparisons import score_policy
from afre.invariance.definitions import (
    EnvironmentDefinition,
    EnvironmentSet,
    StabilityAnalysisSpec,
)
from afre.invariance.forecasts import forecast_source
from afre.invariance.schema import ComparabilityStatus
from afre.schema import require
from afre.statistical_models.metrics import correlation
from afre.statistical_models.schema import MetricName

if TYPE_CHECKING:
    from afre.invariance.repository import InvarianceRepository


def predictions_for(
    repo: "InvarianceRepository",
    left_spec_id: str,
    right_spec_id: str,
    environment_id: str,
    membership_ids: tuple[str, ...],
    cutoff_ns: int,
    available_ns: int,
) -> PredictionStabilityDiagnostic:
    a, b = (
        repo.resolve(StabilityAnalysisSpec, left_spec_id),
        repo.resolve(StabilityAnalysisSpec, right_spec_id),
    )
    require(
        score_policy(a) == score_policy(b)
        and a.sample_ids == b.sample_ids
        and a.top_k == b.top_k
        and a.environment_set_id == b.environment_set_id
        and available_ns >= cutoff_ns,
        "prediction compatible policies/exact sample population",
    )
    definition = repo.resolve(EnvironmentDefinition, environment_id)
    envset = repo.resolve(EnvironmentSet, a.environment_set_id)
    require(definition in envset.definitions, "prediction environment in declared set")
    require(
        len(membership_ids) == len(set(membership_ids)) == len(a.sample_ids),
        "prediction membership bound/exact roster",
    )
    ms = tuple(repo.resolve(EnvironmentMembership, i) for i in sorted(membership_ids))
    require(
        all(
            m.environment_id == environment_id and m.available_ns <= cutoff_ns and not m.soft
            for m in ms
        )
        and {m.sample_id for m in ms} == set(a.sample_ids),
        "prediction exact hard causal membership grid",
    )
    left = {
        s.sample_id: s
        for i in a.forecast_ids
        if (s := forecast_source(repo, i)).available_ns <= cutoff_ns
    }
    right = {
        s.sample_id: s
        for i in b.forecast_ids
        if (s := forecast_source(repo, i)).available_ns <= cutoff_ns
    }
    ids = tuple(sorted({m.sample_id for m in ms if m.weight > 0} & left.keys() & right.keys()))
    require(
        all(
            left[i].origin == right[i].origin and left[i].target == right[i].target for i in ids
        ),
        "prediction exact matched full origins/target",
    )
    ps, qs = tuple(left[i].prediction for i in ids), tuple(right[i].prediction for i in ids)
    pearson = spearman = difference = agreement = overlap = displacement = None
    status, reason = ComparabilityStatus.INSUFFICIENT_DATA, "minimum-matched-prediction-count"
    minimum = max(
        a.minimum_count,
        b.minimum_count,
        definition.minimum_count,
        definition.window.minimum_count if definition.window else 1,
    )
    if len(ids) >= minimum:
        pearson, spearman = (
            correlation(ps, qs).value,
            correlation(ps, qs, MetricName.SPEARMAN_CORRELATION).value,
        )
        difference = fsum(abs(p - q) for p, q in zip(ps, qs, strict=True)) / len(ids)
        agreement = sum(
            (p > 0) - (p < 0) == (q > 0) - (q < 0) for p, q in zip(ps, qs, strict=True)
        ) / len(ids)
        status, reason = (
            ComparabilityStatus.COMPARABLE,
            "exact-matched-predictions-no-model-selection",
        )
        contexts = {
            (
                left[i].origin.timestamp_ns,
                left[i].origin.universe_id,
                left[i].origin.market_session_id,
                left[i].origin.build_context,
            )
            for i in ids
        }
        if len(contexts) == 1 and a.top_k <= len(ids):
            pr = {
                i: rank
                for i, rank, _ in rank_values(
                    tuple(zip(ids, ps, strict=True)),
                    RankDirection.HIGHER_BETTER,
                    RankTiePolicy.AVERAGE_RANK,
                )
            }
            qr = {
                i: rank
                for i, rank, _ in rank_values(
                    tuple(zip(ids, qs, strict=True)),
                    RankDirection.HIGHER_BETTER,
                    RankTiePolicy.AVERAGE_RANK,
                )
            }
            # Top K uses identity tie breaks; displacement retains average ties.
            ptop = set(sorted(ids, key=lambda i: (-left[i].prediction, i))[: a.top_k])
            qtop = set(sorted(ids, key=lambda i: (-right[i].prediction, i))[: a.top_k])
            overlap, displacement = (
                len(ptop & qtop) / a.top_k,
                fsum(abs(pr[i] - qr[i]) for i in ids) / len(ids),
            )
        else:
            status, reason = (
                ComparabilityStatus.PARTIALLY_COMPARABLE,
                "temporal-predictions-comparable-ranks-require-one-exact-origin-and-valid-K",
            )
    return PredictionStabilityDiagnostic(
        left_spec_id,
        right_spec_id,
        membership_ids,
        environment_id,
        ids,
        tuple(left[i].artifact.fingerprint for i in ids),
        tuple(right[i].artifact.fingerprint for i in ids),
        pearson,
        spearman,
        difference,
        agreement,
        overlap,
        displacement,
        status,
        reason,
        cutoff_ns,
        available_ns,
    )

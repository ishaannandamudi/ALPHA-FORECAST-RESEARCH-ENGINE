"""Matched later truth, old proper scores and explicitly descriptive subgroups."""

from dataclasses import replace
from math import fsum, log
from typing import TYPE_CHECKING

from afre.event_conditioned.artifacts import EventConditionedForecast
from afre.probabilistic.artifacts import ProbabilisticForecast
from afre.probabilistic.definitions import ProbabilisticEvaluationProtocol
from afre.probabilistic.distributions import conditional_variance, expected_value, quantile
from afre.probabilistic.scoring import score_forecast
from afre.regime_conditioned.artifacts import (
    RegimeConditionedEvaluation,
    RegimeConditionedForecast,
    RegimeConditionedModel,
    RegimeConditionedSample,
    RegimeEvaluationPair,
    RegimeGroupMetric,
    RegimeSoftDiagnostic,
)
from afre.regime_conditioned.definitions import RegimeConditioningSpec
from afre.regime_conditioned.forecasts import native_base
from afre.regime_conditioned.matching import base_context
from afre.regime_conditioned.memberships import effective_support
from afre.regime_conditioned.regimes import RegimeTaxonomy
from afre.regime_conditioned.schema import RegimeMembershipKind
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.splits import TestEvaluation
from afre.schema import require
from afre.statistical_models.artifacts import PointMetric
from afre.statistical_models.metrics import point_metrics
from afre.statistical_models.schema import MetricState, PredictionScope
from afre.target_engine.models import TargetVintage
from afre.target_engine.validation import target_known_by_cutoff

if TYPE_CHECKING:
    from afre.regime_conditioned.repository import RegimeRepository


def evaluation_for(
    repo: "RegimeRepository",
    ids: tuple[str, ...],
    cutoff_ns: int,
    available_ns: int,
    seal: TestEvaluation | None,
) -> RegimeConditionedEvaluation:
    require(
        0 < len(ids) <= repo.regime_bounds.samples and len(set(ids)) == len(ids),
        "regime evaluation count/duplicates",
    )
    forecasts = tuple(repo.resolve(RegimeConditionedForecast, i) for i in sorted(ids))
    first = forecasts[0]
    model = repo.resolve(RegimeConditionedModel, first.model_id)
    spec = repo.resolve(RegimeConditioningSpec, model.spec_id)
    base_spec = base_context(repo, spec)
    base_first = native_base(repo, first.base_forecast_id)
    require(
        all(
            f.model_id == first.model_id
            and f.target_definition_id == first.target_definition_id
            and native_base(repo, f.base_forecast_id).input.scope is base_first.input.scope
            for f in forecasts
        ),
        "regime evaluation mixed model/horizon/partition",
    )
    require(
        len(
            {
                repo.resolve(RegimeConditionedSample, f.observation_id).sample_id
                for f in forecasts
            }
        )
        == len(forecasts),
        "matched comparison requires unique samples; evaluate overlap relations separately",
    )
    require(
        (seal is not None) == (base_first.input.scope is PredictionScope.TEST),
        "regime TEST access record required",
    )
    if seal:
        require(
            seal.fold_id == base_spec.fold_id and seal.evaluated_ns == cutoff_ns,
            "regime TEST evidence mismatch",
        )
    pairs, excluded, probability = [], [], []
    grouped: dict[str, list[RegimeEvaluationPair]] = {}
    counts: dict[str, int] = {
        s: 0 for s in ("matched", "unmatched", "stale", "invalid", "unsupported")
    }
    counts["eligible"] = len(forecasts)
    weighted: list[tuple[RegimeEvaluationPair, tuple[float, ...]]] = []
    entropies: list[float] = []
    low_confidence = 0
    for f in forecasts:
        require(f.available_ns <= cutoff_ns, "regime forecast unavailable at evaluation")
        o = repo.resolve(RegimeConditionedSample, f.observation_id)
        sample = repo.resolve(ResearchSample, o.sample_id)
        target = repo.resolve(TargetVintage, sample.target_id) if sample.target_id else None
        usable = target is not None and target_known_by_cutoff(target, cutoff_ns)
        if seal:
            require(
                not usable or sample.fingerprint in seal.sample_ids,
                "regime truth outside TEST seal",
            )
        counts[o.state] += 1
        if not usable:
            excluded.append((f.fingerprint, "truth-unavailable-at-cutoff"))
            continue
        assert target is not None and target.value is not None
        require(
            target.origin == f.origin and target.definition == spec.target,
            "regime truth exact target/origin",
        )
        repo._validate_links(target)
        pair = RegimeEvaluationPair(
            f.fingerprint,
            sample.fingerprint,
            target.fingerprint,
            f.base_value,
            f.value,
            target.value,
        )
        pairs.append(pair)
        if f.base_probability_id:
            raw = repo.resolve(ProbabilisticForecast, f.base_probability_id)
            assert f.distribution is not None
            view = replace(
                raw,
                distribution=f.distribution,
                quantiles=f.quantiles,
                threshold_probabilities=f.probabilities,
                expected_value=expected_value(f.distribution),
                median_value=quantile(f.distribution, 0.5),
                conditional_variance=conditional_variance(f.distribution),
            )
            supplied = repo.get_any(f.base_forecast_id)
            if isinstance(supplied, EventConditionedForecast):
                assert supplied.distribution is not None
                raw = replace(
                    raw,
                    distribution=supplied.distribution,
                    quantiles=supplied.quantiles,
                    threshold_probabilities=supplied.probabilities,
                    expected_value=expected_value(supplied.distribution),
                    median_value=quantile(supplied.distribution, 0.5),
                    conditional_variance=conditional_variance(supplied.distribution),
                )
            protocol = ProbabilisticEvaluationProtocol()
            probability.append(
                (
                    f.fingerprint,
                    score_forecast(raw, target.value, protocol)[0],
                    score_forecast(view, target.value, protocol)[0],
                )
            )
        group_keys = [
            "coverage:" + o.state,
            "horizon:" + spec.target.horizon.fingerprint,
            "transition:" + o.transition_status,
            "membership:" + (o.membership.kind.value if o.membership else "missing"),
        ]
        if o.membership:
            weighted.append((pair, o.membership.weights))
            if o.membership.kind is RegimeMembershipKind.HARD:
                group_keys.append("state:" + (o.membership.hard_state or "missing"))
            else:
                low_confidence += max(o.membership.weights) < spec.low_confidence_threshold
                entropies.append(-fsum(w * log(w) for w in o.membership.weights if w > 0))
        supplied = repo.get_any(f.base_forecast_id)
        if isinstance(supplied, EventConditionedForecast):
            group_keys.append("event-base:" + supplied.state)
        for key in group_keys:
            grouped.setdefault(key, []).append(pair)
    require(len(grouped) <= repo.regime_bounds.states + 32, "regime evaluation group bound")
    base_metrics = point_metrics(tuple(p.base for p in pairs), tuple(p.truth for p in pairs))
    conditioned_metrics = point_metrics(
        tuple(p.conditioned for p in pairs), tuple(p.truth for p in pairs)
    )
    deltas = tuple(
        PointMetric(
            a.name,
            a.value - b.value if a.value is not None and b.value is not None else None,
            MetricState.AVAILABLE
            if a.value is not None and b.value is not None
            else a.state
            if a.value is None
            else b.state,
            len(pairs),
        )
        for a, b in zip(conditioned_metrics, base_metrics, strict=True)
    )
    groups = tuple(
        RegimeGroupMetric(
            key,
            tuple(p.sample_id for p in ps),
            len(ps),
            point_metrics(tuple(p.base for p in ps), tuple(p.truth for p in ps))
            if len(ps) >= spec.minimum_evaluation_group
            else (),
            point_metrics(tuple(p.conditioned for p in ps), tuple(p.truth for p in ps))
            if len(ps) >= spec.minimum_evaluation_group
            else (),
            "available" if len(ps) >= spec.minimum_evaluation_group else "insufficient-data",
        )
        for key, ps in sorted(grouped.items())
    )
    diagnostics = []
    taxonomy = repo.resolve(RegimeTaxonomy, spec.taxonomy_id)
    for index, state in enumerate(taxonomy.states):
        weights = tuple(w[index] for _, w in weighted)
        total, support = fsum(weights), effective_support(weights)
        count = sum(w > 0 for w in weights)
        enough = (
            count >= spec.minimum_evaluation_group and support >= spec.minimum_effective_support
        )
        diagnostics.append(
            RegimeSoftDiagnostic(
                state,
                count,
                total / len(weighted) if weighted else 0.0,
                support,
                fsum(w[index] * abs(p.base - p.truth) for p, w in weighted) / total
                if enough
                else None,
                fsum(w[index] * abs(p.conditioned - p.truth) for p, w in weighted) / total
                if enough
                else None,
                "available" if enough else "insufficient-data",
            )
        )
    return RegimeConditionedEvaluation(
        model.fingerprint,
        ids,
        tuple(pairs),
        tuple(excluded),
        base_metrics,
        conditioned_metrics,
        deltas,
        groups,
        tuple(probability),
        tuple(diagnostics),
        low_confidence,
        fsum(entropies) / len(entropies) if entropies else None,
        tuple(sorted(counts.items())),
        seal.fingerprint if seal else None,
        cutoff_ns,
        available_ns,
    )

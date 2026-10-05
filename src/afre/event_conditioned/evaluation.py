"""Matched later truth, old proper scores and explicitly descriptive subgroups."""

from bisect import bisect_right
from dataclasses import replace
from typing import TYPE_CHECKING

from afre.event_conditioned.artifacts import (
    EventConditionedEvaluation,
    EventConditionedForecast,
    EventConditionedModel,
    EventConditionedObservation,
    EventEvaluationPair,
    EventGroupMetric,
    EventMatchSet,
)
from afre.event_conditioned.definitions import EventConditioningSpec
from afre.event_conditioned.events import EventReference
from afre.event_conditioned.matching import base_context
from afre.probabilistic.artifacts import ProbabilisticForecast
from afre.probabilistic.definitions import ProbabilisticEvaluationProtocol
from afre.probabilistic.distributions import conditional_variance, expected_value, quantile
from afre.probabilistic.scoring import score_forecast
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.splits import TestEvaluation
from afre.schema import require
from afre.statistical_models.artifacts import PointForecast, PointMetric
from afre.statistical_models.metrics import point_metrics
from afre.statistical_models.schema import MetricState, PredictionScope
from afre.target_engine.models import TargetVintage
from afre.target_engine.validation import target_known_by_cutoff

if TYPE_CHECKING:
    from afre.event_conditioned.repository import EventRepository


def evaluation_for(
    repo: "EventRepository",
    ids: tuple[str, ...],
    cutoff_ns: int,
    available_ns: int,
    seal: TestEvaluation | None,
) -> EventConditionedEvaluation:
    require(
        0 < len(ids) <= repo.event_bounds.samples and len(set(ids)) == len(ids),
        "event evaluation count/duplicates",
    )
    forecasts = tuple(repo.resolve(EventConditionedForecast, i) for i in sorted(ids))
    first = forecasts[0]
    model = repo.resolve(EventConditionedModel, first.model_id)
    spec = repo.resolve(EventConditioningSpec, model.spec_id)
    base_spec = base_context(repo, spec)
    base_first = repo.resolve(PointForecast, first.base_forecast_id)
    require(
        all(
            f.model_id == first.model_id
            and f.target_definition_id == first.target_definition_id
            and repo.resolve(PointForecast, f.base_forecast_id).input.scope
            is base_first.input.scope
            for f in forecasts
        ),
        "event evaluation mixed model/horizon/partition",
    )
    require(
        len(
            {
                repo.resolve(EventConditionedObservation, f.observation_id).sample_id
                for f in forecasts
            }
        )
        == len(forecasts),
        "matched comparison requires unique samples; evaluate overlap relations separately",
    )
    require(
        (seal is not None) == (base_first.input.scope is PredictionScope.TEST),
        "event TEST access record required",
    )
    if seal:
        require(
            seal.fold_id == base_spec.fold_id and seal.evaluated_ns == cutoff_ns,
            "event TEST evidence mismatch",
        )
    pairs, excluded, probability = [], [], []
    grouped: dict[str, list[EventEvaluationPair]] = {}
    affected = 0
    for f in forecasts:
        require(f.available_ns <= cutoff_ns, "event forecast unavailable at evaluation")
        o = repo.resolve(EventConditionedObservation, f.observation_id)
        sample = repo.resolve(ResearchSample, o.sample_id)
        target = repo.resolve(TargetVintage, sample.target_id) if sample.target_id else None
        usable = target is not None and target_known_by_cutoff(target, cutoff_ns)
        if seal:
            require(
                not usable or sample.fingerprint in seal.sample_ids,
                "event truth outside TEST seal",
            )
        affected += bool(f.event_ids)
        if not usable:
            excluded.append((f.fingerprint, "truth-unavailable-at-cutoff"))
            continue
        assert target is not None and target.value is not None
        require(
            target.origin == f.origin and target.definition == spec.window.target,
            "event truth exact target/origin",
        )
        repo._validate_links(target)
        pair = EventEvaluationPair(
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
            protocol = ProbabilisticEvaluationProtocol()
            probability.append(
                (
                    f.fingerprint,
                    score_forecast(raw, target.value, protocol)[0],
                    score_forecast(view, target.value, protocol)[0],
                )
            )
        match = repo.resolve(EventMatchSet, o.matches_id)
        group_keys = [
            "affected:" + str(bool(f.event_ids)),
            "overlap:"
            + ("multi" if len(match.distances) > 1 else "single" if f.event_ids else "none"),
            "horizon:" + spec.window.target.horizon.fingerprint,
        ]
        if o.event_id:
            event = repo.resolve(EventReference, o.event_id)
            group_keys.append("class:" + event.event_class.value)
            values = dict(o.values)
            for name, bins in (
                ("materiality", spec.materiality_bins),
                ("novelty", spec.novelty_bins),
                ("surprise", spec.surprise_bins),
            ):
                group_keys.append(
                    name
                    + ":"
                    + (
                        str(bisect_right(bins, values[name]))
                        if name in values
                        else "unconfigured"
                    )
                )
            assert o.distance is not None
            group_keys.append("age:" + str(bisect_right(spec.age_bins, o.distance)))
        for key in group_keys:
            grouped.setdefault(key, []).append(pair)
    require(len(grouped) <= repo.event_bounds.groups, "event evaluation group bound")
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
        EventGroupMetric(
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
    return EventConditionedEvaluation(
        model.fingerprint,
        ids,
        tuple(pairs),
        tuple(excluded),
        base_metrics,
        conditioned_metrics,
        deltas,
        groups,
        tuple(probability),
        seal.fingerprint if seal else None,
        cutoff_ns,
        available_ns,
        affected,
        len(forecasts),
        affected / len(forecasts),
    )

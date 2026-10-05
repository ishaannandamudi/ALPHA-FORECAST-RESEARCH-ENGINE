"""Truth-free application and explicit shape-preserving location translation."""

from dataclasses import replace
from typing import TYPE_CHECKING

from afre.event_conditioned.artifacts import (
    EventConditionedForecast,
    EventConditionedModel,
    EventConditionedObservation,
)
from afre.event_conditioned.definitions import EventConditioningSpec
from afre.event_conditioned.events import EventReference
from afre.event_conditioned.schema import EventModelFamily
from afre.probabilistic.artifacts import (
    DistributionParameters,
    ProbabilisticForecast,
    QuantileValue,
    ThresholdProbability,
)
from afre.probabilistic.distributions import quantile
from afre.probabilistic.schema import DistributionFamily
from afre.probabilistic.thresholds import threshold_probability
from afre.schema import require
from afre.statistical_models.artifacts import PointForecast
from afre.statistical_models.linear_algebra import dot, finite
from afre.statistical_models.schema import PredictionScope

if TYPE_CHECKING:
    from afre.event_conditioned.repository import EventRepository


def shifted_distribution(
    distribution: DistributionParameters, shift: float
) -> DistributionParameters:
    if distribution.family is DistributionFamily.QUANTILE_SET:
        return replace(
            distribution,
            location=finite(distribution.location + shift),
            quantile_values=tuple(
                replace(q, value=finite(q.value + shift)) for q in distribution.quantile_values
            ),
        )
    return replace(distribution, location=finite(distribution.location + shift))


def forecast_for(
    repo: "EventRepository",
    model: EventConditionedModel,
    observation: EventConditionedObservation,
    base_id: str,
    probability_id: str | None,
    computed_ns: int,
) -> EventConditionedForecast:
    spec = repo.resolve(EventConditioningSpec, model.spec_id)
    base = repo.resolve(PointForecast, base_id)
    require(
        observation.spec_id == spec.fingerprint
        and base.model_artifact_id == spec.base_model_id
        and base.input.origin == observation.origin
        and base.input.sample_id == observation.sample_id
        and base.input.scope is observation.scope
        and observation.scope is not PredictionScope.IN_SAMPLE
        and base.target_definition_id == spec.window.target.fingerprint
        and base.historical_admissible,
        "event forecast exact base/sample/target/partition",
    )
    repo._validate_links(base)
    repo._validate_links(observation)
    value, state = base.value, "unaffected"
    required = max(base.available_ns, model.available_ns)
    events: tuple[str, ...] = ()
    if observation.event_id:
        events = (observation.event_id,)
        event = repo.resolve(EventReference, observation.event_id)
        required = max(required, event.clocks.final_available_ns)
        for rule in spec.value_rules:
            attr = getattr(event, rule.key)
            assert attr is not None
            required = max(
                required,
                attr.available_ns if rule.key == "surprise" else attr.clocks.final_available_ns,
            )
        from afre.cross_sectional.external import ExternalSignal

        for i in observation.reaction_ids:
            required = max(required, repo.resolve(ExternalSignal, i).clocks.final_available_ns)
        if spec.family is EventModelFamily.EVENT_CLASS_OFFSET:
            record = next(
                (v for c, v, n in model.class_values if c == event.event_class.value), None
            )
            value, state = (
                (record, "conditioned")
                if record is not None
                else (base.value, "insufficient-class-data")
            )
        else:
            values = dict(observation.values)
            value, state = (
                finite(
                    dot((1.0, *(values[k] for k in model.feature_keys)), model.coefficients)
                ),
                "conditioned",
            )
    require(
        required <= computed_ns <= observation.origin.availability_cutoff_ns,
        "event forecast before inputs/model or after origin cutoff",
    )
    shift = finite(value - base.value)
    distribution = None
    qs: tuple[QuantileValue, ...] = ()
    ps: tuple[ThresholdProbability, ...] = ()
    if probability_id:
        raw = repo.resolve(ProbabilisticForecast, probability_id)
        require(
            raw.point_forecast_id == base_id
            and raw.target_definition_id == base.target_definition_id
            and raw.historical_admissible
            and raw.available_ns <= computed_ns,
            "event probability requires exact raw base",
        )
        repo._validate_links(raw)
        distribution = shifted_distribution(raw.distribution, shift)
        qs = tuple(
            QuantileValue(q.level, quantile(distribution, q.level)) for q in raw.quantiles
        )
        ps = tuple(
            ThresholdProbability(p.request, threshold_probability(distribution, p.request))
            for p in raw.threshold_probabilities
        )
    return EventConditionedForecast(
        spec.fingerprint,
        model.fingerprint,
        observation.fingerprint,
        base_id,
        base.input.origin,
        observation.security,
        base.target_definition_id,
        events,
        observation.reaction_ids,
        finite(value),
        base.value,
        shift,
        state,
        probability_id,
        distribution,
        qs,
        ps,
        computed_ns,
        computed_ns,
        True,
    )

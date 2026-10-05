"""Truth-free fixed-state application and exact distribution location translation."""

from math import fsum
from typing import TYPE_CHECKING

from afre.event_conditioned.artifacts import EventConditionedForecast
from afre.event_conditioned.forecasts import shifted_distribution
from afre.probabilistic.artifacts import (
    ProbabilisticForecast,
    QuantileValue,
    ThresholdProbability,
)
from afre.probabilistic.distributions import quantile
from afre.probabilistic.thresholds import threshold_probability
from afre.regime_conditioned.artifacts import (
    RegimeConditionedForecast,
    RegimeConditionedModel,
    RegimeConditionedSample,
)
from afre.regime_conditioned.definitions import RegimeConditioningSpec
from afre.regime_conditioned.regimes import RegimeSnapshot
from afre.regime_conditioned.schema import RegimeFallback, RegimeModelFamily
from afre.schema import require
from afre.statistical_models.artifacts import PointForecast
from afre.statistical_models.linear_algebra import finite
from afre.statistical_models.schema import PredictionScope

if TYPE_CHECKING:
    from afre.regime_conditioned.repository import RegimeRepository


def native_base(repo: "RegimeRepository", base_id: str) -> PointForecast:
    value = repo.get_any(base_id)
    require(
        isinstance(value, (PointForecast, EventConditionedForecast)),
        "regime requires native point or declared event base",
    )
    assert isinstance(value, (PointForecast, EventConditionedForecast))
    return (
        repo.resolve(PointForecast, value.base_forecast_id)
        if isinstance(value, EventConditionedForecast)
        else value
    )


def forecast_for(
    repo: "RegimeRepository",
    model: RegimeConditionedModel,
    observation: RegimeConditionedSample,
    base_id: str,
    probability_id: str | None,
    computed_ns: int,
) -> RegimeConditionedForecast:
    spec = repo.resolve(RegimeConditioningSpec, model.spec_id)
    base = native_base(repo, base_id)
    supplied = repo.get_any(base_id)
    event = supplied if isinstance(supplied, EventConditionedForecast) else None
    require(
        (event is not None) == (spec.event_model_id is not None)
        and (event is None or event.model_id == spec.event_model_id),
        "regime explicit event composition model",
    )
    require(
        observation.spec_id == spec.fingerprint
        and base.model_artifact_id == spec.base_model_id
        and base.input.origin == observation.origin
        and base.input.sample_id == observation.sample_id
        and base.input.scope is observation.scope
        and observation.scope is not PredictionScope.IN_SAMPLE
        and base.target_definition_id == spec.target.fingerprint
        and base.historical_admissible,
        "regime forecast exact base/sample/target/partition",
    )
    repo._validate_links(supplied)
    repo._validate_links(observation)
    base_value = event.value if event else base.value
    required = max(base.available_ns, model.available_ns, event.available_ns if event else 0)
    weights = observation.membership.weights if observation.membership else ()
    if observation.regime_snapshot_id:
        snapshot = repo.resolve(RegimeSnapshot, observation.regime_snapshot_id)
        required = max(required, snapshot.clocks.final_available_ns)
    usable = bool(weights) and all(
        w == 0 or f.value is not None for w, f in zip(weights, model.state_fits, strict=True)
    )
    if usable:
        estimate = finite(
            fsum(w * (f.value or 0.0) for w, f in zip(weights, model.state_fits, strict=True))
        )
        value = (
            estimate
            if spec.family is RegimeModelFamily.REGIME_TARGET_MEAN
            else finite(base_value + estimate)
        )
        state = "conditioned"
    else:
        require(spec.fallback is not RegimeFallback.FAIL, "regime fallback FAIL")
        value = (
            finite(base_value + model.global_offset)
            if spec.fallback is RegimeFallback.GLOBAL_OFFSET
            else base_value
        )
        state = "fallback:" + spec.fallback.value
    require(
        required <= computed_ns <= observation.origin.availability_cutoff_ns,
        "regime forecast before inputs/model or after origin cutoff",
    )
    shift = finite(value - base_value)
    distribution = None
    qs: tuple[QuantileValue, ...] = ()
    ps: tuple[ThresholdProbability, ...] = ()
    if probability_id:
        raw = repo.resolve(ProbabilisticForecast, probability_id)
        require(
            raw.point_forecast_id == base.fingerprint
            and raw.target_definition_id == spec.target.fingerprint
            and raw.historical_admissible
            and raw.available_ns <= computed_ns
            and (event is None or event.base_probability_id == probability_id),
            "regime probability exact raw/event base",
        )
        repo._validate_links(raw)
        original = event.distribution if event else raw.distribution
        require(original is not None, "event base lacks probability distribution")
        assert original is not None
        distribution = shifted_distribution(original, shift)
        qs = tuple(
            QuantileValue(q.level, quantile(distribution, q.level)) for q in raw.quantiles
        )
        ps = tuple(
            ThresholdProbability(p.request, threshold_probability(distribution, p.request))
            for p in raw.threshold_probabilities
        )
    return RegimeConditionedForecast(
        spec.fingerprint,
        model.fingerprint,
        observation.fingerprint,
        base_id,
        observation.origin,
        observation.security,
        spec.target.fingerprint,
        observation.regime_snapshot_id,
        observation.membership,
        finite(value),
        base_value,
        shift,
        state,
        probability_id,
        distribution,
        qs,
        ps,
        computed_ns,
        computed_ns,
        True,
        "base-event-regime-location-v1" if event else "base-regime-location-v1",
    )

"""Stable diagnostic policy and producer identity, separate from forecast origins."""

import json
from typing import TYPE_CHECKING

from afre.calibration.artifacts import CalibratedForecast
from afre.event_conditioned.artifacts import EventConditionedForecast
from afre.hashing import bytes_digest
from afre.mixture.artifacts import MixtureForecast
from afre.nonlinear.artifacts import NonlinearForecast
from afre.probabilistic.artifacts import ProbabilisticForecast
from afre.regime_conditioned.artifacts import RegimeConditionedForecast
from afre.schema import require
from afre.sequence.artifacts import SequenceForecast
from afre.statistical_models.artifacts import PointForecast
from afre.uncertainty.artifacts import UncertaintyComponent
from afre.uncertainty.definitions import UncertaintySpec

if TYPE_CHECKING:
    from afre.orthogonalization.repository import OrthogonalizationRepository


def producer_key(repo: "OrthogonalizationRepository", identity: str) -> tuple[str, ...]:
    value = repo.get_any(identity)
    if isinstance(value, PointForecast):
        return (value.model_artifact_id,)
    if isinstance(value, ProbabilisticForecast):
        return (value.model_artifact_id,)
    if isinstance(value, CalibratedForecast):
        return (value.state_id,)
    if isinstance(value, MixtureForecast):
        return (value.request.gate_id,)
    require(
        isinstance(
            value,
            (
                EventConditionedForecast,
                RegimeConditionedForecast,
                NonlinearForecast,
                SequenceForecast,
            ),
        ),
        "diagnostic requires supported forecast producer",
    )
    assert isinstance(
        value,
        (
            EventConditionedForecast,
            RegimeConditionedForecast,
            NonlinearForecast,
            SequenceForecast,
        ),
    )
    if isinstance(value, (EventConditionedForecast, RegimeConditionedForecast)):
        probability_id = value.base_probability_id
    else:
        probability_id = value.probability.base_forecast_id if value.probability else None
    law = (
        ()
        if probability_id is None
        else (repo.resolve(ProbabilisticForecast, probability_id).model_artifact_id,)
    )
    return (value.model_id, *law)


def diagnostic_policy_key(
    repo: "OrthogonalizationRepository",
    policy: UncertaintySpec,
    component: UncertaintyComponent,
) -> str:
    payload = {
        "producer": producer_key(repo, policy.forecast_id),
        "alternative_producers": sorted(
            producer_key(repo, i) for i in policy.alternative_forecast_ids
        ),
        "target": policy.target.fingerprint,
        "requests": tuple(r.fingerprint for r in policy.requests),
        "component": component.component.value,
        "measure": component.measure.value,
        "method": component.method,
        "status": component.status.value,
        "units": component.units,
        "covariance": policy.covariance_id,
        "closure": policy.closure.value,
        "interval_levels": policy.interval_levels,
        "minimum_count": policy.minimum_count,
        "tolerance": policy.tolerance,
        "seed": policy.seed,
        "calibration_policy": policy.calibration_policy,
        "identifiability_policy": policy.identifiability_policy,
        "implementation_version": policy.implementation_version,
    }
    return bytes_digest(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    )

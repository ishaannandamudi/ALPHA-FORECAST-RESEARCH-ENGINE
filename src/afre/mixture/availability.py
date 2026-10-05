"""Exact native resolution and receipt-aware external evidence; no truth reads."""

from typing import TYPE_CHECKING

from afre.cross_sectional.external import ExternalSignal
from afre.cross_sectional.schema import SignalQuality
from afre.event_conditioned.artifacts import (
    EventConditionedForecast,
    EventConditionedModel,
    EventConditionedObservation,
)
from afre.event_conditioned.definitions import EventConditioningSpec
from afre.feature_store.models import FeatureVintage
from afre.features import DataQuality, MissingState
from afre.mixture.experts import (
    ExpertForecastBinding,
    ExpertReference,
    ExternalExpertForecast,
    GatingFeatureReference,
)
from afre.mixture.schema import ExpertKind, ExpertOutput, ExpertQuality
from afre.probabilistic.artifacts import ProbabilisticForecast, ProbabilisticModelArtifact
from afre.probabilistic.definitions import ProbabilisticModelSpec
from afre.probabilistic.distributions import expected_value
from afre.regime_conditioned.artifacts import (
    RegimeConditionedForecast,
    RegimeConditionedModel,
    RegimeConditionedSample,
)
from afre.regime_conditioned.definitions import RegimeConditioningSpec
from afre.regime_conditioned.regimes import RegimeSnapshot
from afre.regime_conditioned.schema import RegimeQuality, RegimeStateSemantics
from afre.schema import require
from afre.statistical_models.artifacts import FittedModelArtifact, PointForecast
from afre.statistical_models.definitions import BaselineModelSpec
from afre.statistical_models.schema import PredictionScope

if TYPE_CHECKING:
    from afre.mixture.repository import MixtureRepository


def validate_expert(repo: "MixtureRepository", expert: ExpertReference) -> None:
    require(repo.get_any(expert.source.fingerprint) == expert.source, "expert source evidence")
    if expert.kind.value.startswith("external_"):
        require(
            expert.source.provenance.system == expert.provider
            and expert.source.provenance.source_version == expert.provider_version,
            "external expert producer provenance mismatch",
        )
        return
    if expert.kind is ExpertKind.AFRE_POINT:
        model = repo.resolve(FittedModelArtifact, expert.model_id)
        target = repo.resolve(BaselineModelSpec, model.spec_id).target
        available = model.available_ns
    elif expert.kind is ExpertKind.AFRE_PROBABILISTIC:
        probability = repo.resolve(ProbabilisticModelArtifact, expert.model_id)
        target = repo.resolve(ProbabilisticModelSpec, probability.spec_id).target
        available = probability.available_ns
    elif expert.kind is ExpertKind.AFRE_EVENT:
        event = repo.resolve(EventConditionedModel, expert.model_id)
        target = repo.resolve(EventConditioningSpec, event.spec_id).window.target
        available = event.available_ns
    else:
        regime = repo.resolve(RegimeConditionedModel, expert.model_id)
        target = repo.resolve(RegimeConditioningSpec, regime.spec_id).target
        available = regime.available_ns
    require(
        expert.target == target and expert.available_ns == available,
        "native expert target/model availability mismatch",
    )


def binding_for(
    repo: "MixtureRepository", expert: ExpertReference, forecast_id: str
) -> ExpertForecastBinding:
    validate_expert(repo, expert)
    value = repo.get_any(forecast_id)
    point = None
    distribution = None
    quality = ExpertQuality.VALID
    sample_id = None
    if expert.kind.value.startswith("external_"):
        require(isinstance(value, ExternalExpertForecast), "external forecast type mismatch")
        assert isinstance(value, ExternalExpertForecast)
        require(value.expert == expert, "external exact producer mismatch")
        origin, available, asof = value.origin, value.clocks.final_available_ns, value.as_of_ns
        point, distribution, quality = value.point, value.distribution, value.quality
    elif expert.kind is ExpertKind.AFRE_POINT:
        require(isinstance(value, PointForecast), "native point forecast required")
        assert isinstance(value, PointForecast)
        require(
            value.model_artifact_id == expert.model_id
            and value.historical_admissible
            and value.input.scope is not PredictionScope.IN_SAMPLE,
            "gate expert requires historically admissible native forecast",
        )
        origin, available, asof = (
            value.input.origin,
            value.available_ns,
            value.input.origin.timestamp_ns,
        )
        point, sample_id = value.value, value.input.sample_id
        require(value.target_definition_id == expert.target.fingerprint, "native point target")
    elif expert.kind is ExpertKind.AFRE_PROBABILISTIC:
        require(
            isinstance(value, ProbabilisticForecast), "native probabilistic forecast required"
        )
        assert isinstance(value, ProbabilisticForecast)
        require(
            value.model_artifact_id == expert.model_id and value.historical_admissible,
            "native probability producer/admissibility",
        )
        origin, available, asof = (
            value.input.origin,
            value.available_ns,
            value.input.origin.timestamp_ns,
        )
        distribution, sample_id = value.distribution, value.input.sample_id
        require(
            value.target_definition_id == expert.target.fingerprint, "native probability target"
        )
    else:
        expected = (
            EventConditionedForecast
            if expert.kind is ExpertKind.AFRE_EVENT
            else RegimeConditionedForecast
        )
        require(type(value) is expected, "conditioned expert forecast family mismatch")
        assert isinstance(value, (EventConditionedForecast, RegimeConditionedForecast))
        require(
            value.model_id == expert.model_id
            and value.target_definition_id == expert.target.fingerprint,
            "conditioned expert producer/target mismatch",
        )
        observation = (
            repo.resolve(EventConditionedObservation, value.observation_id)
            if isinstance(value, EventConditionedForecast)
            else repo.resolve(RegimeConditionedSample, value.observation_id)
        )
        sample_id = observation.sample_id
        origin, available, asof = value.origin, value.available_ns, value.origin.timestamp_ns
        if expert.output is ExpertOutput.POINT:
            point = value.value
        else:
            distribution = value.distribution
            require(distribution is not None, "conditioned probability expert unavailable")
    if distribution is not None:
        point = expected_value(distribution)
    return ExpertForecastBinding(
        expert.fingerprint,
        forecast_id,
        origin,
        expert.target.fingerprint,
        max(available, expert.available_ns),
        quality,
        point,
        distribution,
        sample_id,
        asof,
    )


def gating_value_for(
    repo: "MixtureRepository",
    feature: GatingFeatureReference,
    approved_attestors: tuple[str, ...] | None = None,
) -> None:
    value = repo.get_any(feature.source_id)
    if isinstance(value, (FeatureVintage, ExternalSignal, RegimeSnapshot)):
        proof = value.clocks.historical_delivery
        require(
            proof is None or approved_attestors is None or proof.attestor in approved_attestors,
            "unapproved gating historical delivery",
        )
    if isinstance(value, FeatureVintage):
        require(
            value.state is MissingState.PRESENT
            and value.quality is DataQuality.VERIFIED
            and value.entity == feature.origin.instrument
            and value.effective_ns <= feature.origin.timestamp_ns
            and value.feature.definition.fingerprint == feature.feature_id,
            "gating feature exact usable security vintage",
        )
        numeric = value.value
        available = value.clocks.final_available_ns
        name = value.feature.definition.name
    elif isinstance(value, ExternalSignal):
        require(
            value.quality is SignalQuality.VALID
            and value.security.instrument == feature.origin.instrument
            and value.as_of_ns <= feature.origin.timestamp_ns
            and feature.feature_id == value.signal_name + ":" + value.signal_version,
            "gating external exact signal evidence",
        )
        numeric = value.value
        available = value.clocks.final_available_ns
        name = value.signal_name
    else:
        require(isinstance(value, RegimeSnapshot), "unsupported gating source family")
        assert isinstance(value, RegimeSnapshot)
        require(
            value.semantics is RegimeStateSemantics.FILTERED
            and value.quality is RegimeQuality.VALID
            and value.as_of_ns <= feature.origin.timestamp_ns,
            "gating regime must be causal filtered state",
        )
        require(
            value.subject.entity == feature.origin.instrument,
            "only security-scoped regime gating evidence supported",
        )
        weights = dict(zip(value.membership.states, value.membership.weights, strict=True))
        require(feature.feature_id in weights, "gating regime exact state identity")
        numeric, available, name = (
            weights[feature.feature_id],
            value.clocks.final_available_ns,
            feature.feature_id,
        )
    require(type(numeric) in (float, int), "gating scalar must be numeric")
    assert isinstance(numeric, (int, float))
    require(
        float(numeric) == feature.value and available == feature.available_ns,
        "gating scalar/availability mismatch",
    )
    require(
        not {
            "positions",
            "position",
            "orders",
            "pending_orders",
            "live_inventory",
            "execution",
            "execution_decisions",
        }.intersection(name.lower().split(".")),
        "execution inputs forbidden in gate",
    )

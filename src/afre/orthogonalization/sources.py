"""Closed provider-neutral source extraction; provider clocks never imply AFRE receipt."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from afre.cross_sectional.external import ExternalSignal
from afre.event_conditioned.artifacts import EventConditionedForecast
from afre.feature_store.models import FeatureVintage
from afre.mixture.artifacts import MixtureForecast
from afre.mixture.experts import ExpertForecastBinding
from afre.nonlinear.artifacts import NonlinearForecast, ScalarInput
from afre.orthogonalization.definitions import SignalReference
from afre.orthogonalization.schema import OrthogonalQuality
from afre.orthogonalization.schema import SignalSourceType as Kind
from afre.orthogonalization.signals import GenericSignalSource, SignalObservation
from afre.probabilistic.distributions import expected_value
from afre.regime_conditioned.artifacts import RegimeConditionedForecast
from afre.research_datasets.samples import ResearchSample
from afre.schema import require
from afre.sequence.artifacts import SequenceForecast
from afre.target_engine.definitions import TargetDefinition
from afre.uncertainty.artifacts import ForecastUncertaintyDecomposition

if TYPE_CHECKING:
    from afre.orthogonalization.repository import OrthogonalizationRepository


@dataclass(frozen=True)
class ScalarSource:
    kind: Kind
    key: tuple[str, ...]
    provider: str
    version: str
    unit: str
    value: float | None
    available_ns: int
    target: TargetDefinition | None


def scalar_source(
    repo: "OrthogonalizationRepository", identity: str, sample: ResearchSample, selector: str
) -> ScalarSource:
    raw = repo.get_any(identity)
    repo._validate_links(raw)
    require(
        sample.origin is not None and not sample.dropped,
        "admitted exact research sample required",
    )
    assert sample.origin is not None
    origin = sample.origin
    target = None
    if isinstance(raw, GenericSignalSource):
        require(raw.origin == origin, "generic exact full origin")
        return ScalarSource(
            Kind.GENERIC,
            raw.reference.source_key,
            raw.reference.provider,
            raw.reference.provider_version,
            raw.reference.unit,
            raw.value,
            raw.clocks.final_available_ns,
            raw.reference.target,
        )
    if isinstance(raw, FeatureVintage):
        require(
            selector == "value"
            and raw.entity == origin.instrument
            and raw.effective_ns <= origin.timestamp_ns
            and (raw.valid_until_ns is None or origin.timestamp_ns < raw.valid_until_ns),
            "feature entity/time/selector mismatch",
        )
        require(
            raw.value is None or type(raw.value) in (int, float),
            "signal source must be an explicit numerical scalar",
        )
        number = (
            float(raw.value)
            if isinstance(raw.value, (float, int)) and not isinstance(raw.value, bool)
            else None
        )
        return ScalarSource(
            Kind.FEATURE,
            (raw.feature.fingerprint,),
            "AFRE-feature",
            raw.feature.definition.version,
            raw.feature.definition.unit,
            number,
            raw.clocks.final_available_ns,
            None,
        )
    if isinstance(raw, ExternalSignal):
        require(
            selector == "value"
            and raw.security.instrument == origin.instrument
            and raw.as_of_ns <= origin.timestamp_ns,
            "external entity/time/selector mismatch",
        )
        require(
            raw.value is None or type(raw.value) in (int, float),
            "signal source must be an explicit numerical scalar",
        )
        number = (
            float(raw.value)
            if isinstance(raw.value, (float, int)) and not isinstance(raw.value, bool)
            else None
        )
        return ScalarSource(
            Kind.EXTERNAL,
            raw.semantic_key,
            raw.provider_name,
            raw.provider_version,
            raw.unit,
            number,
            raw.clocks.final_available_ns,
            None,
        )
    if isinstance(raw, ScalarInput):
        require(selector == "value" and raw.origin == origin, "scalar exact full origin")
        return ScalarSource(
            Kind.SCALAR,
            (raw.definition.fingerprint,),
            "AFRE-scalar",
            raw.definition.fingerprint,
            raw.definition.unit,
            raw.value,
            raw.available_ns,
            None,
        )
    if isinstance(raw, ExpertForecastBinding):
        require(
            selector == "value"
            and raw.origin == origin
            and raw.sample_id in (None, sample.fingerprint),
            "expert exact full origin/sample",
        )
        target = repo.resolve(TargetDefinition, raw.target_definition_id)
        return ScalarSource(
            Kind.EXPERT,
            (raw.expert_id,),
            "AFRE-expert",
            raw.expert_id,
            "target-value:" + target.fingerprint,
            raw.point
            if raw.point is not None
            else expected_value(raw.distribution)
            if raw.distribution is not None
            else None,
            raw.available_ns,
            target,
        )
    require(
        isinstance(
            raw,
            (
                EventConditionedForecast,
                RegimeConditionedForecast,
                MixtureForecast,
                NonlinearForecast,
                SequenceForecast,
                ForecastUncertaintyDecomposition,
            ),
        ),
        "unsupported signal artifact source",
    )
    assert isinstance(
        raw,
        (
            EventConditionedForecast,
            RegimeConditionedForecast,
            MixtureForecast,
            NonlinearForecast,
            SequenceForecast,
            ForecastUncertaintyDecomposition,
        ),
    )
    require(raw.origin == origin, "native signal exact full origin")
    if isinstance(raw, ForecastUncertaintyDecomposition):
        require(raw.sample_id == sample.fingerprint, "uncertainty exact sample")
    else:
        from afre.uncertainty.sources import source_for

        require(
            source_for(repo, raw.fingerprint).sample_id == sample.fingerprint,
            "native forecast exact research sample",
        )
    target_id = (
        raw.target_id
        if isinstance(raw, ForecastUncertaintyDecomposition)
        else raw.target_definition_id
    )
    target = repo.resolve(TargetDefinition, target_id)
    require(
        target.fingerprint == sample.target_definition_id, "native signal exact target/horizon"
    )
    unit = "target-value:" + target.fingerprint
    if isinstance(raw, ForecastUncertaintyDecomposition):
        component = next((c for c in raw.components if c.component.value == selector), None)
        require(
            component is not None and component.value is not None,
            "uncertainty scalar requires identified/explicit proxy numerical component",
        )
        assert component is not None
        from afre.orthogonalization.source_policy import diagnostic_policy_key
        from afre.uncertainty.definitions import UncertaintySpec
        from afre.uncertainty.sources import source_for

        policy = repo.resolve(UncertaintySpec, raw.spec_id)
        underlying = source_for(repo, raw.forecast_id)
        return ScalarSource(
            Kind.UNCERTAINTY,
            (
                underlying.model_id,
                component.component.value,
                component.measure.value,
                component.method,
                policy.covariance_id or "none",
                policy.closure.value,
                diagnostic_policy_key(repo, policy, component),
            ),
            "AFRE-uncertainty",
            "1.0",
            component.units,
            component.value,
            raw.available_ns,
            target,
        )
    if isinstance(raw, MixtureForecast):
        require(
            selector == "value" and raw.request.sample_id == sample.fingerprint,
            "mixture exact sample/selector",
        )
        return ScalarSource(
            Kind.MIXTURE,
            (raw.request.gate_id,),
            "AFRE-mixture",
            raw.request.gate_id,
            unit,
            raw.value,
            raw.available_ns,
            target,
        )
    require(
        selector == "value"
        or isinstance(raw, (EventConditionedForecast, RegimeConditionedForecast)),
        "unsupported native scalar selector",
    )
    number = raw.value
    if isinstance(raw, EventConditionedForecast):
        require(selector in ("value", "shift"), "event selector")
        number = raw.shift if selector == "shift" else number
        kind = Kind.EVENT
    elif isinstance(raw, RegimeConditionedForecast):
        kind = Kind.REGIME
        if selector != "value":
            require(
                raw.membership is not None and selector in raw.membership.states,
                "regime supplied probability state required",
            )
            assert raw.membership is not None
            number = raw.membership.weights[raw.membership.states.index(selector)]
            unit = "probability"
    else:
        kind = Kind.NONLINEAR if isinstance(raw, NonlinearForecast) else Kind.SEQUENCE
        require(raw.sample_id == sample.fingerprint, "native output exact sample")
    return ScalarSource(
        kind,
        (raw.model_id,),
        "AFRE-" + kind.value,
        raw.model_id,
        unit,
        number,
        raw.available_ns,
        target,
    )


def reference_for(
    repo: "OrthogonalizationRepository",
    source_id: str,
    sample_id: str,
    signal_id: str,
    selector: str = "value",
) -> SignalReference:
    with repo.feature_only():
        sample = repo.resolve(ResearchSample, sample_id)
        source = scalar_source(repo, source_id, sample, selector)
        return SignalReference(
            signal_id,
            source.kind,
            source.key,
            source.provider,
            source.version,
            signal_id,
            "1",
            source.unit,
            selector,
            source.target,
        )


def observation_for(
    repo: "OrthogonalizationRepository",
    reference: SignalReference,
    source_id: str,
    sample_id: str,
    approved_attestors: tuple[str, ...] = (),
) -> SignalObservation:
    sample = repo.resolve(ResearchSample, sample_id)
    raw = repo.get_any(source_id)
    if isinstance(raw, (GenericSignalSource, ExternalSignal, FeatureVintage)):
        proof = raw.clocks.historical_delivery
        require(
            proof is None or proof.attestor in approved_attestors,
            "qualified reconstruction requires caller-approved historical attestor",
        )
    scalar = scalar_source(repo, source_id, sample, reference.selector)
    require(
        (
            reference.source_type,
            reference.source_key,
            reference.provider,
            reference.provider_version,
            reference.unit,
            reference.target,
        )
        == (
            scalar.kind,
            scalar.key,
            scalar.provider,
            scalar.version,
            scalar.unit,
            scalar.target,
        ),
        "signal source semantic/version/unit mismatch",
    )
    require(
        scalar.target is None or scalar.target.fingerprint == sample.target_definition_id,
        "predictive signal exact sample target/horizon",
    )
    assert sample.origin is not None
    return SignalObservation(
        reference.fingerprint,
        source_id,
        sample_id,
        sample.origin,
        scalar.value,
        OrthogonalQuality.AVAILABLE if scalar.value is not None else OrthogonalQuality.MISSING,
        scalar.available_ns,
        approved_attestors,
    )
